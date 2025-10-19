from __future__ import annotations
import os
import json
import re
from typing import List, Dict, Any, Optional, Literal

# --- SDK imports ---
try:
    # Modern Google GenAI SDK
    from google import genai
    from google.genai.types import GenerateContentConfig
except Exception:
    genai = None
    GenerateContentConfig = None  

from pydantic import BaseModel, RootModel, ValidationError

from dotenv import load_dotenv
load_dotenv()

DEBUG = os.getenv('DEBUG_AI', '') == '1'

# Module-level cached client
_GENAI_CLIENT = None
_GENAI_KEY = None

def _get_client():
    global _GENAI_CLIENT, _GENAI_KEY
    key = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
    if not key:
        raise RuntimeError('GOOGLE_API_KEY or GEMINI_API_KEY is not set in environment')
    if genai is None or GenerateContentConfig is None:
        raise RuntimeError('Google GenAI SDK not installed. Install: pip install google-genai')
    if _GENAI_CLIENT is None or _GENAI_KEY != key:
        _GENAI_CLIENT = genai.Client(api_key=key)
        _GENAI_KEY = key
    return _GENAI_CLIENT
# =========================
# Prompt builders (public helper)
# =========================
def build_locked_prompt_cot(hw_type: str, locked_topic: str, post_text: str, num_items: int) -> str:
    # 1) Topic-specific rule snippets (choose by locked_topic, fallback generic)
    topic_rules_map = {
        # Articles
        "a/an/the/zero": """
TOPIC-SPECIFIC RULES — Articles
- Stem phải có cue về tính xác định/duy nhất/đã biết HOẶC tính khái quát để phân biệt 'the' vs a/an/zero.
- Ít nhất 1 cue bắt buộc: uniqueness (“the only/first/best”), prior mention (“the … we discussed”), of-phrase (“the price of …”), generic/plural/uncountable cho zero article.
- Tránh stem mà cả 'a' và 'the' đều có thể chấp nhận.
""",
    # Present Perfect vs Past Simple
    "present perfect": """
TOPIC-SPECIFIC RULES — Present Perfect vs Past Simple
- Nếu dùng time marker cụ thể (yesterday, in 2020, last week) → Past Simple.
- Nếu là trải nghiệm/ảnh hưởng đến hiện tại/unfinished time (today, this week) → Present Perfect.
- Thêm cue thời gian rõ ràng để loại trừ đáp án còn lại.
""",
        # Relative clauses
        "Defining vs Non-defining": """
TOPIC-SPECIFIC RULES — Relative Clauses
- Dùng dấu phẩy cho non-defining; không dấu phẩy cho defining.
- Ép đáp án duy nhất bằng: preposition fronting (“to whom …”), superlatives/only/all (ưu tiên 'that'), hoặc comma-rule (non-defining dùng which/who; không dùng 'that' sau dấu phẩy).
""",
        # Reported speech
        "Backshifting tenses": """
TOPIC-SPECIFIC RULES — Reported Speech / Backshifting
- Reporting verb ở quá khứ ⇒ bắt buộc lùi thì.
- Bổ sung chuyển đổi chỉ thời gian/đại từ (today→that day, here→there, now→then) để loại đáp án hiện tại/không lùi thì.
- Không dùng ngoại lệ “still true” trong benchmark.
""",
        # Present Simple (habit/fact)
        "Present Simple": """
TOPIC-SPECIFIC RULES — Present Simple
- Thêm cue thói quen/sự thật (every day, usually, always, generally; facts/laws).
- Tránh cue “specific past time” làm nhiễu với Past Simple.
""",
        # Comparatives (less/fewer/more)
        "less/fewer/more/most": """
TOPIC-SPECIFIC RULES — Comparatives/Superlatives
- BẮT BUỘC baseline 'than …' và định hướng (increase/decrease) để chỉ còn 1 đáp án đúng (fewer/less/more).
- Superlatives cần phạm vi: “in the class/of all/among …”.
""",
    # Passive Voice (synonyms)
    "passive": """
TOPIC-SPECIFIC RULES — Passive Voice
- Thêm cue bắt buộc thể bị động: by-phrase, focus on process/result, unknown agent.
- Ép thì bằng time marker hoặc state result vs ongoing process.
- Với modals: must/should/can + be + V3; thêm nghĩa bắt buộc/khả năng để loại chủ động.
""",
    "Passive (all tenses)": """
TOPIC-SPECIFIC RULES — Passive Voice
- Thêm cue bắt buộc thể bị động: by-phrase, focus on process/result, unknown agent.
- Ép thì bằng time marker hoặc state result vs ongoing process.
- Với modals: must/should/can + be + V3; thêm nghĩa bắt buộc/khả năng để loại chủ động.
""",
    "Passive with modals": """
TOPIC-SPECIFIC RULES — Passive Voice
- Thêm cue bắt buộc thể bị động: by-phrase, focus on process/result, unknown agent.
- Ép thì bằng time marker hoặc state result vs ongoing process.
- Với modals: must/should/can + be + V3; thêm nghĩa bắt buộc/khả năng để loại chủ động.
""",
    # Causative
    "causative have/get": """
TOPIC-SPECIFIC RULES — Causative (have/get sth done)
- Bắt buộc có cấu trúc gây khiến (have/get + object + V3) và bối cảnh thuê/dịch vụ.
- Thêm từ khóa dịch vụ (repair, cut, clean, install) để loại cấu trúc chủ động tự làm.
""",
    "Causative: have/get something done": """
TOPIC-SPECIFIC RULES — Causative (have/get sth done)
- Bắt buộc có cấu trúc gây khiến (have/get + object + V3) và bối cảnh thuê/dịch vụ.
- Thêm từ khóa dịch vụ (repair, cut, clean, install) để loại cấu trúc chủ động tự làm.
""",
    # Conditionals
    "zero conditional": """
TOPIC-SPECIFIC RULES — Zero Conditional
- Khái quát sự thật/quy luật; dùng Present Simple ở cả 2 vế.
- Thêm cue “always/usually/whenever/if + S + V (present), S + V (present)”.
""",
    "first conditional": """
TOPIC-SPECIFIC RULES — First Conditional
- Dự đoán tương lai thực tế; If-clause: Present Simple; main clause: will/might/can + V.
- Thêm hậu quả cụ thể “tomorrow/next week/this evening” để loại 2nd/3rd.
""",
    "second conditional": """
TOPIC-SPECIFIC RULES — Second Conditional
- Tình huống giả định hiện tại/khó xảy ra; If: past simple; main: would + V.
- Thêm cue “if I were you / unlikely / hypothetical” để loại 1st/3rd.
""",
    "third conditional": """
TOPIC-SPECIFIC RULES — Third Conditional
- Quá khứ không có thật; If: had + V3; main: would have + V3; thêm marker “yesterday / last year / in 2010”.
""",
    "mixed conditional": """
TOPIC-SPECIFIC RULES — Mixed Conditional
- If (past perfect) → result (would + V) hiện tại; hoặc If (past simple) → result (would have + V3) quá khứ.
- Thêm cue kết quả-hiện tại hoặc nguyên nhân-quá khứ để ép dạng mixed.
""",
    # Modals bundles
    "must/have to": """
TOPIC-SPECIFIC RULES — Modals (obligation)
- Đặt cue nghĩa bắt buộc (policy, requirement), phân biệt 'must' (speaker obligation) vs 'have to' (external rule).
- Với quá khứ: had to + V (không dùng musted).
""",
    "may/might/could": """
TOPIC-SPECIFIC RULES — Modals (possibility)
- Thêm cue xác suất (probably/possibly/uncertain). Công thức quá khứ: may/might/could have + V3.
""",
    "should/ought to": """
TOPIC-SPECIFIC RULES — Modals (advice)
- Bối cảnh khuyên nhủ/đánh giá; tránh để “must/have to” cũng hợp nghĩa bắt buộc.
""",
    # Gerunds / Infinitives
    "v-ing vs to-v": """
TOPIC-SPECIFIC RULES — Gerunds & Infinitives
- Ép chọn theo verb pattern: enjoy/avoid/mind + V-ing; decide/plan/hope + to-V.
- Thêm cue mục đích (to-V) vs hoạt động chung (V-ing).
""",
    "V-ing vs to-V": """
TOPIC-SPECIFIC RULES — Gerunds & Infinitives
- Ép chọn theo verb pattern: enjoy/avoid/mind + V-ing; decide/plan/hope + to-V.
- Thêm cue mục đích (to-V) vs hoạt động chung (V-ing).
""",
    "verb patterns": """
TOPIC-SPECIFIC RULES — Verb Patterns
- Remember/try/stop + V-ing vs + to-V (đổi nghĩa). Thêm ngữ cảnh khiến một hướng duy nhất hợp nghĩa.
""",
    # SVA
    "subject-verb agreement": """
TOPIC-SPECIFIC RULES — Subject–Verb Agreement
- Thêm chủ ngữ “tricky”: each/every, a number/the number, either/neither, collective nouns, noun clause.
- Cue số ít/số nhiều rõ ràng (data are vs data is? — tránh tranh luận khu vực).
""",
    "Subject–Verb Agreement (basics)": """
TOPIC-SPECIFIC RULES — Subject–Verb Agreement
- Thêm chủ ngữ “tricky”: each/every, a number/the number, either/neither, collective nouns, noun clause.
- Cue số ít/số nhiều rõ ràng (data are vs data is? — tránh tranh luận khu vực).
""",
    # Prepositions
    "prepositions of time": """
TOPIC-SPECIFIC RULES — Prepositions of Time
- Ép chọn in/on/at/by/for/since/during/over với mốc thời gian cụ thể; thêm dạng danh từ thời gian phù hợp.
""",
    "Time (in/on/at/by/for/since/during/over)": """
TOPIC-SPECIFIC RULES — Prepositions of Time
- Ép chọn in/on/at/by/for/since/during/over với mốc thời gian cụ thể; thêm dạng danh từ thời gian phù hợp.
""",
    "prepositions of place": """
TOPIC-SPECIFIC RULES — Prepositions of Place
- in/on/at/into/onto với bối cảnh vị trí/chuyển động; thêm động từ chuyển động để loại in/on vs into/onto.
""",
    "Place (in/on/at/into/onto/…)": """
TOPIC-SPECIFIC RULES — Prepositions of Place
- in/on/at/into/onto với bối cảnh vị trí/chuyển động; thêm động từ chuyển động để loại in/on vs into/onto.
""",
    "prepositional phrases": """
TOPIC-SPECIFIC RULES — Prepositional Phrases
- in spite of/despite/because of/according to; ép danh từ/gerund theo sau để loại sai hình thức.
""",
    "Phrases (in spite of/despite/because of/according to/…)": """
TOPIC-SPECIFIC RULES — Prepositional Phrases
- in spite of/despite/because of/according to; ép danh từ/gerund theo sau để loại sai hình thức.
""",
    # Inversion / Emphasis
    "inversion": """
TOPIC-SPECIFIC RULES — Inversion
- Hardly/rarely/seldom/no sooner + auxiliary + subject; thêm cặp quá khứ “No sooner had S V3 than …”.
""",
    "negative_adverbial_inversion": """
TOPIC-SPECIFIC RULES — Inversion
- Hardly/rarely/seldom/no sooner + auxiliary + subject; thêm cặp quá khứ “No sooner had S V3 than …”.
""",
    "conditional_inversion": """
TOPIC-SPECIFIC RULES — Inversion
- Hardly/rarely/seldom/no sooner + auxiliary + subject; thêm cặp quá khứ “No sooner had S V3 than …”.
""",
    # Cleft
    "cleft": """
TOPIC-SPECIFIC RULES — Cleft Sentences
- It is/was ... that ...; what-clause. Thêm bối cảnh nhấn mạnh đúng thành phần duy nhất.
""",
    "Cleft sentences (It is/was … that …)": """
TOPIC-SPECIFIC RULES — Cleft Sentences
- It is/was ... that ...; what-clause. Thêm bối cảnh nhấn mạnh đúng thành phần duy nhất.
""",
    "What-cleft": """
TOPIC-SPECIFIC RULES — Cleft Sentences
- It is/was ... that ...; what-clause. Thêm bối cảnh nhấn mạnh đúng thành phần duy nhất.
""",
    # Linking / Result
    "linking": """
TOPIC-SPECIFIC RULES — Linking/Adverbials
- so/so that/such...that: ép cấu trúc mức độ (such + adj + n + that; so + adj/adv + that) để chỉ còn 1 đáp án đúng.
""",
    "so / so that": """
TOPIC-SPECIFIC RULES — Linking/Adverbials
- so/so that/such...that: ép cấu trúc mức độ (such + adj + n + that; so + adj/adv + that) để chỉ còn 1 đáp án đúng.
""",
    "such … that": """
TOPIC-SPECIFIC RULES — Linking/Adverbials
- so/so that/such...that: ép cấu trúc mức độ (such + adj + n + that; so + adj/adv + that) để chỉ còn 1 đáp án đúng.
""",
    # Questions / Tags
    "question tags": """
TOPIC-SPECIFIC RULES — Question Tags
- Ép trợ động từ phù hợp thì/chủ ngữ; phủ định-nghi vấn đối xứng; thêm main clause để loại các tag sai.
""",
    }

    # choose block by topic name, else generic
    topic_rules = None
    for k, v in topic_rules_map.items():
        if k.lower() in (locked_topic or "").lower():
            topic_rules = v
            break
    if topic_rules is None:
        topic_rules = f"""
TOPIC-SPECIFIC RULES — {locked_topic}
- Thêm cue ngữ pháp/ngữ nghĩa đặc trưng của chủ đề để đảm bảo chỉ có 1 đáp án đúng.
- Ví dụ: thì quá khứ → time markers; mệnh đề quan hệ → comma/preposition/superlatives; so sánh → baseline 'than …' + định hướng; mạo từ → cue xác định/khái quát/duy nhất.
"""

    # 2) CoT guidance — locked_topic & num_items embedded
    cot_guidance = f"""
You are an expert English-assessment writer for Vietnamese learners.
OUTPUT: JSON list only (no markdown). Follow the schema strictly.

LANGUAGE
- Stems & options/answers: English.
- Hints: Vietnamese, ≤ 30 words, explain WHY typical errors are wrong.

CONSTRAINTS
- Type: "mcq" or "fill" (given by user).
- Exactly {num_items} items.
- Topic is LOCKED: "{locked_topic}". Every item MUST test only this topic (no drift).
- For "fill": prompt contains exactly one "_____".
- For "mcq": exactly 4 options with ids a,b,c,d and exactly one correctOptionId.

QUALITY & ANTI-AMBIGUITY
- Each stem MUST have exactly one grammatically correct answer.
- Past tenses: include explicit time markers (yesterday, last month, in 2020, ago).
- Relative clauses: force uniqueness via commas / preposition placement / superlatives.
- Comparatives (more/less/fewer): add directional context + baseline ("than ...") so only ONE answer is correct.
- Use contexts/vocabulary adapted from the user source text (business, travel, study, tech, daily life).
- Distractors must be plausible and reflect common VN-learner errors (tense/aspect confusion; who/whom; fewer/less; present perfect vs past simple; article specificity).

{topic_rules.strip()}

FEW-SHOT (GOOD)
{{
  "type": "mcq",
  "question": {{
    "id": "ex_cmp_001",
    "prompt": "To save money, we should hire _____ employees than last quarter.",
    "options": [
      {{"id":"a","label":"less"}},
      {{"id":"b","label":"fewer"}},
      {{"id":"c","label":"more"}},
      {{"id":"d","label":"most"}}
    ]
  }},
  "correctOptionId": "b",
  "hint": "Dùng 'fewer' cho danh từ đếm được (employees). Ngữ cảnh 'save money' cho thấy cần giảm số lượng."
}}

CHECKLIST BEFORE OUTPUT
- [ ] Exactly one correct answer?
- [ ] On-topic with "{locked_topic}" only (no drift)?
- [ ] Clear disambiguation cue? (time marker / commas / preposition / superlative / 'than ...' / article specificity)
- [ ] VN hint explains the typical error, ≤ 30 words?
- [ ] Schema valid (ids a,b,c,d; exactly one blank for fill)?

SOURCE TEXT (may mix EN+VI):
{post_text}

NOW OUTPUT THE FINAL JSON LIST OF {num_items} ITEMS.
""".strip()

    # 3) Wrap with base rules & user header
    base_rules = (
        "You are an expert English-assessment writer for Vietnamese students.\n"
        "OUTPUT JSON ONLY per the provided schema — no markdown, no commentary.\n\n"
        "LANGUAGE POLICY\n"
        "- Stems & options/answers: English.\n"
        "- Hints: Vietnamese.\n\n"
        "STRICT RULES\n"
        "- Type: \"mcq\" or \"fill\" (provided by user).\n"
        f"- Exactly {num_items} items.\n"
        "- Topic is LOCKED to the provided topic; every item MUST target that topic only (no topic drift).\n"
        "- For \"fill\": prompt contains exactly one \"_____\".\n"
        "- For \"mcq\": exactly 4 options with ids \"a\",\"b\",\"c\",\"d\" and exactly one correctOptionId.\n\n"
        "QUALITY\n"
        "- VN school contexts; common VN-learner errors; unambiguous stems; plausible distractors; concise Vietnamese hints.\n"
    )
    user_common = (
        f"Type: {hw_type}\n"
        f"Topic (LOCKED): \"{locked_topic}\"\n"
        f"Count (N): {num_items}\n"
        f"Source text (may mix EN+VI):\n\n{post_text}\n\n"
        f"Output: JSON according to schema.\n"
    )

    return f"{base_rules}\n{cot_guidance}\n{user_common}"


def build_locked_prompt(hw_type: str, locked_topic: str, post_text: str, num_items: int, mode: str) -> str:
    hw_type = hw_type if hw_type in {'mcq','fill'} else 'mcq'
    base_rules = (
        "You are an expert English-assessment writer for Vietnamese students.\n"
        "OUTPUT JSON ONLY per the provided schema — no markdown, no commentary.\n\n"
        "LANGUAGE POLICY\n"
        "- Stems & options/answers: English.\n"
        "- Hints: Vietnamese.\n\n"
        "STRICT RULES\n"
        "- Type: \"mcq\" or \"fill\" (provided by user).\n"
        "- Exactly N items.\n"
        "- Topic is LOCKED to the provided topic; every item MUST target that topic only (no topic drift).\n"
        "- For \"fill\": prompt contains exactly one \"_____\".\n"
        "- For \"mcq\": exactly 4 options with ids \"a\",\"b\",\"c\",\"d\" and exactly one correctOptionId.\n\n"
        "QUALITY\n"
        "- VN school contexts; common VN-learner errors; unambiguous stems; plausible distractors; concise Vietnamese hints.\n"
    )
    user_common = (
        f"Type: {hw_type}\n"
        f"Topic (LOCKED): \"{locked_topic}\"\n"
        f"Count (N): {num_items}\n"
        f"Source text (may mix EN+VI):\n\n{post_text}\n\n"
        f"Output: JSON according to schema.\n"
    )
    if mode == 'cot':
        return build_locked_prompt_cot(hw_type, locked_topic, post_text, num_items)
    else:
        minimal_guidance = (
            "ONLY OUTPUT JSON. DO NOT WRITE ANYTHING ELSE.\n"
            "Obey all rules above: locked topic, language policy, and schema.\n"
        )
        return f"{base_rules}\n{minimal_guidance}\n{user_common}"


# =========================
# Batch caller (best-effort)
# =========================
def _call_genai_batch(
    prompts: List[str],
    *,
    model: Optional[str] = None,
    response_mime_type: Optional[str] = 'application/json',
    response_schema: Any | None = None,
    temperature: Optional[float] = None,
    seed: Optional[int] = None,
) -> List[str]:
    key = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
    if not key:
        raise RuntimeError('GOOGLE_API_KEY or GEMINI_API_KEY is not set in environment')
    if genai is None or GenerateContentConfig is None:
        raise RuntimeError('Google GenAI SDK not installed. Install: pip install google-genai')
    model = model or os.getenv('GEMINI_MODEL') or 'gemini-2.5-flash'
    client = _get_client()
    cfg_kwargs = {
        'response_mime_type': response_mime_type,
        # Do not pass response_schema due to SDK transformer issues
    }
    if temperature is not None:
        cfg_kwargs['temperature'] = float(temperature)
    if seed is not None:
        cfg_kwargs['seed'] = int(seed)
    cfg = GenerateContentConfig(**cfg_kwargs)

    # Try batch API if present
    if hasattr(client.models, 'batch_generate_content'):
        resp = client.models.batch_generate_content(model=model, contents=prompts, config=cfg)
        texts: List[str] = []
        for r in resp:
            if getattr(r, 'parsed', None) is not None:
                try:
                    if hasattr(r.parsed, 'model_dump'):
                        texts.append(json.dumps(r.parsed.model_dump(), ensure_ascii=False))
                    elif hasattr(r.parsed, 'dict'):
                        texts.append(json.dumps(r.parsed.dict(), ensure_ascii=False))
                    else:
                        texts.append(json.dumps(r.parsed, ensure_ascii=False))
                    continue
                except Exception:
                    pass
            if getattr(r, 'text', None):
                texts.append(r.text)
            else:
                texts.append('')
        return texts

    # Fallback to serial calls
    return [
        _call_genai(p, model=model, response_mime_type=response_mime_type, response_schema=None,
                    temperature=temperature, seed=seed)
        for p in prompts
    ]



# =========================
# Utils
# =========================
def _strip_code_fences(s: str) -> str:
    if not s:
        return s
    s2 = s.strip()
    if s2.startswith('```'):
        s2 = re.sub(r"^```[a-zA-Z0-9_-]*\n", "", s2)
        if s2.endswith('```'):
            s2 = s2[:-3]
    return s2.strip()


 


# =========================
# Pydantic Schemas
# =========================
class Option(BaseModel):
    id: str  # a|b|c|d
    label: str


class QuestionMCQ(BaseModel):
    id: str
    prompt: str
    options: List[Option]


class MCQItem(BaseModel):
    type: Literal["mcq"]
    question: QuestionMCQ
    correctOptionId: str  # a|b|c|d
    hint: Optional[str] = None


class QuestionFill(BaseModel):
    id: str
    prompt: str  # should contain "_____"


class FillItem(BaseModel):
    type: Literal["fill"]
    question: QuestionFill
    answer: str
    hint: Optional[str] = None


class MCQList(RootModel[List[MCQItem]]):
    pass


class FillList(RootModel[List[FillItem]]):
    pass


# =========================
# Low-level caller
# =========================
def _call_genai(
    prompt: str,
    *,
    model: str | None = None,
    response_mime_type: Optional[str] = 'application/json',
    response_schema: Any | None = None,
    # Determinism controls (optional)
    temperature: Optional[float] = None,
    seed: Optional[int] = None,
) -> str:
    """
    Calls Gemini with structured-output enabled via response_schema (Pydantic).
    Returns a JSON string. Raises on any failure.
    """
    key = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
    if not key:
        raise RuntimeError('GOOGLE_API_KEY or GEMINI_API_KEY is not set in environment')

    if genai is None or GenerateContentConfig is None:
        raise RuntimeError('Google GenAI SDK not installed. Install: pip install google-genai')

    # Choose model (env override: GEMINI_MODEL)
    model = model or os.getenv('GEMINI_MODEL') or 'gemini-2.5-flash'  # or 'gemini-2.5-flash-lite'

    if DEBUG:
        print(f'[ai] model={model}')

    client = _get_client()

    cfg = None
    if response_mime_type or (response_schema is not None) or (temperature is not None) or (seed is not None):
        # Some SDK versions may not support all fields; use kwargs dict.
        cfg_kwargs = {
            'response_mime_type': response_mime_type,
            'response_schema': response_schema,
        }
        if temperature is not None:
            cfg_kwargs['temperature'] = float(temperature)
        if seed is not None:
            cfg_kwargs['seed'] = int(seed)
        cfg = GenerateContentConfig(**cfg_kwargs)

    if DEBUG:
        print('[ai] sending prompt (first 600 chars):\n', prompt[:600])

    resp = client.models.generate_content(model=model, contents=prompt, config=cfg)

    # Prefer structured parsed object when schema is given
    if getattr(resp, 'parsed', None) is not None:
        if DEBUG:
            print(f'[ai] resp.parsed type: {type(resp.parsed)}')
        try:
            # For Pydantic models, use model_dump() method
            if hasattr(resp.parsed, 'model_dump'):
                data = resp.parsed.model_dump()
                return json.dumps(data, ensure_ascii=False)
            # For older Pydantic versions, try dict() method
            elif hasattr(resp.parsed, 'dict'):
                data = resp.parsed.dict()
                return json.dumps(data, ensure_ascii=False)
            # Try direct JSON serialization as fallback
            else:
                return json.dumps(resp.parsed, ensure_ascii=False)
        except Exception as e:
            if DEBUG:
                print(f'[ai] Pydantic serialization failed: {e}')
            pass

    # Fallback: raw JSON string
    if getattr(resp, 'text', None):
        return resp.text

    raise RuntimeError('GenAI returned no structured parsed output')


# =========================
# Public API
# =========================
def _pick_schema_and_hint(hw_type: str):
    """Return (list_model, item_hint_str) based on type."""
    if hw_type == 'mcq':
        return (
            MCQList,
            'Each item must have type "mcq". Options must be exactly 4 items with ids a|b|c|d and label.'
        )
    else:
        return (
            FillList,
            'Each item must have type "fill". The question.prompt must contain a single "_____".'
        )


def generate_with_llm(
    post_text: str,
    hw_type: str,
    num_items: int = 5,
    mode: str = 'cot',
    *,
    temperature: Optional[float] = None,
    seed: Optional[int] = None,
    locked_topic: Optional[str] = None,
    full_prompt: Optional[str] = None,
    model: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Generate strict JSON items using Google GenAI SDK with Pydantic schema.
    mode: 'cot' for Chain-of-Thought (analysis + generation), 'minimal' for a concise prompt.
    Returns a Python list of dicts (already validated).
    Raises on any failure.
    """
    hw_type = hw_type if hw_type in {'mcq', 'fill'} else 'mcq'

    list_model, item_hint = _pick_schema_and_hint(hw_type)

    # If caller provides a full prompt, use it as-is
    if full_prompt is not None:
        prompt_to_use = full_prompt
    else:
        # Build prompt according to mode and whether a locked topic is provided
        if locked_topic:
            if mode == 'cot':
                # Single source of truth for CoT prompts
                prompt_to_use = build_locked_prompt_cot(hw_type, locked_topic, post_text, num_items)
            else:
                minimal_guidance = (
                    "ONLY OUTPUT JSON. DO NOT WRITE ANYTHING ELSE.\n"
                    "Obey all rules above: locked topic, language policy, and schema.\n"
                )
                base_rules = (
                    "You are an expert English-assessment writer for Vietnamese students.\n"
                    "OUTPUT JSON ONLY per the provided schema — no markdown, no commentary.\n\n"
                    "LANGUAGE POLICY\n"
                    "- Stems & options/answers: English.\n"
                    "- Hints: Vietnamese.\n\n"
                    "STRICT RULES\n"
                    "- Type: \"mcq\" or \"fill\" (provided by user).\n"
                    "- Exactly N items.\n"
                    "- Topic is LOCKED to the provided topic; every item MUST target that topic only (no topic drift).\n"
                    "- For \"fill\": prompt contains exactly one \"_____\".\n"
                    "- For \"mcq\": exactly 4 options with ids \"a\",\"b\",\"c\",\"d\" and exactly one correctOptionId.\n\n"
                    "QUALITY\n"
                    "- VN school contexts; common VN-learner errors; unambiguous stems; plausible distractors; concise Vietnamese hints.\n"
                )
                user_common = (
                    f"Type: {hw_type}\n"
                    f"Topic (LOCKED): \"{locked_topic}\"\n"
                    f"Count (N): {num_items}\n"
                    f"Source text (may mix EN+VI):\n\n{post_text}\n\n"
                    f"Output: JSON according to schema.\n"
                    f"{item_hint}"
                )
                prompt_to_use = f"{base_rules}\n{minimal_guidance}\n{user_common}"
        else:
            # Backward-compatible prompts used by existing four-sets pipeline
            cot_prompt = f"""You are an expert English teacher specializing in Vietnamese English exams. Follow this step-by-step analysis:

CONTENT TO ANALYZE:
{post_text}

**STEP 1: TOPIC & VOCABULARY ANALYSIS**
Identify grammar topics relevant to Vietnamese exams and key vocabulary.

**STEP 2: QUESTION PRIORITIZATION STRATEGY**
Plan {num_items} {hw_type} high-quality questions.

**STEP 3: QUESTION CREATION**
Create the {num_items} questions (VN school context, common VN-learner errors, unambiguous stems, concise Vietnamese hints).

FORMAT REQUIREMENTS:
{item_hint}

ONLY OUTPUT THE JSON LIST OF ITEMS."""
            if mode == 'minimal':
                minimal_prompt = (
                    f"Create exactly {num_items} {hw_type} questions from the following text. "
                    f"ONLY OUTPUT JSON following this schema: {item_hint} "
                    f"Text: {post_text}"
                )
                prompt_to_use = minimal_prompt
            else:
                prompt_to_use = cot_prompt

    # Ask model to produce structured output as JSON string (no SDK schema to avoid transformer issues)
    raw = _call_genai(
        prompt_to_use,
        model=model or os.getenv('GEMINI_MODEL') or 'gemini-2.5-flash',
        response_mime_type='application/json',
        response_schema=list_model,  # enable SDK structured-output with Pydantic schema
        temperature=temperature,
        seed=seed,
    )
    cleaned = _strip_code_fences(raw)
    try:
        # Prefer fast JSON-validated path
        validated_list = list_model.model_validate_json(cleaned)
    except ValidationError:
        # If SDK returned parsed-like JSON text, validate the parsed object
        parsed_any = json.loads(cleaned)
        validated_list = list_model.model_validate(parsed_any)
    # Convert to list[dict] for downstream compatibility
    return [item.model_dump() for item in validated_list.root]


def generate_homework(post_text: str, hw_type: str, num_items: int = 5) -> List[Dict[str, Any]]:
    """Public API mirroring original: pure GenAI, Pydantic-validated."""
    return generate_with_llm(post_text, hw_type, num_items)
