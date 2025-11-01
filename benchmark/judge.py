from __future__ import annotations
import os
import json
from typing import Dict, Any, List
import re
import time

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


MCQ_SYS = (
    'Trả JSON: { "verdict": "correct|ambiguous|incorrect", "why": "<vi-vn>" }\n'
    'Vai trò: Giám khảo EFL (nghiêm ngặt vừa phải). Chỉ sử dụng stem và options; KHÔNG dùng kiến thức ngoài.\n'
    'Quy trình ra quyết định (ưu tiên tính chặt chẽ cho AMBIGUOUS):\n'
    '1) Trích xuất ràng buộc từ stem (ngữ pháp, nghĩa, dấu hiệu loại trừ).\n'
    '2) Đánh giá từng option theo ràng buộc: phân loại "phù hợp rõ ràng" vs "có thể chấp nhận" vs "loại".\n'
    '3) Nếu đúng 1 option "phù hợp rõ ràng" và các option khác bị "loại" → verdict=correct.\n'
    '4) Nếu 0 option "phù hợp rõ ràng" HOẶC có ≥2 option ở mức "có thể chấp nhận" nhưng thiếu bằng chứng để loại trừ → verdict=ambiguous.\n'
    '5) Nếu đáp án gán-đúng bị bác bỏ theo stem hoặc có option khác đúng/ tốt ngang làm mất tính duy nhất → verdict=incorrect.\n'
    'Khi nào nên AMBIGUOUS (các tình huống thường gặp):\n'
    '- Stem thiếu thông tin quyết định (phải dựa kiến thức ngoài).\n'
    '- Nhiều option đồng nghĩa/paraphrase thỏa ràng buộc như nhau, không có tín hiệu tách bạch.\n'
    '- Tham chiếu/khung thời gian/tiêu điểm ngữ nghĩa không đủ rõ trong stem.\n'
    '- Lỗi hình thức MCQ (trùng/thiếu option, mô tả chồng lấn) khiến không thể loại trừ.\n'
    'Xuất kết quả:\n'
    '- Chỉ {verdict, why}. why 1–2 câu, nêu ràng buộc trong stem và option liên quan (nhắc ID option nếu cần).\n'
    '- Không đoán: nếu chưa thể loại trừ hoàn toàn → chọn ambiguous và giải thích vì sao.'
)
FILL_SYS = (
    'Trả JSON: { "verdict": "acceptable|unacceptable", "why": "<vi-vn>" }\n'
    'Vai trò: Giám khảo EFL (nghiêm ngặt vừa phải). Chỉ sử dụng stem và answer; KHÔNG dùng kiến thức ngoài.\n'
    'Tiêu chí:\n'
    '- acceptable: Đáp án khớp ngữ pháp và ý nghĩa mục tiêu theo stem (chấp nhận biến thể nhỏ như viết hoa/chấm câu; ghi rõ nếu chấp nhận).\n'
    '- unacceptable: Sai ngữ pháp/ý hoặc không đáp ứng ràng buộc cần thiết (thì, hòa hợp chủ-vị, cấu trúc).\n'
    'Đầu ra: Chỉ {verdict, why}; why ngắn gọn 1–2 câu, bám sát stem/answer.'
)


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


def judge_mcq(stem: str, options: Dict[str, str], correct_id: str, topic: str, context: str | None = None) -> Dict[str, Any]:
    c = _client()
    user = json.dumps({
        'stem': stem,
        'options': options,
        'correctOptionId': correct_id,
        'topic': topic,
        **({'context': context} if context else {}),
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


def judge_fill(prompt: str, answer: str, topic: str, context: str | None = None) -> Dict[str, Any]:
    c = _client()
    user = json.dumps({
        'prompt': prompt,
        'answer': answer,
        'topic': topic,
        **({'context': context} if context else {}),
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


# ---- Optional second judge via DeepSeek native API ----
def _deepseek_client():
    """Create OpenAI-compatible client for DeepSeek native endpoint.
    Requires DEEPSEEK_API_KEY. Base URL defaults to https://api.deepseek.com
    """
    try:
        from openai import OpenAI  # type: ignore
        import httpx  # type: ignore
    except Exception:
        return None
    key = os.getenv('DEEPSEEK_API_KEY')
    if not key:
        return None
    base = os.getenv('DEEPSEEK_BASE_URL') or 'https://api.deepseek.com'
    # Create httpx client with simple timeout config
    http_client = httpx.Client(timeout=60.0)
    return OpenAI(base_url=base, api_key=key, http_client=http_client)


def _parse_json_loose(text: str) -> Dict[str, Any]:
    """Parse a JSON object from a noisy LLM output.
    Strategy:
    - direct json.loads
    - strip markdown code fences ```...```
    - extract all balanced JSON objects and pick the one containing a 'verdict' key
    - heuristic fallback based on keywords
    """
    # 1) direct
    try:
        j = json.loads(text)
        if isinstance(j, dict):
            return j
    except Exception:
        pass

    s = str(text)
    # 2) remove code fences while preserving inner content
    try:
        s = re.sub(r"```[a-zA-Z]*\n([\s\S]*?)```", r"\1", s)
    except Exception:
        pass
    # quick retry
    try:
        j = json.loads(s)
        if isinstance(j, dict):
            return j
    except Exception:
        pass

    # 3) collect balanced {...} candidates
    candidates: List[Dict[str, Any]] = []
    buf = []
    depth = 0
    for ch in s:
        if ch == '{':
            depth += 1
        if depth > 0:
            buf.append(ch)
        if ch == '}':
            depth -= 1
            if depth == 0 and buf:
                cand_str = ''.join(buf)
                buf = []
                try:
                    cand = json.loads(cand_str)
                    if isinstance(cand, dict):
                        candidates.append(cand)
                except Exception:
                    # ignore
                    pass
    # prefer one with 'verdict' key
    for cand in candidates:
        if 'verdict' in cand:
            return cand
    # else return the last parsed dict if any
    if candidates:
        return candidates[-1]

    # 4) heuristic keyword fallback
    low = s.lower()
    if any(w in low for w in ['"verdict"\s*:\s*"correct', ' verdict": "correct', ' correct"']):
        return {"verdict": "correct", "why": s}
    if any(w in low for w in ['ambiguous','unclear','both could']):
        return {"verdict": "ambiguous", "why": s}
    if any(w in low for w in ['incorrect','wrong','not correct']):
        return {"verdict": "incorrect", "why": s}
    raise ValueError("Could not parse JSON from model output")


def _log_j2(msg: str) -> None:
    """Append a one-line log to the path in $JUDGE2_CALL_LOG if set."""
    path = os.getenv('JUDGE2_CALL_LOG')
    if not path:
        return
    try:
        ts = time.strftime('%Y-%m-%d %H:%M:%S')
        with open(path, 'a', encoding='utf-8') as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass


def judge_mcq_deepseek(stem: str, options: Dict[str, str], correct_id: str, topic: str, context: str | None = None) -> Dict[str, Any]:
    client = _deepseek_client()
    if client is None:
        raise RuntimeError('DeepSeek client not available or DEEPSEEK_API_KEY missing')
    sys_msg = MCQ_SYS
    user = json.dumps({
        'stem': stem,
        'options': options,
        'correctOptionId': correct_id,
        'topic': topic,
        **({'context': context} if context else {}),
    }, ensure_ascii=False)
    model = os.getenv('JUDGE2_MODEL') or 'deepseek-reasoner'
    try:
        _log_j2(f"CALL mcq model={model} topic={topic} len_stem={len(stem)} n_opts={len(options)} has_ctx={1 if context else 0}")
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role":"system","content": sys_msg}, {"role":"user","content": user}],
            temperature=0,
        )
        content = resp.choices[0].message.content  # type: ignore[index]
        _log_j2(f"OK mcq id={getattr(resp,'id','')} content_len={len(content or '')}")
        return _parse_json_loose(content or "")
    except Exception:
        # Retry once with stricter instruction
        strict = MCQ_SYS + "\nONLY JSON. DO NOT WRITE ANYTHING ELSE. Keys: verdict, why."
        _log_j2("RETRY mcq strict-json")
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role":"system","content": strict}, {"role":"user","content": user}],
            temperature=0,
        )
        content = resp.choices[0].message.content  # type: ignore[index]
        _log_j2(f"OK mcq(strict) id={getattr(resp,'id','')} content_len={len(content or '')}")
        return _parse_json_loose(content or "")


def judge_fill_deepseek(prompt: str, answer: str, topic: str, context: str | None = None) -> Dict[str, Any]:
    client = _deepseek_client()
    if client is None:
        raise RuntimeError('DeepSeek client not available or DEEPSEEK_API_KEY missing')
    sys_msg = FILL_SYS
    user = json.dumps({
        'prompt': prompt,
        'answer': answer,
        'topic': topic,
        **({'context': context} if context else {}),
    }, ensure_ascii=False)
    model = os.getenv('JUDGE2_MODEL') or 'deepseek-reasoner'
    try:
        _log_j2(f"CALL fill model={model} topic={topic} len_prompt={len(prompt)} len_answer={len(answer)} has_ctx={1 if context else 0}")
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role":"system","content": sys_msg}, {"role":"user","content": user}],
            temperature=0,
        )
        content = resp.choices[0].message.content  # type: ignore[index]
        _log_j2(f"OK fill id={getattr(resp,'id','')} content_len={len(content or '')}")
        return _parse_json_loose(content or "")
    except Exception:
        strict = FILL_SYS + "\nONLY JSON. DO NOT WRITE ANYTHING ELSE. Keys: verdict, why."
        _log_j2("RETRY fill strict-json")
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role":"system","content": strict}, {"role":"user","content": user}],
            temperature=0,
        )
        content = resp.choices[0].message.content  # type: ignore[index]
        _log_j2(f"OK fill(strict) id={getattr(resp,'id','')} content_len={len(content or '')}")
        return _parse_json_loose(content or "")


def _judges_enabled() -> List[str]:
    # env JUDGES accepts comma list: gemini,deepseek
    s = (os.getenv('JUDGES') or 'gemini,deepseek').lower()
    out: List[str] = []
    for p in [x.strip() for x in s.split(',') if x.strip()]:
        if p in {'gemini', 'deepseek'}:
            out.append(p)
    return out or ['gemini']


def run_judges_mcq(stem: str, options: Dict[str, str], correct_id: str, topic: str, context: str | None = None) -> List[Dict[str, Any]]:
    res: List[Dict[str, Any]] = []
    for j in _judges_enabled():
        try:
            if j == 'gemini':
                r = judge_mcq(stem, options, correct_id, topic, context=context)
            elif j == 'deepseek':
                r = judge_mcq_deepseek(stem, options, correct_id, topic, context=context)
            else:
                continue
            res.append({'name': j, **r})
        except Exception as e:
            res.append({'name': j, 'verdict': 'error', 'why': str(e)})
    return res


def run_judges_fill(prompt: str, answer: str, topic: str, context: str | None = None) -> List[Dict[str, Any]]:
    res: List[Dict[str, Any]] = []
    for j in _judges_enabled():
        try:
            if j == 'gemini':
                r = judge_fill(prompt, answer, topic, context=context)
            elif j == 'deepseek':
                r = judge_fill_deepseek(prompt, answer, topic, context=context)
            else:
                continue
            res.append({'name': j, **r})
        except Exception as e:
            res.append({'name': j, 'verdict': 'error', 'why': str(e)})
    return res
