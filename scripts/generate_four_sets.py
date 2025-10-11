from __future__ import annotations
import argparse
import csv
import json
import os
import re
import sys
from typing import Any, Dict, List, Tuple


def _add_repo_root_to_syspath():
    here = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.normpath(os.path.join(here, os.pardir))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)


_add_repo_root_to_syspath()

from utilities.ai_generator_LLM_Clone import MCQList, FillList, generate_with_llm  # noqa: E402


def load_rows(path: str) -> Tuple[List[dict], List[str]]:
    with open(path, 'r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        headers = reader.fieldnames or []
    return rows, headers


def detect_source_field(headers: List[str]) -> str:
    for c in ("source_text", "source", "text", "input"):
        if c in headers:
            return c
    return headers[1] if len(headers) > 1 else headers[0]


def is_mcq_items(items: Any) -> bool:
    if not isinstance(items, list) or not items:
        return False
    t = items[0].get('type') if isinstance(items[0], dict) else None
    return t == 'mcq'


def is_fill_items(items: Any) -> bool:
    if not isinstance(items, list) or not items:
        return False
    t = items[0].get('type') if isinstance(items[0], dict) else None
    return t == 'fill'


def json_ok(text: str) -> bool:
    try:
        data = json.loads(text)
        # validate basic schema with pydantic where possible
        if is_mcq_items(data):
            MCQList.model_validate({'root': data})
        elif is_fill_items(data):
            FillList.model_validate({'root': data})
        else:
            # If empty or wrong, still consider parse success
            pass
        return True
    except Exception:
        return False


def check_number_of_options(items: Any) -> bool:
    """True if for MCQ items each question has exactly 4 options with ids a|b|c|d."""
    if not isinstance(items, list) or not items:
        return False
    if not is_mcq_items(items):
        return True  # Only applies to MCQ; non-MCQ passes
    for it in items:
        q = it.get('question') or {}
        opts = q.get('options') or []
        if len(opts) != 4:
            return False
        ids = {o.get('id') for o in opts}
        if ids != {'a','b','c','d'}:
            return False
    return True


def normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()


def answer_in_context(items: Any, context: str) -> bool:
    """For fill items: answer substring appears in context (case-insensitive, normalized). For MCQ, check correct option text present in context as a weak heuristic."""
    if not isinstance(items, list) or not items:
        return False
    ctx = normalize_text(context)
    if is_fill_items(items):
        for it in items:
            ans = normalize_text(it.get('answer'))
            if ans and ans in ctx:
                return True
        return False
    if is_mcq_items(items):
        # Weak heuristic: correct option label appears in context
        for it in items:
            cid = it.get('correctOptionId')
            q = it.get('question') or {}
            opts = q.get('options') or []
            label = None
            for o in opts:
                if o.get('id') == cid:
                    label = o.get('label')
                    break
            if label and normalize_text(label) in ctx:
                return True
        return False
    return False


def pretty_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def maybe_reuse(existing_text: str | None) -> List[dict] | None:
    if not existing_text:
        return None
    try:
        data = json.loads(existing_text)
        if isinstance(data, list):
            return data
    except Exception:
        return None
    return None


def main():
    parser = argparse.ArgumentParser(description='Generate 4 output sets (flash/flash-lite x CoT/Minimal) and compute checks.')
    parser.add_argument('--input', default='data/jfleg_eval_prefill_100_pretty.csv')
    parser.add_argument('--output', default='data/jfleg_eval_four_sets.csv')
    parser.add_argument('--reuse-cot', action='store_true', help='Reuse existing CoT from input CSV if present (for flash CoT)')
    parser.add_argument('--limit', type=int, default=100)
    parser.add_argument('--hw-type', choices=['mcq','fill'], default='mcq')
    args = parser.parse_args()

    rows, headers = load_rows(args.input)
    src_field = detect_source_field(headers)

    out_rows: List[Dict[str, Any]] = []

    # Configure model mapping
    configs = [
        ("flash", "cot", "gemini-2.5-flash", 'cot_output_flash'),
        ("flash", "minimal", "gemini-2.5-flash", 'minimal_output_flash'),
        ("flash-lite", "cot", "gemini-2.5-flash-lite", 'cot_output_flash_lite'),
        ("flash-lite", "minimal", "gemini-2.5-flash-lite", 'minimal_output_flash_lite'),
    ]

    for i, r in enumerate(rows[: args.limit]):
        rid = r.get('id') or r.get('Id') or r.get('ID') or r.get(headers[0]) or str(i+1)
        context = (r.get(src_field) or '').strip()
        base: Dict[str, Any] = {
            'id': rid,
            'source_text': context,
        }

        # Generate or reuse
        for family, mode, model, colname in configs:
            items: List[dict] | None = None
            if args.reuse_cot and family == 'flash' and mode == 'cot':
                items = maybe_reuse(r.get('cot_output'))
            if items is None:
                os.environ['GEMINI_MODEL'] = model
                items = generate_with_llm(context, args.hw_type, num_items=1, mode=mode)
            # Write pretty JSON
            base[colname] = pretty_json(items)
            # Checks
            j_ok = items is not None  # if we got here, it's parsed python already
            num_ok = check_number_of_options(items)
            aic = answer_in_context(items, context)
            base[f'{colname}_json_ok'] = 1 if j_ok else 0
            base[f'{colname}_num_options_ok'] = 1 if num_ok else 0
            base[f'{colname}_answer_in_context'] = 1 if aic else 0

        out_rows.append(base)

    # Write output CSV
    fieldnames = [
        'id','source_text',
        'cot_output_flash','cot_output_flash_json_ok','cot_output_flash_num_options_ok','cot_output_flash_answer_in_context',
        'minimal_output_flash','minimal_output_flash_json_ok','minimal_output_flash_num_options_ok','minimal_output_flash_answer_in_context',
        'cot_output_flash_lite','cot_output_flash_lite_json_ok','cot_output_flash_lite_num_options_ok','cot_output_flash_lite_answer_in_context',
        'minimal_output_flash_lite','minimal_output_flash_lite_json_ok','minimal_output_flash_lite_num_options_ok','minimal_output_flash_lite_answer_in_context',
    ]

    with open(args.output, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in out_rows:
            writer.writerow(row)

    print(f"Wrote {len(out_rows)} rows to {args.output}")

    # Compute dataset-level summary metrics
    def avg(key: str) -> float:
        vals = [r.get(key) for r in out_rows]
        vals = [v for v in vals if isinstance(v, int)]
        return (sum(vals) / len(vals)) if vals else 0.0

    summary = {
        'rows': len(out_rows),
        'flash_cot': {
            'json_ok_rate': avg('cot_output_flash_json_ok'),
            'json_error_rate': 1 - avg('cot_output_flash_json_ok'),
            'num_options_ok_rate': avg('cot_output_flash_num_options_ok'),
            'answer_in_context_rate': avg('cot_output_flash_answer_in_context'),
        },
        'flash_minimal': {
            'json_ok_rate': avg('minimal_output_flash_json_ok'),
            'json_error_rate': 1 - avg('minimal_output_flash_json_ok'),
            'num_options_ok_rate': avg('minimal_output_flash_num_options_ok'),
            'answer_in_context_rate': avg('minimal_output_flash_answer_in_context'),
        },
        'flash_lite_cot': {
            'json_ok_rate': avg('cot_output_flash_lite_json_ok'),
            'json_error_rate': 1 - avg('cot_output_flash_lite_json_ok'),
            'num_options_ok_rate': avg('cot_output_flash_lite_num_options_ok'),
            'answer_in_context_rate': avg('cot_output_flash_lite_answer_in_context'),
        },
        'flash_lite_minimal': {
            'json_ok_rate': avg('minimal_output_flash_lite_json_ok'),
            'json_error_rate': 1 - avg('minimal_output_flash_lite_json_ok'),
            'num_options_ok_rate': avg('minimal_output_flash_lite_num_options_ok'),
            'answer_in_context_rate': avg('minimal_output_flash_lite_answer_in_context'),
        },
    }

    summary_path = os.path.join(os.path.dirname(args.output), 'jfleg_eval_four_sets_summary.json')
    with open(summary_path, 'w', encoding='utf-8') as sf:
        json.dump(summary, sf, ensure_ascii=False, indent=2)
    print("Summary:")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Wrote summary to {summary_path}")


if __name__ == '__main__':
    main()
