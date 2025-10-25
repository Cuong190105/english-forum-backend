from __future__ import annotations
import argparse
import csv
import json
import re
from pathlib import Path
from typing import Dict, Any

# Ensure project root on path
import sys
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmark.score import mcq_semantics, fill_semantics
from benchmark.judge import run_judges_mcq, run_judges_fill


def _safe_topic(topic: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", topic or "")


def repair_row(run_id: str, line_number: int) -> Dict[str, Any]:
    """
    Recompute semantics + judges for a single per_item row identified by its 1-based CSV line number.
    The header is line 1; pass a data line >= 2.
    Returns the updated row.
    """
    per_item_path = Path(f"benchmark/reports/{run_id}/per_item.csv")
    if not per_item_path.exists():
        raise FileNotFoundError(f"per_item.csv not found for run_id={run_id}: {per_item_path}")

    # Read CSV into memory (small enough for targeted fix)
    with per_item_path.open('r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        header = reader.fieldnames or []

    # CSV line_number includes header, so data index = line_number - 2
    data_idx = line_number - 2
    if data_idx < 0 or data_idx >= len(rows):
        raise IndexError(f"line_number out of range: {line_number} (rows={len(rows)} + header)")

    row = rows[data_idx]
    topic = row.get('topic', '')
    hw_type = row.get('type', 'mcq')
    seed = int(row.get('seed', '0') or 0)
    cfg = row.get('config', 'minimal')
    sha = row.get('source_text_sha', '')
    idx = int(row.get('idx', '1') or 1) - 1  # 0-based index for JSON arrays

    if not topic or not sha:
        raise ValueError('Row is missing required fields: topic/source_text_sha')

    safe_topic = _safe_topic(topic)
    pred_path = Path(f"benchmark/pred/{cfg}/{safe_topic}/{hw_type}/{sha}/seed{seed}.json")
    gold_path = Path(f"benchmark/gold/{safe_topic}/{hw_type}/{sha}/seed0.json")
    if not pred_path.exists():
        raise FileNotFoundError(f"pred file not found: {pred_path}")
    if not gold_path.exists():
        raise FileNotFoundError(f"gold file not found: {gold_path}")

    pred = json.loads(pred_path.read_text(encoding='utf-8'))
    gold = json.loads(gold_path.read_text(encoding='utf-8'))
    if not (0 <= idx < min(len(pred), len(gold))):
        raise IndexError(f"Item idx out of range: {idx+1} with pred={len(pred)} gold={len(gold)}")

    pi = pred[idx]
    gi = gold[idx]

    # Recompute semantics and judges (primary + judge2)
    if hw_type == 'mcq':
        ps, ans_sim, diversity, item_score = mcq_semantics(pi, gi)
        all_j = run_judges_mcq(
            pi['question']['prompt'],
            {o['id']: o['label'] for o in pi['question']['options']},
            pi['correctOptionId'],
            topic,
            context=None,
        )
        vmap: Dict[str, float] = {'correct': 1.0, 'ambiguous': 0.5, 'incorrect': 0.0}
        primary = all_j[0] if all_j else {'verdict': 'error', 'why': 'no_judge'}
        jscore = vmap.get(str(primary.get('verdict', '')).lower(), 0.0)
        jwhy = primary.get('why', '')
        j2 = all_j[1] if len(all_j) > 1 else None
        row.update({
            'question_sim': round(ps, 4),
            'ans_sim': ('' if ans_sim is None else round(ans_sim, 4)),
            'distractor_diversity': round(diversity, 4),
            'ans_score': ('' if ans_sim is None else round(ans_sim, 4)),
            'item_score': round(item_score, 4),
            'judge_verdict': primary.get('verdict', ''),
            'judge_score': round(jscore, 4),
            'judge_why': jwhy,
            'judge2_verdict': (j2.get('verdict') if j2 else ''),
            'judge2_score': (vmap.get(str(j2.get('verdict', '')).lower(), 0.0) if j2 else ''),
            'judge2_why': (j2.get('why') if j2 else ''),
        })
    else:
        ps, ans_score, item_score = fill_semantics(pi, gi)
        all_j = run_judges_fill(
            pi['question']['prompt'],
            pi['answer'],
            topic,
            context=None,
        )
        vmap: Dict[str, float] = {'acceptable': 1.0, 'unacceptable': 0.0}
        primary = all_j[0] if all_j else {'verdict': 'error', 'why': 'no_judge'}
        jscore = vmap.get(str(primary.get('verdict', '')).lower(), 0.0)
        jwhy = primary.get('why', '')
        j2 = all_j[1] if len(all_j) > 1 else None
        row.update({
            'question_sim': round(ps, 4),
            'ans_sim': round(ans_score, 4),
            'distractor_diversity': '',
            'ans_score': round(ans_score, 4),
            'item_score': round(item_score, 4),
            'judge_verdict': primary.get('verdict', ''),
            'judge_score': round(jscore, 4),
            'judge_why': jwhy,
            'judge2_verdict': (j2.get('verdict') if j2 else ''),
            'judge2_score': (vmap.get(str(j2.get('verdict', '')).lower(), 0.0) if j2 else ''),
            'judge2_why': (j2.get('why') if j2 else ''),
        })

    # Write back CSV (preserve header order)
    keys = ['run_id','config','topic','type','seed','source_text_sha','idx','qid_gold','qid_pred','structural_valid',
            'question_sim','ans_sim','distractor_diversity','ans_score','item_score',
            'judge_verdict','judge_score','judge_why','judge2_verdict','judge2_score','judge2_why']
    with per_item_path.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for i, r in enumerate(rows):
            if i == data_idx:
                w.writerow({k: row.get(k, '') for k in keys})
            else:
                w.writerow({k: r.get(k, '') for k in keys})

    return row


def main():
    ap = argparse.ArgumentParser(description='Repair a single per_item row by recomputing semantics and judges.')
    ap.add_argument('--run-id', required=True, help='Run ID (folder name under benchmark/reports)')
    ap.add_argument('--line', type=int, required=True, help='1-based CSV line number to repair (including header line=1)')
    args = ap.parse_args()

    row = repair_row(args.run_id, args.line)
    print(json.dumps({'ok': True, 'run_id': args.run_id, 'line': args.line, 'updated_idx': row.get('idx')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
