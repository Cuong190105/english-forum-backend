"""Validate JSON outputs and write a pretty-printed CSV for human evaluation.

- Reads `data/jfleg_eval_prefill_100.csv` (or path passed via --input).
- Validates `cot_output` and `minimal_output` JSON strings against Pydantic root models
  exported from `utilities.ai_generator_LLM_Clone` (MCQList / FillList). If validation fails,
  writes the row id to `data/invalid_rows.txt` and continues.
- Writes `data/jfleg_eval_prefill_100_pretty.csv` where `cot_output` and `minimal_output` are
  pretty-printed JSON (with newlines and indentation) for readability.

Usage:
    python -m scripts.validate_and_pretty_csv --input data/jfleg_eval_prefill_100.csv

"""
from __future__ import annotations
import argparse
import csv
import json
import os
from typing import Optional

# Add repo root to path so utilities can be imported when running script directly
import sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    from utilities.ai_generator_LLM_Clone import MCQList, FillList
except Exception as e:
    MCQList = None
    FillList = None
    print("Warning: Could not import Pydantic schemas from utilities.ai_generator_LLM_Clone:", e)


def try_validate(json_text: str) -> bool:
    """Try parsing json_text and validate against known schemas. Returns True if valid or empty."""
    if not json_text or json_text.strip() == "":
        return False
    try:
        parsed = json.loads(json_text)
    except Exception:
        return False
    # If schemas available, try them
    if MCQList is None and FillList is None:
        # Basic sanity: parsed should be a list of dicts with 'type' keys
        if isinstance(parsed, list) and all(isinstance(x, dict) and 'type' in x for x in parsed):
            return True
        return False
    # Try MCQList then FillList
    try:
        if isinstance(parsed, list):
            # try MCQList
            if MCQList is not None:
                MCQList.model_validate(parsed)
                return True
            if FillList is not None:
                FillList.model_validate(parsed)
                return True
    except Exception:
        return False
    return False


def pretty_json_field(json_text: str, indent: int = 2) -> str:
    if not json_text or json_text.strip() == "":
        return ""
    try:
        parsed = json.loads(json_text)
        return json.dumps(parsed, ensure_ascii=False, indent=indent)
    except Exception:
        # fallback: return original text
        return json_text


def main(input_path: str, output_path: str, invalid_path: str):
    invalid_ids = []
    rows = []
    with open(input_path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for r in reader:
            rows.append(r)
    # Validate each row
    for r in rows:
        rid = r.get('id') or r.get('Id') or ''
        cot = r.get('cot_output', '')
        mini = r.get('minimal_output', '')
        ok_cot = try_validate(cot)
        ok_min = try_validate(mini)
        if not (ok_cot and ok_min):
            invalid_ids.append(rid)
    # Write invalids
    with open(invalid_path, 'w', encoding='utf-8') as f:
        for i in invalid_ids:
            f.write(f"{i}\n")
    print(f"Found {len(invalid_ids)} rows with invalid JSON (written to {invalid_path})")
    # Write pretty CSV
    pretty_fieldnames = fieldnames.copy() if fieldnames else []
    # override the cot/minimal fields to contain pretty text
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=pretty_fieldnames)
        writer.writeheader()
        for r in rows:
            r2 = r.copy()
            r2['cot_output'] = pretty_json_field(r.get('cot_output', ''))
            r2['minimal_output'] = pretty_json_field(r.get('minimal_output', ''))
            writer.writerow(r2)
    print(f"Wrote pretty CSV to {output_path}")


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--input', default='data/jfleg_eval_prefill_100.csv')
    p.add_argument('--output', default='data/jfleg_eval_prefill_100_pretty.csv')
    p.add_argument('--invalid', default='data/invalid_rows.txt')
    args = p.parse_args()
    main(args.input, args.output, args.invalid)
