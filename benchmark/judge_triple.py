from __future__ import annotations
import os
import json
import time
from typing import Any, Dict, List, Optional, Tuple

# Reuse existing judge system prompts and helpers
from .judge import MCQ_SYS, FILL_SYS, _parse_json_loose, judge_mcq_deepseek, judge_fill_deepseek


# ---------- Gemini Batch (google-genai) ----------
try:
    from google import genai  # type: ignore
    from google.genai import types  # type: ignore
except Exception:
    genai = None  # type: ignore
    types = None  # type: ignore


def _gemini_build_user_contents(prompt: str) -> List[Dict[str, Any]]:
    return [{"role": "user", "parts": [{"text": prompt}]}]


def _normalize_model_name(model: Any) -> str:
    if isinstance(model, (list, tuple)):
        model = model[0] if model else ''
    if isinstance(model, str) and model.strip().startswith('['):
        try:
            j = json.loads(model)
            if isinstance(j, list) and j:
                model = j[0]
        except Exception:
            pass
    model = (str(model or '')).strip()
    if not model:
        model = 'gemini-2.5-pro'
    if not model.startswith('models/'):
        model = f'models/{model}'
    return model


def gemini_batch_generate(prompts: List[str], *, model: Any = "gemini-2.5-pro", poll_interval_s: float = 3.0, timeout_s: float = 60*60) -> List[str]:
    """Strict Gemini Batch API call: enqueue -> poll -> retrieve. No fallback.
    Returns list of raw response texts aligned to prompts order.
    """
    if genai is None:
        raise RuntimeError("google-genai not installed")
    key = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
    if not key:
        raise RuntimeError("GEMINI/GOOGLE API key not set")
    client = genai.Client(api_key=key)
    if not hasattr(client, 'batches') or not hasattr(client.batches, 'create'):
        raise RuntimeError('Installed google-genai SDK does not expose Batch API (client.batches.create)')

    # Build per-request configs (temperature 0, JSON MIME) using types.GenerateContentConfig
    if types is None:
        raise RuntimeError("google-genai types module not available; update google-genai SDK")
    req_cfg = types.GenerateContentConfig(
        response_mime_type="application/json",
        temperature=0,
        top_p=0,
    )
    reqs = [
        {
            "contents": _gemini_build_user_contents(p),
            "config": req_cfg,
        }
        for p in prompts
    ]
    model = _normalize_model_name(model)
    # Create batch: prefer inline 'requests='; fall back to 'src=' for older SDKs
    print(f"[Gemini] Submitting batch of {len(prompts)} prompts to model '{model}'", flush=True)
    try:
        batch = client.batches.create(model=model, requests=reqs)
    except Exception:
        # Some SDKs require 'src=' and expect a GCS URI or inline payload; try src=reqs
        batch = client.batches.create(model=model, src=reqs)
    name = getattr(batch, 'name', None) or getattr(batch, 'id', None)
    if not name:
        raise RuntimeError('Gemini Batch missing name/id')
    print(f"[Gemini] Batch submitted. name={name}", flush=True)
    t0 = time.time()
    while True:
        b = client.batches.get(name=name)
        state = (getattr(b, 'state', None) or getattr(b, 'status', None) or '').upper()
        waited = int(time.time() - t0)
        print(f"[Gemini] Polling: state={state or 'UNKNOWN'} waited={waited}s", flush=True)
        if state in ('SUCCEEDED','COMPLETED') or state.endswith('_SUCCEEDED') or state.endswith('_COMPLETED'):
            break
        if state in ('FAILED','CANCELLED','CANCELED') or state.endswith('_FAILED') or state.endswith('_CANCELLED') or state.endswith('_CANCELED'):
            raise RuntimeError(f'Gemini Batch failed: state={state}')
        if (time.time() - t0) > timeout_s:
            raise TimeoutError('Gemini Batch timeout')
        time.sleep(poll_interval_s)

    # Retrieve results; prefer inline_output.inline_responses (SDK variant: inlineOutput.inline_responses)
    b = client.batches.get(name=name)
    print("[Gemini] Batch finished. Retrieving results...", flush=True)
    out: List[str] = [''] * len(prompts)

    inline_output = getattr(b, 'inline_output', None) or getattr(b, 'inlineOutput', None)
    if inline_output is not None:
        inline_res = getattr(inline_output, 'inline_responses', None)
        if inline_res is None:
            inline_res = getattr(inline_output, 'inlineResponses', None)
        if inline_res is not None:
            for idx, ir in enumerate(inline_res):
                resp = getattr(ir, 'response', None)
                err = getattr(ir, 'error', None)
                txt = ''
                if resp is not None:
                    # Try direct text; else candidates[0].content.parts[*].text
                    txt = getattr(resp, 'text', None) or ''
                    if not txt and hasattr(resp, 'to_dict'):
                        rd = resp.to_dict()
                        cand = rd.get('candidates')
                        if isinstance(cand, list) and cand:
                            content = cand[0].get('content') or {}
                            parts = content.get('parts') or []
                            if isinstance(parts, list):
                                for part in parts:
                                    if isinstance(part, dict) and 'text' in part:
                                        txt = part['text']
                                        break
                elif err is not None:
                    txt = json.dumps(err.to_dict() if hasattr(err, 'to_dict') else str(err), ensure_ascii=False)
                if idx < len(out):
                    out[idx] = txt or ''
            print(f"[Gemini] Retrieved {len(out)} inline responses.", flush=True)
            return out

    # Fallback: some SDKs expose dest.file_name or dest.inlined_responses
    dest = getattr(b, 'dest', None)
    file_name = getattr(dest, 'file_name', None) if dest is not None else None
    inlined = getattr(dest, 'inlined_responses', None) if dest is not None else None
    if file_name:
        content_bytes = client.files.download(file=file_name)
        text = content_bytes.decode('utf-8', errors='ignore') if isinstance(content_bytes, (bytes, bytearray)) else str(content_bytes)
        lines = text.splitlines()
        for i, line in enumerate(lines):
            try:
                j = json.loads(line)
            except Exception:
                continue
            # Try to map by index
            idx_val = None
            if isinstance(j, dict):
                for k in ('index','requestIndex','input_index','request_index'):
                    if k in j:
                        try:
                            idx_val = int(j[k])
                            break
                        except Exception:
                            pass
                if idx_val is None:
                    idx_val = i
                # Extract text
                txt = ''
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
                    txt = j.get('text') or ''
                if 0 <= idx_val < len(out):
                    out[idx_val] = txt or ''
        print(f"[Gemini] Retrieved {len(out)} responses from file.", flush=True)
        return out
    elif inlined is not None:
        for idx, ir in enumerate(inlined):
            resp = getattr(ir, 'response', None)
            err = getattr(ir, 'error', None)
            txt = ''
            if resp is not None:
                txt = getattr(resp, 'text', None) or ''
                if not txt and hasattr(resp, 'to_dict'):
                    rd = resp.to_dict()
                    cand = rd.get('candidates')
                    if isinstance(cand, list) and cand:
                        content = cand[0].get('content') or {}
                        parts = content.get('parts') or []
                        if isinstance(parts, list):
                            for part in parts:
                                if isinstance(part, dict) and 'text' in part:
                                    txt = part['text']
                                    break
            elif err is not None:
                txt = json.dumps(err.to_dict() if hasattr(err, 'to_dict') else str(err), ensure_ascii=False)
            if idx < len(out):
                out[idx] = txt or ''
        print(f"[Gemini] Retrieved {len(out)} inlined_responses from dest.", flush=True)
        return out

    # Nothing found; return blanks
    return out


# ---------- Claude Batch (anthropic) ----------
try:
    from anthropic import Anthropic  # type: ignore
except Exception:
    Anthropic = None  # type: ignore


def claude_batch_generate(prompts: List[str], *, model: str = 'claude-haiku-4-5', poll_interval_s: float = 2.0, timeout_s: float = 60*60) -> List[str]:
    """Anthropic messages.batches flow. No fallback. Align results by custom_id."""
    if Anthropic is None:
        raise RuntimeError('anthropic SDK not installed: pip install anthropic')
    key = os.getenv('ANTHROPIC_API_KEY') or os.getenv('CLAUDE_API_KEY')
    if not key:
        raise RuntimeError('ANTHROPIC_API_KEY/CLAUDE_API_KEY not set')
    client = Anthropic(api_key=key)

    # 1) create batch
    requests = [
        {
            "custom_id": f"req-{i}",
            "params": {
                "model": model,
                "max_tokens": 1024,
                "temperature": 0,
                "messages": [{"role": "user", "content": p}],
            },
        }
        for i, p in enumerate(prompts)
    ]
    print(f"[Claude] Submitting batch of {len(prompts)} prompts to model '{model}'", flush=True)
    resp = client.messages.batches.create(requests=requests)
    batch_id = getattr(resp, 'id', None)
    if not batch_id:
        raise RuntimeError('Claude batch: missing id')
    print(f"[Claude] Batch submitted. id={batch_id}", flush=True)
    # 2) poll
    t0 = time.time()
    while True:
        b = client.messages.batches.retrieve(batch_id)
        status = getattr(b, 'processing_status', None) or getattr(b, 'status', None)
        counts = getattr(b, 'request_counts', None)
        waited = int(time.time() - t0)
        print(f"[Claude] Polling: status={status} waited={waited}s counts={counts}", flush=True)
        if status == 'ended':
            break
        if (time.time() - t0) > timeout_s:
            raise TimeoutError('Claude batch timeout')
        time.sleep(poll_interval_s)

    # 3) results
    out_by_id: Dict[str, str] = {}
    total = 0
    for entry in client.messages.batches.results(batch_id):
        cid = getattr(entry, 'custom_id', None)
        result = getattr(entry, 'result', None)
        if not cid:
            continue
        if hasattr(result, 'type') and getattr(result, 'type') == 'succeeded':
            msg = getattr(result, 'message', None)
            text = ''
            if msg is not None:
                content = getattr(msg, 'content', [])
                if isinstance(content, list):
                    for c in content:
                        if getattr(c, 'type', None) == 'text':
                            text += getattr(c, 'text', '')
            out_by_id[cid] = text
        else:
            out_by_id[cid] = json.dumps(result, ensure_ascii=False)
        total += 1
    print(f"[Claude] Retrieved {total} results.", flush=True)

    # align to original order by req-i
    out: List[str] = []
    for i in range(len(prompts)):
        out.append(out_by_id.get(f'req-{i}', ''))
    return out


# ---------- Prompt builders & triple judge orchestrators ----------
def _norm_options(options_any: Any) -> Dict[str, str]:
    """Normalize options into {id: label} dict."""
    if options_any is None:
        return {}
    if isinstance(options_any, dict):
        # string labels
        return {str(k): (v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)) for k, v in options_any.items()}
    if isinstance(options_any, list):
        letters = 'abcdefghijklmnopqrstuvwxyz'
        return {letters[i]: (o.get('label') if isinstance(o, dict) else str(o)) for i, o in enumerate(options_any) if i < len(letters)}
    return {}


def _build_prompt_mcq(stem: str, options: Dict[str, str], correct_id: str, topic: str) -> str:
    user = json.dumps({
        'stem': stem,
        'options': options,
        'correctOptionId': correct_id,
        'topic': topic,
    }, ensure_ascii=False)
    return f"{MCQ_SYS}\n{user}"


def _build_prompt_fill(prompt: str, answer: str, topic: str) -> str:
    user = json.dumps({
        'prompt': prompt,
        'answer': answer,
        'topic': topic,
    }, ensure_ascii=False)
    return f"{FILL_SYS}\n{user}"


def judge_triple_batch_mcq(items: List[Dict[str, Any]], *, topic: str) -> List[Dict[str, Any]]:
    """Batch-judge MCQ items using Gemini (batch), Claude (batch), and DeepSeek (per-item).
    Each item: expects question.prompt, question.options(list[{id,label}] or dict), correctOptionId.
    Returns list of dicts with keys: gemini_verdict, gemini_why, claude_verdict, claude_why, deepseek_verdict, deepseek_why.
    """
    prompts: List[str] = []
    stems: List[str] = []
    options_list: List[Dict[str, str]] = []
    correct_ids: List[str] = []
    for it in items:
        q = it.get('question', {})
        stem = q.get('prompt') or it.get('stem') or ''
        opts = _norm_options(q.get('options'))
        cid = it.get('correctOptionId') or ''
        stems.append(stem)
        options_list.append(opts)
        correct_ids.append(cid)
        prompts.append(_build_prompt_mcq(stem, opts, cid, topic))

    # Gemini & Claude batch
    gem_txts = gemini_batch_generate(prompts, model=os.getenv('JUDGE_MODEL') or 'gemini-2.5-pro')
    cla_txts = claude_batch_generate(prompts, model=os.getenv('CLAUDE_MODEL') or 'claude-haiku-4-5')

    out: List[Dict[str, Any]] = []
    for i in range(len(items)):
        # Parse batch outputs
        try:
            g = _parse_json_loose(gem_txts[i] or '')
        except Exception:
            g = {'verdict': 'error', 'why': (gem_txts[i] or '')[:200]}
        try:
            c = _parse_json_loose(cla_txts[i] or '')
        except Exception:
            c = {'verdict': 'error', 'why': (cla_txts[i] or '')[:200]}
        # DeepSeek per item (no batch API yet)
        try:
            d = judge_mcq_deepseek(stems[i], options_list[i], correct_ids[i], topic, context=None)
        except Exception as e:
            d = {'verdict': 'error', 'why': str(e)}
        out.append({
            'gemini_verdict': str(g.get('verdict', '')).lower(),
            'gemini_why': g.get('why', ''),
            'claude_verdict': str(c.get('verdict', '')).lower(),
            'claude_why': c.get('why', ''),
            'deepseek_verdict': str(d.get('verdict', '')).lower(),
            'deepseek_why': d.get('why', ''),
        })
    return out


def judge_triple_batch_fill(items: List[Dict[str, Any]], *, topic: str) -> List[Dict[str, Any]]:
    prompts: List[str] = []
    stems: List[str] = []
    answers: List[str] = []
    for it in items:
        q = it.get('question', {})
        prompt = q.get('prompt') or it.get('prompt') or ''
        ans = it.get('answer') or ''
        stems.append(prompt)
        answers.append(ans)
        prompts.append(_build_prompt_fill(prompt, ans, topic))

    gem_txts = gemini_batch_generate(prompts, model=os.getenv('JUDGE_MODEL') or 'gemini-2.5-pro')
    cla_txts = claude_batch_generate(prompts, model=os.getenv('CLAUDE_MODEL') or 'claude-haiku-4-5')

    out: List[Dict[str, Any]] = []
    for i in range(len(items)):
        try:
            g = _parse_json_loose(gem_txts[i] or '')
        except Exception:
            g = {'verdict': 'error', 'why': (gem_txts[i] or '')[:200]}
        try:
            c = _parse_json_loose(cla_txts[i] or '')
        except Exception:
            c = {'verdict': 'error', 'why': (cla_txts[i] or '')[:200]}
        try:
            d = judge_fill_deepseek(stems[i], answers[i], topic, context=None)
        except Exception as e:
            d = {'verdict': 'error', 'why': str(e)}
        out.append({
            'gemini_verdict': str(g.get('verdict', '')).lower(),
            'gemini_why': g.get('why', ''),
            'claude_verdict': str(c.get('verdict', '')).lower(),
            'claude_why': c.get('why', ''),
            'deepseek_verdict': str(d.get('verdict', '')).lower(),
            'deepseek_why': d.get('why', ''),
        })
    return out
