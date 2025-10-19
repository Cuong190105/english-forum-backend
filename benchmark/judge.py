from __future__ import annotations
import os
import json
from typing import Dict, Any

try:
    from google import genai
    from google.genai.types import GenerateContentConfig
except Exception:
    genai = None
    GenerateContentConfig = None

# Load .env so GOOGLE_API_KEY/GEMINI_API_KEY is available
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass


MCQ_SYS = 'Trả JSON: { "verdict": "correct|ambiguous|incorrect", "why": "<vi-vn>" }\nĐánh giá chuẩn EFL, nghiêm ngặt, không sinh thêm.'
FILL_SYS = 'Trả JSON: { "verdict": "acceptable|unacceptable", "why": "<vi-vn>" }\nĐánh giá chuẩn EFL, nghiêm ngặt, không sinh thêm.'


def _client():
    key = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
    if not key:
        raise RuntimeError('GEMINI_API_KEY/GOOGLE_API_KEY not set')
    if genai is None:
        raise RuntimeError('google-genai not installed')
    # Cache the client per process for reuse
    global _CACHED_CLIENT, _CACHED_KEY
    try:
        _CACHED_CLIENT
    except NameError:
        _CACHED_CLIENT = None  # type: ignore[assignment]
        _CACHED_KEY = None  # type: ignore[assignment]
    if _CACHED_CLIENT is None or _CACHED_KEY != key:
        _CACHED_CLIENT = genai.Client(api_key=key)  # type: ignore[assignment]
        _CACHED_KEY = key  # type: ignore[assignment]
    return _CACHED_CLIENT  # type: ignore[return-value]


def judge_mcq(stem: str, options: Dict[str, str], correct_id: str, topic: str) -> Dict[str, Any]:
    c = _client()
    user = json.dumps({
        'stem': stem,
        'options': options,
        'correctOptionId': correct_id,
        'topic': topic,
    }, ensure_ascii=False)
    cfg = GenerateContentConfig(response_mime_type='application/json', temperature=0.0, top_p=0.0)
    resp = c.models.generate_content(model=os.getenv('JUDGE_MODEL') or 'gemini-2.5-pro', contents=f"{MCQ_SYS}\n{user}", config=cfg)
    txt = getattr(resp, 'text', None) or json.dumps(getattr(resp, 'parsed', {}), ensure_ascii=False)
    try:
        return json.loads(txt)
    except Exception:
        # Retry strictly
        resp2 = c.models.generate_content(model=os.getenv('JUDGE_MODEL') or 'gemini-2.5-pro', contents=f"{MCQ_SYS}\nONLY JSON. DO NOT WRITE ANYTHING ELSE.\n{user}", config=cfg)
        txt2 = getattr(resp2, 'text', None) or json.dumps(getattr(resp2, 'parsed', {}), ensure_ascii=False)
        return json.loads(txt2)


def judge_fill(prompt: str, answer: str, topic: str) -> Dict[str, Any]:
    c = _client()
    user = json.dumps({
        'prompt': prompt,
        'answer': answer,
        'topic': topic,
    }, ensure_ascii=False)
    cfg = GenerateContentConfig(response_mime_type='application/json', temperature=0.0, top_p=0.0)
    resp = c.models.generate_content(model=os.getenv('JUDGE_MODEL') or 'gemini-2.5-pro', contents=f"{FILL_SYS}\n{user}", config=cfg)
    txt = getattr(resp, 'text', None) or json.dumps(getattr(resp, 'parsed', {}), ensure_ascii=False)
    try:
        return json.loads(txt)
    except Exception:
        resp2 = c.models.generate_content(model=os.getenv('JUDGE_MODEL') or 'gemini-2.5-pro', contents=f"{FILL_SYS}\nONLY JSON. DO NOT WRITE ANYTHING ELSE.\n{user}", config=cfg)
        txt2 = getattr(resp2, 'text', None) or json.dumps(getattr(resp2, 'parsed', {}), ensure_ascii=False)
        return json.loads(txt2)
