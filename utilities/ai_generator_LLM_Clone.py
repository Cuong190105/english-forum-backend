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

    client = genai.Client(api_key=key)

    cfg = None
    if response_mime_type or (response_schema is not None):
        cfg = GenerateContentConfig(
            response_mime_type=response_mime_type,
            response_schema=response_schema, 
        )

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


def generate_with_llm(post_text: str, hw_type: str, num_items: int = 5, mode: str = 'cot') -> List[Dict[str, Any]]:
    """
    Generate strict JSON items using Google GenAI SDK with Pydantic schema.
    mode: 'cot' for Chain-of-Thought (analysis + generation), 'minimal' for a concise prompt.
    Returns a Python list of dicts (already validated).
    Raises on any failure.
    """
    hw_type = hw_type if hw_type in {'mcq', 'fill'} else 'mcq'

    list_model, item_hint = _pick_schema_and_hint(hw_type)

    # Chain of Thought prompting with Vietnamese exam focus
    cot_prompt = f"""You are an expert English teacher specializing in Vietnamese English exams. Follow this step-by-step analysis:

CONTENT TO ANALYZE:
{post_text}

**STEP 1: TOPIC & VOCABULARY ANALYSIS**
First, analyze the content and identify:
1. All grammar topics present (focus on these high-priority Vietnamese exam topics):
   - Tenses & Aspects (Present Perfect vs Past Simple, Past Perfect, Future forms, etc.)
   - Conditionals (Zero, First, Second, Third, Mixed)
   - Passive Voice (all tenses, with modals)
   - Reported Speech (tense changes, reporting verbs)
   - Modal Verbs (obligation, possibility, ability, past modals)
   - Relative Clauses (defining/non-defining, pronouns)
   - Gerunds & Infinitives (verb patterns)
   - Inversion (formal structures, negative adverbials, conditionals without if)
   - Articles, Prepositions, Subject-Verb Agreement
   - Cleft Sentences, Subjunctive, Causative Verbs
   - Wish & If only, Comparison, Participle Clauses

2. Key vocabulary words ranked by CEFR level (C2, C1, B2, B1, A2, A1)
   - Select 2-3 most challenging/important words for testing

**STEP 2: QUESTION PRIORITIZATION STRATEGY**
Based on the {num_items} questions requested:
1. Prioritize grammar topics that appear most frequently in Vietnamese English exams
2. Focus on topics that Vietnamese learners commonly struggle with
3. If more grammar topics than questions: choose the most exam-relevant ones
4. Include vocabulary testing for the selected challenging words
5. Ensure difficulty progression from basic to advanced

**STEP 3: QUESTION CREATION**
Create {num_items} {hw_type} questions following Vietnamese exam patterns:
- Use realistic scenarios familiar to Vietnamese students
- Include common mistake patterns Vietnamese learners make
- Test practical application, not just theoretical knowledge
- Ensure clear, unambiguous language
- Add educational hints that explain the underlying rules

**ANALYSIS OUTPUT:**
Now think through each step and create the questions:

1. **Topics Identified:** [List the grammar topics found]
2. **Key Vocabulary:** [List 2-3 challenging words with CEFR levels]
3. **Prioritization:** [Explain which topics you'll focus on and why]
4. **Questions:** [Generate the actual questions]

FORMAT REQUIREMENTS:
{item_hint}

Please generate exactly {num_items} high-quality questions that Vietnamese English exam takers would benefit from."""
    # Choose prompt based on mode
    if mode == 'minimal':
        minimal_prompt = (
            f"Create exactly {num_items} {hw_type} questions from the following text. "
            f"Do NOT write any extra explanation. Output MUST be valid JSON and follow this schema: {item_hint} "
            f"Text: {post_text}"
        )
        prompt_to_use = minimal_prompt
    else:
        prompt_to_use = cot_prompt

    # Ask model to produce structured output per our Pydantic list model
    raw = _call_genai(
        prompt_to_use,
        model=os.getenv('GEMINI_MODEL') or 'gemini-2.5-flash',
        response_mime_type='application/json',
        response_schema=list_model,   # << pass the Pydantic RootModel[List[...]]
    )

    cleaned = _strip_code_fences(raw)

    # Validate into Pydantic types (handles both JSON string or parsed python objects)
    try:
        # If `raw` is JSON text, use model_validate_json:
        validated_list = list_model.model_validate_json(cleaned)
    except ValidationError:
        # In case SDK already returned parsed Python structures serialized oddly:
        parsed_any = json.loads(cleaned)
        validated_list = list_model.model_validate(parsed_any)

    # Convert to list[dict] for downstream compatibility
    return [item.model_dump() for item in validated_list.root]


def generate_homework(post_text: str, hw_type: str, num_items: int = 5) -> List[Dict[str, Any]]:
    """Public API mirroring original: pure GenAI, Pydantic-validated."""
    return generate_with_llm(post_text, hw_type, num_items)
