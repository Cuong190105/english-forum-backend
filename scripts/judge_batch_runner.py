from __future__ import annotations
import os
import csv
import json
import time
from pathlib import Path
import inspect
import tempfile
from typing import List, Dict, Any, Optional, Set, Tuple
import sys

# Ensure project root on path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmark.judge import MCQ_SYS, FILL_SYS, _parse_json_loose, judge_mcq_deepseek, judge_fill_deepseek

try:
    from google import genai
except Exception:
    genai = None


def load_per_item(run_id: str) -> List[Dict[str, Any]]:
    p = Path(f"benchmark/reports/{run_id}/per_item.csv")
    if not p.exists():
        raise FileNotFoundError(p)
    out = []
    with p.open('r', encoding='utf-8') as f:
        rdr = csv.DictReader(f)
        for r in rdr:
            out.append(dict(r))
    return out


def _read_existing_row_idx(out_p: Path) -> Set[int]:
    idxs: Set[int] = set()
    if not out_p.exists():
        return idxs
    try:
        with out_p.open('r', encoding='utf-8') as f:
            rdr = csv.DictReader(f)
            for r in rdr:
                try:
                    if 'row_idx' in r and r['row_idx'] != '':
                        idxs.add(int(r['row_idx']))
                except Exception:
                    continue
    except Exception:
        pass
    return idxs


def _open_out_writer(out_dir: Path, header_keys: List[str]) -> csv.DictWriter:
    out_dir.mkdir(parents=True, exist_ok=True)
    out_p = out_dir / 'per_item.csv'
    file_exists = out_p.exists()
    f = out_p.open('a', encoding='utf-8', newline='')
    w = csv.DictWriter(f, fieldnames=header_keys)
    if not file_exists:
        w.writeheader()
    # Attach file handle so caller can close later
    w._outfile_handle = f  # type: ignore[attr-defined]
    return w


def _extract_batch_name(obj: Any) -> Optional[str]:
    try:
        if isinstance(obj, dict):
            return obj.get('name') or obj.get('id')
        return getattr(obj, 'name', None) or getattr(obj, 'id', None)
    except Exception:
        return None


def _extract_batch_state(obj: Any) -> Optional[str]:
    try:
        # Direct attributes first
        state = getattr(obj, 'state', None) or getattr(obj, 'status', None)
        if isinstance(state, str) and state:
            return state
        # Try metadata attr
        meta = getattr(obj, 'metadata', None)
        if meta is not None:
            if isinstance(meta, dict):
                mstate = meta.get('state') or meta.get('status')
                if isinstance(mstate, str) and mstate:
                    return mstate
            else:
                mstate = getattr(meta, 'state', None) or getattr(meta, 'status', None)
                if isinstance(mstate, str) and mstate:
                    return mstate
        # Try dict form
        if isinstance(obj, dict):
            state = obj.get('state') or obj.get('status')
            if isinstance(state, str) and state:
                return state
            meta = obj.get('metadata')
            if isinstance(meta, dict):
                mstate = meta.get('state') or meta.get('status')
                if isinstance(mstate, str) and mstate:
                    return mstate
        # Last resort: to_dict
        if hasattr(obj, 'to_dict'):
            d = obj.to_dict()
            if isinstance(d, dict):
                s = d.get('state') or d.get('status')
                if isinstance(s, str) and s:
                    return s
                m = d.get('metadata')
                if isinstance(m, dict):
                    s2 = m.get('state') or m.get('status')
                    if isinstance(s2, str) and s2:
                        return s2
    except Exception:
        return None
    return None


def _gemini_build_user_contents(prompt: str) -> List[Dict[str, Any]]:
    # Gemini Batch API expects messages-style contents
    return [{
        'role': 'user',
        'parts': [{'text': prompt}]
    }]


def _normalize_model_name(model: Any) -> str:
    if isinstance(model, (list, tuple)):
        model = model[0] if model else ''
    s = (str(model or '')).strip()
    if not s:
        s = 'gemini-2.5-pro'
    if not s.startswith('models/'):
        s = f'models/{s}'
    return s


def _files_upload_bytes(client: Any, name: str, mime_type: str, data: bytes):
    """Upload bytes to the provider, trying multiple possible SDK shapes.
    Detect files object under: client.files, client.upload_files, client.uploadFiles.
    Only include kwargs that the target method actually supports (no unconditional name=).
    """
    fobj = (
        getattr(client, "files", None)
        or getattr(client, "upload_files", None)
        or getattr(client, "uploadFiles", None)
    )
    if fobj is None:
        raise RuntimeError("client.files/upload_files/uploadFiles not available")

    tried: List[str] = []
    upload_fn = getattr(fobj, "upload", None)
    create_fn = getattr(fobj, "create", None)

    def _sig_info(fn) -> Tuple[Optional[set], bool]:
        try:
            sig = inspect.signature(fn)
            params = set(sig.parameters.keys())
            accepts_var_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
            return params, accepts_var_kw
        except Exception:
            return None, True  # assume permissive when unknown

    def _try(fn, kwargs: Dict[str, Any]):
        try:
            return fn(**kwargs)
        except TypeError as e:
            tried.append(f"{getattr(fn, '__name__', 'upload')} {e}; kwargs={list(kwargs.keys())}")
            return None
        except Exception as e:
            tried.append(f"{getattr(fn, '__name__', 'upload')} {e}; kwargs={list(kwargs.keys())}")
            return None

    def _maybe_add(d: Dict[str, Any], key: str, val: Any, params: Optional[set], accepts_var_kw: bool):
        if params is None or key in params or accepts_var_kw:
            d[key] = val

    # Prefer upload(...)
    if upload_fn:
        params, accepts_any = _sig_info(upload_fn)

        # bytes params (contents | content | data | file)
        for key in ("contents", "content", "data", "file"):
            if params is None or key in params or accepts_any:
                kw: Dict[str, Any] = {}
                _maybe_add(kw, key, data, params, accepts_any)
                # include mime_type if accepted as either mime_type or mimeType
                if params is None or "mime_type" in params or accepts_any:
                    kw["mime_type"] = mime_type
                elif "mimeType" in (params or set()):
                    kw["mimeType"] = mime_type
                # include name only if accepted
                if params is None or "name" in params or accepts_any:
                    kw["name"] = name
                obj = _try(upload_fn, kw)
                if obj is not None:
                    return obj

        # path-ish params: try path=, then file= with path, then file= with file object
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / name
            p.write_bytes(data)
            # Also create a .json copy to help SDKs infer mime when mime_type kw not supported
            p_json = Path(td) / (Path(name).stem + ".json")
            try:
                p_json.write_bytes(data)
            except Exception:
                p_json = p

            if params is None or "path" in params or accepts_any:
                kw2: Dict[str, Any] = {"path": str(p)}
                if params is None or "mime_type" in params or accepts_any:
                    kw2["mime_type"] = mime_type
                elif "mimeType" in (params or set()):
                    kw2["mimeType"] = mime_type
                if params is None or "name" in params or accepts_any:
                    kw2["name"] = name
                obj = _try(upload_fn, kw2)
                if obj is not None:
                    return obj
                # Try .json copy for mime inference
                kw2b = dict(kw2)
                kw2b["path"] = str(p_json)
                obj = _try(upload_fn, kw2b)
                if obj is not None:
                    return obj

            if params is None or "file" in params or accepts_any:
                # Try multiple combinations: with mime_type, with mimeType, with/without name
                attempts: List[Dict[str, Any]] = []
                attempts.append({"file": str(p), "mime_type": mime_type, "name": name})
                attempts.append({"file": str(p), "mimeType": mime_type, "name": name})
                attempts.append({"file": str(p), "mime_type": mime_type})
                attempts.append({"file": str(p), "mimeType": mime_type})
                attempts.append({"file": str(p)})
                # Try .json copy
                attempts.append({"file": str(p_json), "mime_type": mime_type, "name": name})
                attempts.append({"file": str(p_json), "mimeType": mime_type, "name": name})
                attempts.append({"file": str(p_json), "mime_type": mime_type})
                attempts.append({"file": str(p_json), "mimeType": mime_type})
                attempts.append({"file": str(p_json)})
                for kw3 in attempts:
                    obj = _try(upload_fn, kw3)
                    if obj is not None:
                        return obj

                # file as file object with same combinations
                try:
                    with p.open('rb') as fh:
                        attempts2: List[Dict[str, Any]] = []
                        attempts2.append({"file": fh, "mime_type": mime_type, "name": name})
                        attempts2.append({"file": fh, "mimeType": mime_type, "name": name})
                        attempts2.append({"file": fh, "mime_type": mime_type})
                        attempts2.append({"file": fh, "mimeType": mime_type})
                        attempts2.append({"file": fh})
                        for kw4 in attempts2:
                            obj = _try(upload_fn, kw4)
                            if obj is not None:
                                return obj
                except Exception:
                    pass

    # Fallback create(...)
    if create_fn:
        params_c, accepts_any_c = _sig_info(create_fn)
        for key in ("contents", "content", "data", "file"):
            if params_c is None or key in params_c or accepts_any_c:
                kw3: Dict[str, Any] = {}
                _maybe_add(kw3, key, data, params_c, accepts_any_c)
                if params_c is None or "mime_type" in params_c or accepts_any_c:
                    kw3["mime_type"] = mime_type
                elif "mimeType" in (params_c or set()):
                    kw3["mimeType"] = mime_type
                if params_c is None or "name" in params_c or accepts_any_c:
                    kw3["name"] = name
                obj = _try(create_fn, kw3)
                if obj is not None:
                    return obj

    raise RuntimeError("Files upload failed; tried:\n" + "\n".join(tried))


def _files_download(client: Any, file_name: str) -> bytes:
    fobj = (
        getattr(client, "files", None)
        or getattr(client, "upload_files", None)
        or getattr(client, "uploadFiles", None)
    )
    if fobj is None:
        raise RuntimeError("client.files/upload_files/uploadFiles not available")
    dl = getattr(fobj, "download", None)
    if not dl:
        raise RuntimeError("client.files.download not available")
    try:
        return dl(file=file_name)          # variant A
    except TypeError:
        return dl(name=file_name)          # variant B


def call_gemini_batch_api(
    prompts: List[str],
    model: str,
    display_name: Optional[str] = None,
    poll_interval_s: float = 5.0,
    timeout_s: float = 60*60,
    response_schema: Optional[Any] = None,
    **_: Any,
) -> Tuple[List[str], Optional[Dict[str, Any]]]:
    from google import genai  # dùng đúng SDK đã cài
    key = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
    if not key:
        raise RuntimeError('GEMINI/GOOGLE API key not set')
    client = genai.Client(api_key=key)

    model = _normalize_model_name(model)

    # Build requests payload (messages style)
    reqs = [{"contents": [{"role": "user", "parts": [{"text": p}]}]} for p in prompts]

    print(f"[Gemini] Submitting batch of {len(prompts)} prompts to model '{model}'...", flush=True)
    # Try requests=
    batch = None
    create_fn = getattr(client.batches, 'create')
    # Inspect signature to include only supported kwargs
    try:
        sig_b = inspect.signature(create_fn)
        params_b = set(sig_b.parameters.keys())
        accepts_any_b = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig_b.parameters.values())
    except Exception:
        params_b, accepts_any_b = None, True
    try:
        kw_batch = {"model": model, "requests": reqs}
        if display_name and (params_b is None or 'display_name' in params_b or accepts_any_b):
            kw_batch["display_name"] = display_name
        batch = create_fn(**kw_batch)
    except TypeError as e_req:
        # Fallback: upload JSONL + src=
        print("[Gemini] requests= path failed. Falling back to JSONL upload + src=.", flush=True)
        gen_cfg = {
            "responseMimeType": "application/json",
            "temperature": 0,
            "topP": 0,
        }
        lines = []
        for p in prompts:
            req = {
                "contents": [{"role": "user", "parts": [{"text": p}]}],
                "generationConfig": gen_cfg,
            }
            lines.append(json.dumps({"request": req}, ensure_ascii=False))
        jsonl_bytes = ("\n".join(lines)).encode("utf-8")
        up = None
        last_err = None
        for mime in ("application/jsonl", "application/x-ndjson"):
            try:
                up = _files_upload_bytes(client, name=f"batch_{int(time.time())}.jsonl", mime_type=mime, data=jsonl_bytes)
                break
            except Exception as e_up:
                last_err = e_up
        if up is None:
            raise RuntimeError(f"Gemini files.upload failed: {last_err}")
        src_name = getattr(up, "name", None) or getattr(up, "id", None)
        if not src_name:
            raise RuntimeError("Upload returned no file name/id")
        try:
            kw_src = {"model": model, "src": src_name}
            if display_name and (params_b is None or 'display_name' in params_b or accepts_any_b):
                kw_src["display_name"] = display_name
            batch = create_fn(**kw_src)
        except Exception as e_src:
            raise RuntimeError(f"Gemini batches.create failed for model {model}: {e_src}") from e_req

    name = getattr(batch, "name", None) or getattr(batch, "id", None)
    if not name:
        raise RuntimeError("Gemini Batch missing name/id")

    # Poll
    t0 = time.time()
    while True:
        # some SDKs expose state/status/metadata.state
        state = getattr(batch, "state", None) or getattr(batch, "status", None)
        if not isinstance(state, str):
            meta = getattr(batch, "metadata", None)
            state = getattr(meta, "state", None) or getattr(meta, "status", None) if meta else None
        state_u = (state or "").upper()
        waited = int(time.time() - t0)
        if waited == 0 or waited % max(5, int(poll_interval_s)) == 0:
            print(f"[Gemini] Polling: state={state_u or 'UNKNOWN'} waited={waited}s name={name}", flush=True)
        if state_u in ("SUCCEEDED", "COMPLETED") or state_u.endswith("_SUCCEEDED") or state_u.endswith("_COMPLETED"):
            break
        if state_u in ("FAILED", "CANCELLED", "CANCELED") or state_u.endswith("_FAILED") or state_u.endswith("_CANCELLED") or state_u.endswith("_CANCELED"):
            raise RuntimeError(f"Gemini Batch state={state_u}")
        if (time.time() - t0) > timeout_s:
            raise TimeoutError("Gemini Batch timeout")
        time.sleep(poll_interval_s)
        # refresh
        try:
            batch = client.batches.get(name=name)
        except Exception:
            pass

    # Retrieve
    try:
        batch = client.batches.get(name=name)
    except Exception:
        pass

    # inline_output (newer) or dest.file_name/inlined_responses (older)
    inline_output = getattr(batch, "inline_output", None) or getattr(batch, "inlineOutput", None)
    lines: List[str] = []
    result_source = "unknown"

    if inline_output is not None:
        inline_res = getattr(inline_output, "inline_responses", None) or getattr(inline_output, "inlineResponses", None)
        if inline_res is not None:
            for idx, ir in enumerate(inline_res):
                resp = getattr(ir, "response", None)
                err = getattr(ir, "error", None)
                item = {"index": idx}
                if resp is not None:
                    txt = getattr(resp, "text", None)
                    if txt is None and hasattr(resp, "to_dict"):
                        item["response"] = resp.to_dict()
                    else:
                        item["response"] = {"text": (txt or "")}
                elif err is not None:
                    if hasattr(err, "to_dict"):
                        item["error"] = err.to_dict()
                    else:
                        item["error"] = str(err)
                lines.append(json.dumps(item, ensure_ascii=False))
            result_source = "inline"
    else:
        dest = getattr(batch, "dest", None)
        file_name = getattr(dest, "file_name", None) if dest is not None else None
        inlined = getattr(dest, "inlined_responses", None) if dest is not None else None
        if file_name:
            data_bytes = _files_download(client, file_name)
            text = data_bytes.decode("utf-8", errors="ignore") if isinstance(data_bytes, (bytes, bytearray)) else str(data_bytes)
            lines = text.splitlines()
            result_source = "file"
        elif inlined is not None:
            for idx, ir in enumerate(inlined):
                resp = getattr(ir, "response", None)
                err = getattr(ir, "error", None)
                item = {"index": idx}
                if resp is not None:
                    txt = getattr(resp, "text", None)
                    if txt is None and hasattr(resp, "to_dict"):
                        item["response"] = resp.to_dict()
                    else:
                        item["response"] = {"text": (txt or "")}
                elif err is not None:
                    if hasattr(err, "to_dict"):
                        item["error"] = err.to_dict()
                    else:
                        item["error"] = str(err)
                lines.append(json.dumps(item, ensure_ascii=False))
            result_source = "dest.inline"

    print(f"[Gemini] Retrieved {len(lines)} result lines from {result_source}.", flush=True)

    # Parse -> list[str] aligned by index
    out_by_idx: Dict[int, str] = {}
    errs = 0
    for i, line in enumerate(lines):
        try:
            j = json.loads(line)
        except Exception:
            out_by_idx[i] = line
            continue
        txt = ""
        if isinstance(j, dict) and j.get("error") is not None:
            try:
                txt = json.dumps(j["error"], ensure_ascii=False)
            except Exception:
                txt = str(j["error"])
            errs += 1
        resp = j.get("response") if isinstance(j, dict) else None
        if isinstance(resp, dict) and not txt:
            cand = resp.get("candidates")
            if isinstance(cand, list) and cand:
                content = cand[0].get("content") or {}
                parts = content.get("parts") or []
                if isinstance(parts, list):
                    for part in parts:
                        if isinstance(part, dict) and "text" in part:
                            txt = part["text"]; break
            if not txt:
                txt = resp.get("text") or ""
        if not txt:
            txt = j.get("text") or j.get("output") or ""
        idx_val = j.get("index") or j.get("requestIndex") or j.get("input_index") or j.get("request_index")
        try:
            out_by_idx[int(idx_val)] = txt
        except Exception:
            out_by_idx[i] = txt

    out = [out_by_idx.get(i, "") for i in range(len(prompts))]
    meta = {"batch_name": name, "result_source": result_source, "error_count": errs, "response_count": len(out)}
    return out, meta


# Note: No async fallback for Gemini; Batch API is mandatory per requirements.
def _upload_jsonl_for_batch(client: Any, prompts: List[str]) -> str:
    """Build a JSONL with one request per line including generation_config, upload via files API, and
    return the uploaded file name/id suitable for batches.create(src=...)."""
    # Build JSONL lines
    lines: List[str] = []
    gen_cfg = {
        'response_mime_type': 'application/json',
        'temperature': 0,
        'top_p': 0,
    }
    for p in prompts:
        obj = {
            'contents': _gemini_build_user_contents(p),
            'generation_config': gen_cfg,
        }
        lines.append(json.dumps(obj, ensure_ascii=False))
    data = ("\n".join(lines)).encode('utf-8')

    # Write to a temp .jsonl file
    with tempfile.NamedTemporaryFile(delete=False, suffix='.jsonl') as tmp:
        tmp_path = tmp.name
        tmp.write(data)
    uploaded_name: Optional[str] = None
    last_err: Optional[Exception] = None
    try:
        # Try with explicit mime_type first (ndjson preferred for JSONL)
        mime_candidates = ['application/x-ndjson', 'application/jsonl', 'application/json', 'text/plain']
        res = None
        upload_fn = getattr(client.files, 'upload', None)
        if upload_fn is None:
            raise RuntimeError('client.files.upload not available')
        try:
            sig = inspect.signature(upload_fn)
            params = set(sig.parameters.keys())
        except Exception:
            params = set()

        # Helper to extract name/id from upload response
        def _extract_name(obj: Any) -> Optional[str]:
            n = getattr(obj, 'name', None) or getattr(obj, 'id', None)
            if n:
                return str(n)
            if hasattr(obj, 'to_dict'):
                try:
                    rd = obj.to_dict()
                    if isinstance(rd, dict):
                        return rd.get('name') or rd.get('id') or rd.get('file')
                except Exception:
                    pass
            return None

        # Strategy matrix based on accepted parameters
        # A) path + mime_type
        if res is None and ('path' in params or not params):
            for mt in mime_candidates:
                try:
                    res = upload_fn(path=tmp_path, mime_type=mt)  # type: ignore[call-arg]
                    uploaded_name = _extract_name(res)
                    if uploaded_name:
                        break
                except Exception as e:
                    last_err = e
                    res = None

        # B) file + mime_type (file can be path or file object)
        if res is None and 'file' in params:
            for mt in mime_candidates:
                try:
                    res = upload_fn(file=tmp_path, mime_type=mt)  # type: ignore[call-arg]
                    uploaded_name = _extract_name(res)
                    if uploaded_name:
                        break
                except Exception as e:
                    last_err = e
                    res = None
            if res is None:
                with open(tmp_path, 'rb') as f:
                    for mt in mime_candidates:
                        try:
                            res = upload_fn(file=f, mime_type=mt)  # type: ignore[call-arg]
                            uploaded_name = _extract_name(res)
                            if uploaded_name:
                                break
                        except Exception as e:
                            last_err = e
                            res = None
                            f.seek(0)

        # C) contents (+ optional name) + mime_type
        if res is None and 'contents' in params:
            base = os.path.basename(tmp_path)
            for mt in mime_candidates:
                try:
                    kwargs = {'contents': data, 'mime_type': mt}
                    # Only pass 'name' if accepted
                    if 'name' in params:
                        kwargs['name'] = base  # type: ignore[assignment]
                    res = upload_fn(**kwargs)  # type: ignore[misc]
                    uploaded_name = _extract_name(res)
                    if uploaded_name:
                        break
                except Exception as e:
                    last_err = e
                    res = None

        # D) Last ditch: positional upload with path or contents
        if res is None:
            try:
                res = upload_fn(tmp_path)  # type: ignore[misc]
                uploaded_name = _extract_name(res)
            except Exception as e:
                last_err = e
                res = None
        if res is None:
            try:
                res = upload_fn(data)  # type: ignore[misc]
                uploaded_name = _extract_name(res)
            except Exception as e:
                last_err = e
                res = None

        if res is None:
            raise last_err or RuntimeError('files.upload returned None')
        uploaded_name = _extract_name(res)
    except Exception as e:
        last_err = e
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass
    if not uploaded_name:
        raise RuntimeError(f"[Gemini] files.upload failed: {last_err}")
    print(f"[Gemini] Uploaded JSONL for batch: {uploaded_name}", flush=True)
    return uploaded_name


def call_claude_batch(payloads: List[Dict[str, Any]]) -> List[str]:
    """Call Claude batch endpoint. Requires CLAUDE_BATCH_URL and CLAUDE_API_KEY env vars.
    Returns list of raw texts (responses) in same order.
    This is a lightweight wrapper expecting the response to include per-item content under standard keys.
    """
    import requests
    url = os.getenv('CLAUDE_BATCH_URL')
    key = os.getenv('CLAUDE_API_KEY')
    if not url or not key:
        raise RuntimeError('Claude batch URL/API key not configured')
    headers = {'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'}
    body = {'messages': payloads}
    r = requests.post(url, headers=headers, json=body, timeout=120)
    r.raise_for_status()
    j = r.json()
    # The exact shape depends on Claude batch response; try to extract per-item content conservatively
    out: List[str] = []
    items = j.get('items') or j.get('responses') or []
    for it in items:
        # try common locations
        if isinstance(it, dict):
            text = it.get('response') or it.get('content') or it.get('text') or ''
            out.append(text)
        else:
            out.append(str(it))
    # If counts don't match, pad
    while len(out) < len(payloads):
        out.append('')
    return out


def load_claude_results(path: str) -> List[str]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(p)
    out: List[str] = []
    with p.open('r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                j = json.loads(line)
            except Exception:
                out.append(line)
                continue
            # try common keys
            text = ''
            for k in ('response','content','text','output','completion'):
                if k in j and isinstance(j[k], str):
                    text = j[k]
                    break
            # fallback: stringify
            if not text:
                text = json.dumps(j, ensure_ascii=False)
            out.append(text)
    return out


def rejudge_run(
    run_id: str,
    out_suffix: str = '_rejudged',
    batch_size: int = 16,
    stub: bool = True,
    claude_batch_file: Optional[str] = None,
    resume: bool = True,
    use_response_schema: bool = True,
    start_index: int = 0,
    limit: Optional[int] = None,
) -> Path:
    rows_all = load_per_item(run_id)
    # Bound start/limit and slice the working rows; keep global indexing aligned to original file via start_index
    if start_index < 0:
        start_index = 0
    if start_index > len(rows_all):
        start_index = len(rows_all)
    end_index = start_index + limit if (limit is not None) else len(rows_all)
    if end_index > len(rows_all):
        end_index = len(rows_all)
    rows = rows_all[start_index:end_index]
    out_dir = Path(f'benchmark/reports/{run_id}{out_suffix}')
    out_p = out_dir / 'per_item.csv'
    # Prepare existing set of processed row_idx for resume
    done_idx: Set[int] = _read_existing_row_idx(out_p) if resume else set()

    # Precompute prompts for gemini/claude batch when not stub
    gemini_model = os.getenv('JUDGE_MODEL') or 'gemini-2.5-pro'
    use_gemini = (not stub) and (genai is not None) and (os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY'))
    use_claude = (not stub) and (os.getenv('CLAUDE_BATCH_URL') and os.getenv('CLAUDE_API_KEY'))

    # If a precomputed Claude batch file is provided, load it once and reuse
    claude_texts_all: Optional[List[str]] = None
    if claude_batch_file:
        claude_texts_all = load_claude_results(claude_batch_file)

    print(f"[Rejudge] run_id={run_id} total_rows={len(rows)} batch_size={batch_size} resume={resume} start_index={start_index} limit={limit if limit is not None else 'all'}", flush=True)

    i = 0
    total = len(rows)
    # Prepare writer lazily on first write to know full header
    writer: Optional[csv.DictWriter] = None

    while i < total:
        batch_rows = rows[i:i+batch_size]
        print(f"[Rejudge] Processing batch rows {i}..{i + len(batch_rows) - 1}", flush=True)
        # If all rows in this batch are already done (by row_idx), skip quickly
        all_done = True
        for j in range(len(batch_rows)):
            if (start_index + i + j) not in done_idx:
                all_done = False
                break
        if all_done:
            print(f"[Rejudge] Skipping batch {i}..{i + len(batch_rows) - 1} (already completed)", flush=True)
            i += batch_size
            continue
        # Build prompts
        gemini_prompts: List[str] = []
        claude_payloads: List[Dict[str, Any]] = []
        for r in batch_rows:
            hw_type = (r.get('type') or 'mcq').lower()
            if hw_type == 'mcq':
                # Normalize options to a dict {"A": ..., "B": ...}
                opts_obj: Dict[str, Any] = {}
                raw_opts = r.get('options_json') if r.get('options_json') is not None else r.get('options')
                try:
                    if isinstance(raw_opts, str):
                        tmp = json.loads(raw_opts)
                    else:
                        tmp = raw_opts
                    if isinstance(tmp, list):
                        # Convert list to letter-indexed dict
                        letters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
                        opts_obj = {letters[i]: v for i, v in enumerate(tmp) if i < len(letters)}
                    elif isinstance(tmp, dict):
                        opts_obj = tmp
                except Exception:
                    opts_obj = {}

                user = json.dumps({
                    'stem': r.get('stem') or r.get('question_prompt') or r.get('question.prompt') or r.get('question', ''),
                    'options': opts_obj,
                    'correctOptionId': r.get('correctOptionId') or r.get('correct_option_id') or '',
                    'topic': r.get('topic') or ''
                }, ensure_ascii=False)
                prompt = f"{MCQ_SYS}\n{user}"
            else:
                user = json.dumps({
                    'prompt': r.get('question_prompt') or r.get('question.prompt') or r.get('prompt') or r.get('question', ''),
                    'answer': r.get('answer') or r.get('gold_answer') or '',
                    'topic': r.get('topic') or ''
                }, ensure_ascii=False)
                prompt = f"{FILL_SYS}\n{user}"
            gemini_prompts.append(prompt)
            claude_payloads.append({'role': 'user', 'content': prompt})

        gemini_texts: List[str] = []
        claude_texts: List[str] = []

        # Call Gemini using Batch API only
        if use_gemini:
            try:
                t0 = time.perf_counter()
                # response_schema not set at request level for batch; parse loosely
                gemini_texts, meta = call_gemini_batch_api(
                    gemini_prompts,
                    model=gemini_model,
                    display_name=f'{run_id}_rejudge_batch',
                )
                t1 = time.perf_counter()
                print(f"[Gemini] Batch completed in {t1 - t0:.1f}s for {len(gemini_prompts)} prompts.", flush=True)
            except Exception as e:
                print(f"[Gemini] Batch call failed: {e}", flush=True)
                gemini_texts = [''] * len(gemini_prompts)
        else:
            gemini_texts = [''] * len(gemini_prompts)

        # Call Claude batch if configured, or use preloaded results
        if claude_texts_all is not None:
            start_idx = start_index + i
            claude_texts = claude_texts_all[start_idx:start_idx + len(batch_rows)]
            if len(claude_texts) < len(batch_rows):
                claude_texts += [''] * (len(batch_rows) - len(claude_texts))
        elif use_claude:
            try:
                claude_texts = call_claude_batch(claude_payloads)
            except Exception as e:
                print(f"Claude batch failed: {e}")
                claude_texts = [''] * len(claude_payloads)
        else:
            claude_texts = [''] * len(claude_payloads)

        # For each item in batch, parse results (or stub)
        for idx, r in enumerate(batch_rows):
            global_row_idx = start_index + i + idx
            if resume and (global_row_idx in done_idx):
                continue
            hw_type = (r.get('type') or 'mcq').lower()
            # Start from original row but drop legacy 2-judge columns to avoid duplicates
            out_r = dict(r)
            for k in (
                'judge_verdict','judge_score','judge_why',
                'judge2_verdict','judge2_score','judge2_why'
            ):
                if k in out_r:
                    out_r.pop(k, None)
            out_r['row_idx'] = global_row_idx

            # GEMINI
            gtxt = gemini_texts[idx] if idx < len(gemini_texts) else ''
            if stub or not gtxt:
                prev = (r.get('judge_verdict') or r.get('verdict') or '').lower()
                if prev:
                    gver = prev
                else:
                    gver = 'correct' if hw_type == 'mcq' and (r.get('correctOptionId') and r.get('correctOptionId') != '') else ('acceptable' if hw_type == 'fill' else 'ambiguous')
                gwhy = 'stubbed'
            else:
                try:
                    parsed = _parse_json_loose(gtxt)
                    gver = parsed.get('verdict') or parsed.get('verdict'.upper()) or ''
                    gwhy = parsed.get('why') or ''
                except Exception:
                    gver = 'error'
                    gwhy = gtxt[:200]
            out_r['judge_gemini_verdict'] = (gver or '').lower()
            out_r['judge_gemini_why'] = gwhy

            # CLAUDE
            ctxt = claude_texts[idx] if idx < len(claude_texts) else ''
            if stub or not ctxt:
                prev2 = (r.get('judge2_verdict') or r.get('claude_verdict') or '').lower()
                if prev2:
                    cver = prev2
                else:
                    cver = 'ambiguous' if hw_type == 'mcq' else 'acceptable'
                cwhy = 'stubbed'
            else:
                try:
                    parsed2 = _parse_json_loose(ctxt)
                    cver = parsed2.get('verdict') or ''
                    cwhy = parsed2.get('why') or ''
                except Exception:
                    cver = 'error'
                    cwhy = ctxt[:200]
            out_r['judge_claude_verdict'] = (cver or '').lower()
            out_r['judge_claude_why'] = cwhy

            # DEEPSEEK (call per-item)
            try:
                t0 = time.perf_counter()
                if hw_type == 'mcq':
                    # Reuse the same normalization logic for DeepSeek
                    stem_val = r.get('stem') or r.get('question_prompt') or r.get('question.prompt') or r.get('question', '')
                    raw_opts = r.get('options_json') if r.get('options_json') is not None else r.get('options')
                    opts_obj: Dict[str, Any] = {}
                    try:
                        if isinstance(raw_opts, str):
                            tmp = json.loads(raw_opts)
                        else:
                            tmp = raw_opts
                        if isinstance(tmp, list):
                            letters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
                            opts_obj = {letters[i]: v for i, v in enumerate(tmp) if i < len(letters)}
                        elif isinstance(tmp, dict):
                            opts_obj = tmp
                    except Exception:
                        opts_obj = {}
                    ds = judge_mcq_deepseek(stem_val, opts_obj, r.get('correctOptionId') or r.get('correct_option_id') or '', r.get('topic') or '', context=None)
                else:
                    ds = judge_fill_deepseek(r.get('question_prompt') or r.get('question.prompt') or r.get('prompt') or r.get('question', ''), r.get('answer') or r.get('gold_answer') or '', r.get('topic') or '', context=None)
                dt = (time.perf_counter() - t0) * 1000.0
                ds_ver = ds.get('verdict') if isinstance(ds, dict) else ''
                ds_why = ds.get('why') if isinstance(ds, dict) else ''
            except Exception as e:
                ds_ver = 'error'
                ds_why = str(e)
                dt = ''
            out_r['judge_deepseek_verdict'] = (ds_ver or '').lower()
            out_r['judge_deepseek_why'] = ds_why

            # Lazily create writer with stable header order
            if writer is None:
                header_keys = list(out_r.keys())
                # Ensure 3-judge columns appear (even if blanks for some rows)
                for extra in [
                    'judge_gemini_verdict','judge_gemini_why',
                    'judge_claude_verdict','judge_claude_why',
                    'judge_deepseek_verdict','judge_deepseek_why',
                ]:
                    if extra not in header_keys:
                        header_keys.append(extra)
                writer = _open_out_writer(out_dir, header_keys)
            writer.writerow(out_r)
            try:
                writer._outfile_handle.flush()  # type: ignore[attr-defined]
            except Exception:
                pass

        print(f"[Rejudge] Finished batch rows {i}..{i + len(batch_rows) - 1}", flush=True)
        i += batch_size

    if writer is not None:
        try:
            writer._outfile_handle.close()  # type: ignore[attr-defined]
        except Exception:
            pass
    return out_dir


def main():
    import argparse
    ap = argparse.ArgumentParser(description='Re-judge an existing run using batch judges (Gemini, Claude, DeepSeek)')
    ap.add_argument('--run-id', required=True)
    ap.add_argument('--batch-size', type=int, default=16)
    ap.add_argument('--out-suffix', default='_rejudged')
    ap.add_argument('--no-stub', dest='stub', action='store_false')
    ap.set_defaults(stub=True)
    ap.add_argument('--claude-batch-file', dest='claude_batch_file', default=None,
                    help='Path to an existing Claude batch results JSONL to reuse')
    ap.add_argument('--no-resume', dest='resume', action='store_false', help='Disable resume (process all rows again)')
    ap.set_defaults(resume=True)
    ap.add_argument('--no-response-schema', dest='use_response_schema', action='store_false', help='Disable structured response schema for parsed output')
    ap.add_argument('--start-index', type=int, default=0, help='Start row index (0-based) within the original per_item.csv to process')
    ap.add_argument('--limit', type=int, default=None, help='Maximum number of rows to process from start-index')
    ap.set_defaults(use_response_schema=True)
    args = ap.parse_args()
    out = rejudge_run(
        args.run_id,
        out_suffix=args.out_suffix,
        batch_size=args.batch_size,
        stub=args.stub,
        claude_batch_file=args.claude_batch_file,
        resume=args.resume,
        use_response_schema=args.use_response_schema,
        start_index=args.start_index,
        limit=args.limit,
    )
    print(f'Rejudged per_item written to: {out / "per_item.csv"}')


if __name__ == '__main__':
    main()
