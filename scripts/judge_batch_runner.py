from __future__ import annotations
import os
import csv
import json
import time
from pathlib import Path
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


# ---- Utilities to reconstruct question data (stem/options/answer) from gold files ----
_GOLD_CACHE: Dict[Tuple[str, str, str, int], List[Dict[str, Any]]] = {}


def _topic_to_dir(topic: str) -> str:
    # Map display topic to folder (spaces -> '_')
    return (topic or '').strip().replace(' ', '_')


def _gold_load(topic: str, typ: str, sha: str, seed: int) -> List[Dict[str, Any]]:
    key = (_topic_to_dir(topic), typ, sha, seed)
    if key in _GOLD_CACHE:
        return _GOLD_CACHE[key]
    base = ROOT / 'benchmark' / 'gold' / _topic_to_dir(topic) / (typ or 'mcq') / (sha or '') / f'seed{seed}.json'
    try:
        with open(base, 'r', encoding='utf-8') as f:
            arr = json.load(f)
            if isinstance(arr, list):
                _GOLD_CACHE[key] = arr
                return arr
    except Exception:
        pass
    _GOLD_CACHE[key] = []
    return []


def _reconstruct_mcq(r: Dict[str, Any]) -> Tuple[str, Dict[str, str], str]:
    topic = r.get('topic') or ''
    sha = r.get('source_text_sha') or ''
    typ = 'mcq'
    try:
        seed = int(r.get('seed') or 0)
    except Exception:
        seed = 0
    items = _gold_load(topic, typ, sha, seed)
    stem = ''
    opts: Dict[str, str] = {}
    cid = ''
    # Prefer by qid_gold if present
    qid = r.get('qid_gold') or r.get('qid_pred') or ''
    found = None
    if qid:
        for it in items:
            try:
                q = it.get('question') or {}
                if (q.get('id') or '') == qid:
                    found = it
                    break
            except Exception:
                continue
    # Else by 1-based idx
    if found is None:
        try:
            idx = int(r.get('idx') or 1)
            if 1 <= idx <= len(items):
                found = items[idx - 1]
        except Exception:
            found = None
    if isinstance(found, dict):
        q = found.get('question') or {}
        stem = q.get('prompt') or ''
        cid = (found.get('correctOptionId') or '').upper()
        try:
            letters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
            arr = q.get('options') or []
            if isinstance(arr, list):
                for i, o in enumerate(arr):
                    oid = (o.get('id') or '').upper() or (letters[i] if i < len(letters) else str(i+1))
                    opts[oid] = o.get('label') or ''
        except Exception:
            opts = {}
    return stem, opts, cid


def _reconstruct_fill(r: Dict[str, Any]) -> Tuple[str, str]:
    topic = r.get('topic') or ''
    sha = r.get('source_text_sha') or ''
    typ = 'fill'
    try:
        seed = int(r.get('seed') or 0)
    except Exception:
        seed = 0
    items = _gold_load(topic, typ, sha, seed)
    prompt = ''
    ans = ''
    qid = r.get('qid_gold') or r.get('qid_pred') or ''
    found = None
    if qid:
        for it in items:
            try:
                q = it.get('question') or {}
                if (q.get('id') or '') == qid:
                    found = it
                    break
            except Exception:
                continue
    if found is None:
        try:
            idx = int(r.get('idx') or 1)
            if 1 <= idx <= len(items):
                found = items[idx - 1]
        except Exception:
            found = None
    if isinstance(found, dict):
        q = found.get('question') or {}
        prompt = q.get('prompt') or ''
        ans = found.get('answer') or ''
    return prompt, ans


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


def call_gemini_batch_api(
    prompts: List[str],
    model: str,
    display_name: Optional[str] = None,
    response_schema: Optional[Dict[str, Any]] = None,
    poll_interval_s: float = 5.0,
    timeout_s: float = 60 * 60 * 6,
) -> Tuple[List[str], Optional[Dict[str, Any]]]:
    """
    Use the official Gemini Batch API: enqueue -> poll -> download.
    Returns (texts, meta) where texts length == len(prompts).
    No fallback paths are used.
    """
    if genai is None:
        raise RuntimeError('google-genai not installed or GEMINI API key missing')
    key = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
    if not key:
        raise RuntimeError('GEMINI API key not set')
    client = genai.Client(api_key=key)

    if not (hasattr(client, 'batches') and hasattr(client.batches, 'create')):
        raise RuntimeError('Installed google-genai SDK does not expose Batch API (client.batches.create)')

    # Build inline requests per official SDK example
    requests_payload: List[Dict[str, Any]] = []
    for p in prompts:
        requests_payload.append({'contents': _gemini_build_user_contents(p)})

    # Normalize model name to the form 'models/...' expected by official docs
    if not model.startswith('models/'):
        model = f'models/{model}'
    print(f"[Gemini] Submitting batch of {len(prompts)} prompts to model '{model}'...", flush=True)

    # Create batch job
    try:
        if display_name:
            batch = client.batches.create(model=model, src=requests_payload, config={'display_name': display_name})
        else:
            batch = client.batches.create(model=model, src=requests_payload)
    except TypeError:
        # Alternate signature may accept display_name directly
        if display_name:
            batch = client.batches.create(model=model, src=requests_payload, display_name=display_name)
        else:
            batch = client.batches.create(model=model, src=requests_payload)

    name = _extract_batch_name(batch)
    print(f"[Gemini] Batch submitted. name={name}", flush=True)

    # Poll for completion
    started = time.time()
    last_log = started
    while True:
        state = (_extract_batch_state(batch) or '').upper()
        now = time.time()
        if now - last_log >= max(poll_interval_s, 5.0):
            waited = int(now - started)
            name_dbg = name or _extract_batch_name(batch) or 'UNKNOWN'
            print(f"[Gemini] Polling: state={state or 'UNKNOWN'} waited={waited}s name={name_dbg}", flush=True)
            last_log = now
        # Handle both simple and enum-like states (e.g., JOB_STATE_SUCCEEDED)
        if state in ('SUCCEEDED', 'COMPLETED') or state.endswith('_SUCCEEDED') or state.endswith('_COMPLETED'):
            break
        if state in ('FAILED', 'CANCELLED', 'CANCELED') or state.endswith('_FAILED') or state.endswith('_CANCELLED') or state.endswith('_CANCELED'):
            raise RuntimeError(f'Gemini Batch state={state}')
        if (now - started) > timeout_s:
            raise TimeoutError(f'Gemini Batch timeout after {timeout_s}s')
        time.sleep(poll_interval_s)
        # Refresh with retry/backoff
        if name:
            attempts = 0
            while True:
                try:
                    batch = client.batches.get(name=name)
                    break
                except Exception as ge:
                    attempts += 1
                    if attempts > 3:
                        raise RuntimeError(f"[Gemini] batches.get failed after retries: {ge}")
                    backoff = min(10.0, poll_interval_s * (attempts + 1))
                    print(f"[Gemini] batches.get retry {attempts} in {backoff:.1f}s due to: {ge}", flush=True)
                    time.sleep(backoff)
        else:
            print('[Gemini] Warning: cannot refresh batch status (no name).', flush=True)
            break

    # Retrieve results: file download or inline responses
    if not name:
        raise RuntimeError('Gemini Batch API: missing batch name for result retrieval')
    try:
        batch = client.batches.get(name=name)
    except Exception:
        pass

    dest = getattr(batch, 'dest', None)
    dest_d = None
    if dest is None and hasattr(batch, 'to_dict'):
        try:
            bd = batch.to_dict()
            if isinstance(bd, dict):
                dest_d = bd.get('dest') if isinstance(bd.get('dest'), dict) else None
        except Exception:
            dest_d = None
    file_name = getattr(dest, 'file_name', None) if dest is not None else None
    inlined_responses = getattr(dest, 'inlined_responses', None) if dest is not None else None
    if (file_name is None and inlined_responses is None) and dest_d is not None:
        file_name = dest_d.get('file_name')
        inlined_responses = dest_d.get('inlined_responses')

    lines: List[str] = []
    result_source = 'unknown'
    if file_name:
        print(f"[Gemini] Results are in file: {file_name}. Downloading via files API...", flush=True)
        dl_attempts = 0
        content_bytes = None
        while True:
            try:
                content_bytes = client.files.download(file=file_name)
                break
            except Exception as de:
                dl_attempts += 1
                if dl_attempts > 10:
                    raise RuntimeError(f"[Gemini] files.download failed after retries: {de}")
                backoff = min(60.0, 2.0 * dl_attempts)
                print(f"[Gemini] files.download retry {dl_attempts} in {backoff:.1f}s due to: {de}", flush=True)
                time.sleep(backoff)
        text = content_bytes.decode('utf-8', errors='ignore') if isinstance(content_bytes, (bytes, bytearray)) else str(content_bytes)
        lines = text.splitlines()
        result_source = 'file'
    elif inlined_responses is not None:
        print("[Gemini] Results are inline (dest.inlined_responses).", flush=True)
        result_source = 'inline'
        try:
            for idx, ir in enumerate(inlined_responses):
                resp = getattr(ir, 'response', None)
                err = getattr(ir, 'error', None)
                item: Dict[str, Any] = {'index': idx}
                if resp is not None:
                    txt = None
                    try:
                        txt = getattr(resp, 'text', None)
                    except Exception:
                        txt = None
                    if txt is None:
                        if hasattr(resp, 'to_dict'):
                            try:
                                item['response'] = resp.to_dict()
                            except Exception:
                                item['response'] = str(resp)
                        else:
                            item['response'] = str(resp)
                    else:
                        item['response'] = {'text': txt}
                elif err is not None:
                    try:
                        if hasattr(err, 'to_dict'):
                            item['error'] = err.to_dict()  # type: ignore[attr-defined]
                        else:
                            item['error'] = str(err)
                    except Exception:
                        item['error'] = str(err)
                else:
                    item['response'] = {'text': ''}
                lines.append(json.dumps(item, ensure_ascii=False))
        except Exception:
            for idx, ir in enumerate(inlined_responses):
                lines.append(json.dumps({'index': idx, 'response': str(ir)}, ensure_ascii=False))
    else:
        print("[Gemini] No results found in dest (neither file_name nor inlined_responses).", flush=True)
        lines = []
    print(f"[Gemini] Retrieved {len(lines)} result lines from {result_source}.", flush=True)

    # Parse lines into plain texts, preserving original request order via index metadata
    results_text: List[str] = []
    tmp_by_index: Dict[int, str] = {}
    error_count = 0
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            j = json.loads(line)
            txt = ''
            # Prefer explicit error payloads (service-level error per item)
            if isinstance(j, dict) and j.get('error') is not None:
                try:
                    txt = json.dumps(j['error'], ensure_ascii=False)
                except Exception:
                    txt = str(j['error'])
                error_count += 1
            # Extract index to maintain request order
            idx_val = None
            if isinstance(j, dict):
                for k in ('index', 'requestIndex', 'input_index', 'request_index'):
                    if k in j:
                        idx_val = j.get(k)
                        break
            # Extract response text if not error
            if isinstance(j, dict):
                # Primary: response.candidates[0].content.parts[*].text
                resp = j.get('response') if isinstance(j.get('response'), dict) else None
                if resp:
                    cand = resp.get('candidates')
                    if isinstance(cand, list) and cand:
                        content = cand[0].get('content') or {}
                        parts = content.get('parts') or []
                        if isinstance(parts, list):
                            for part in parts:
                                if isinstance(part, dict) and 'text' in part:
                                    txt = part['text']
                                    break
                    if not txt:
                        txt = resp.get('text') or ''
                if not txt:
                    txt = j.get('text') or j.get('output') or ''
            # Place into map or append if no index
            out_txt = txt if isinstance(txt, str) else json.dumps(txt, ensure_ascii=False)
            if idx_val is not None:
                try:
                    tmp_by_index[int(idx_val)] = out_txt
                except Exception:
                    results_text.append(out_txt)
            else:
                results_text.append(out_txt)
        except Exception:
            results_text.append(line)

    # Reconstruct results by original prompt order if indices were available
    if tmp_by_index:
        ordered = [tmp_by_index.get(i, '') for i in range(len(prompts))]
        results_text = ordered

    meta = {
        'batch_name': name,
        'state': _extract_batch_state(batch),
        'response_count': len(results_text),
        'error_count': error_count,
        'result_source': result_source,
    }
    # Align length with prompts
    if len(results_text) < len(prompts):
        results_text += [''] * (len(prompts) - len(results_text))
    elif len(results_text) > len(prompts):
        results_text = results_text[:len(prompts)]
    print(f"[Gemini] Parsed {len(results_text)} responses.", flush=True)
    return results_text, meta


# Note: No async fallback for Gemini; Batch API is mandatory per requirements.


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
                stem_val = r.get('stem') or r.get('question_prompt') or r.get('question.prompt') or r.get('question', '')
                cid_val = r.get('correctOptionId') or r.get('correct_option_id') or ''
                # If missing critical pieces, try reconstruct from gold
                if (not stem_val) or (not opts_obj) or (not cid_val):
                    rs, ropts, rcid = _reconstruct_mcq(r)
                    stem_val = stem_val or rs
                    if not opts_obj:
                        opts_obj = ropts
                    cid_val = cid_val or rcid
                user = json.dumps({
                    'stem': stem_val,
                    'options': opts_obj,
                    'correctOptionId': cid_val,
                    'topic': r.get('topic') or ''
                }, ensure_ascii=False)
                prompt = f"{MCQ_SYS}\n{user}"
            else:
                pr_val = r.get('question_prompt') or r.get('question.prompt') or r.get('prompt') or r.get('question', '')
                ans_val = r.get('answer') or r.get('gold_answer') or ''
                if (not pr_val) or (not ans_val):
                    rp, ra = _reconstruct_fill(r)
                    pr_val = pr_val or rp
                    ans_val = ans_val or ra
                user = json.dumps({
                    'prompt': pr_val,
                    'answer': ans_val,
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
                    # Reuse normalization + reconstruction
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
                    cid_val = r.get('correctOptionId') or r.get('correct_option_id') or ''
                    if (not stem_val) or (not opts_obj) or (not cid_val):
                        rs, ropts, rcid = _reconstruct_mcq(r)
                        stem_val = stem_val or rs
                        if not opts_obj:
                            opts_obj = ropts
                        cid_val = cid_val or rcid
                    ds = judge_mcq_deepseek(stem_val, opts_obj, cid_val, r.get('topic') or '', context=None)
                else:
                    pr_val = r.get('question_prompt') or r.get('question.prompt') or r.get('prompt') or r.get('question', '')
                    ans_val = r.get('answer') or r.get('gold_answer') or ''
                    if (not pr_val) or (not ans_val):
                        rp, ra = _reconstruct_fill(r)
                        pr_val = pr_val or rp
                        ans_val = ans_val or ra
                    ds = judge_fill_deepseek(pr_val, ans_val, r.get('topic') or '', context=None)
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
