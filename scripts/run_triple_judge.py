from __future__ import annotations
import os
import json
import csv
from pathlib import Path
from typing import Any, Dict, List

# Ensure project root on path
import sys
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmark.judge_triple import judge_triple_batch_mcq, judge_triple_batch_fill
from benchmark.report import write_per_item_csv


def load_items(pred_path: Path) -> List[Dict[str, Any]]:
    data = json.loads(pred_path.read_text(encoding='utf-8'))
    if not isinstance(data, list):
        raise ValueError('pred JSON must be a list of items')
    return data


def write_per_item(out_csv: Path, rows: List[Dict[str, Any]]) -> None:
    # Use centralized writer with full legacy schema
    write_per_item_csv(out_csv, rows)


def main():
    import argparse
    ap = argparse.ArgumentParser(description='Run triple judges (Gemini batch, Claude batch, DeepSeek) on a prediction JSON file.')
    ap.add_argument('--pred', required=True, help='Path to pred JSON (from benchmark/pred/...)')
    ap.add_argument('--topic', required=True)
    ap.add_argument('--type', dest='hw_type', required=True, choices=['mcq','fill'])
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--run-id', required=True)
    ap.add_argument('--config', required=True)
    ap.add_argument('--out', required=True, help='Output CSV path (per_item)')
    ap.add_argument('--source-sha', default='', help='Optional source_text_sha to include in output')
    args = ap.parse_args()

    pred_path = Path(args.pred)
    items = load_items(pred_path)

    if args.hw_type == 'mcq':
        results = judge_triple_batch_mcq(items, topic=args.topic)
    else:
        results = judge_triple_batch_fill(items, topic=args.topic)

    rows: List[Dict[str, Any]] = []
    for i, it in enumerate(items):
        q = it.get('question', {})
        rows.append({
            # Core identity
            'run_id': args.run_id,
            'config': args.config,
            'topic': args.topic,
            'type': args.hw_type,
            'seed': args.seed,
            'source_text_sha': args.source_sha,
            'idx': i+1,
            # IDs (gold may be unknown here)
            'qid_gold': '',
            'qid_pred': q.get('id') or f"{i+1}",
            # Structural/semantic metrics not available in this judge-only pass
            'structural_valid': '',
            'question_sim': '',
            'ans_sim': '',
            'distractor_diversity': '',
            'ans_score': '',
            'item_score': '',
            # Legacy two-judge fields (left empty in triple-judge flow)
            'judge_verdict': '',
            'judge_score': '',
            'judge_why': '',
            'judge2_verdict': '',
            'judge2_score': '',
            'judge2_why': '',
            # Extended 3-judge fields
            'row_idx': '',
            'judge_gemini_verdict': results[i].get('gemini_verdict',''),
            'judge_gemini_why': results[i].get('gemini_why',''),
            'judge_claude_verdict': results[i].get('claude_verdict',''),
            'judge_claude_why': results[i].get('claude_why',''),
            'judge_deepseek_verdict': results[i].get('deepseek_verdict',''),
            'judge_deepseek_why': results[i].get('deepseek_why',''),
        })

    write_per_item(Path(args.out), rows)
    print(f"Wrote {len(rows)} rows to {args.out}")


if __name__ == '__main__':
    main()
