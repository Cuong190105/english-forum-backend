from __future__ import annotations
from typing import List, Dict, Any, Tuple, Optional
import re
from pydantic import ValidationError

from utilities.ai_generator_LLM_Clone import MCQList, FillList


VI_PATTERN = re.compile(r"[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđĐ]")
EN_FUNCTIONS = set(
    "a,an,the,and,or,but,if,so,to,of,in,for,on,at,by,with,from,that,which,who,whom,whose,not,no,do,does,did,be,is,are,was,were,been,being".split(',')
)


def is_vietnamese(s: str) -> bool:
    return bool(VI_PATTERN.search(s or ""))


def is_english_like(s: str) -> bool:
    # Language enforcement removed; keep stub for potential future use
    if not s:
        return False
    tokens = re.findall(r"[A-Za-z']+", s.lower())
    return len(tokens) >= 1


def validate_items(
    data: List[Dict[str, Any]],
    item_type: str,
    *,
    expected_count: Optional[int] = None,
) -> Tuple[bool, List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []

    # Pydantic schema
    try:
        if item_type == 'mcq':
            MCQList.model_validate(data)
        else:
            FillList.model_validate(data)
    except ValidationError as e:
        errors.append(f"pydantic: {e}")
        # continue to collect more errors

    # Count check: if expected_count provided, enforce exact match; else require at least 1
    N = len(data)
    if expected_count is not None:
        if N != expected_count:
            errors.append(f"count_mismatch: expected {expected_count}, got {N}")
    else:
        if N <= 0:
            errors.append("count_mismatch: expected at least 1 item")

    # Per-item checks
    for i, it in enumerate(data, start=1):
        t = it.get('type')
        if item_type == 'mcq' and t != 'mcq':
            errors.append(f"i{i}: type != mcq")
        if item_type == 'fill' and t != 'fill':
            errors.append(f"i{i}: type != fill")

        q = it.get('question', {})
        prompt = q.get('prompt', '')
        # Language policy removed from hard validation; only log warnings for code-mixing
        code_mixing = False
        if item_type == 'fill':
            if is_vietnamese(prompt) or is_vietnamese(it.get('answer', '')):
                code_mixing = True
        else:
            if is_vietnamese(prompt) or any(is_vietnamese(opt.get('label','')) for opt in q.get('options', [])):
                code_mixing = True
        if code_mixing:
            warnings.append(f"i{i}: code_mixing_detected")

        if item_type == 'fill':
            if prompt.count('_____') != 1:
                errors.append(f"i{i}: fill_blank_count != 1")
        else:
            opts = q.get('options', [])
            if len(opts) != 4:
                errors.append(f"i{i}: mcq_options_count != 4")
            ids = [o.get('id') for o in opts]
            if ids != ['a','b','c','d']:
                errors.append(f"i{i}: mcq_option_ids != a,b,c,d")
            cid = it.get('correctOptionId')
            if cid not in {'a','b','c','d'}:
                errors.append(f"i{i}: correctOptionId_invalid")

    # Difficulty progression checks removed per requirement
    
    return (len(errors) == 0, errors, warnings)
