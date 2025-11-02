from __future__ import annotations
import csv
from pathlib import Path
from typing import Dict, Any, List, Tuple
from statistics import mean, stdev
from math import sqrt

import sys
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmark.report import (
    write_summary_csv,
    compute_inter_judge_by_topic_three,
    write_inter_judge_by_topic_csv_three,
    compute_inter_judge_by_topic_three_multi,
    write_inter_judge_by_topic_csv_three_multi,
)


def load_per_item(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open('r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f, skipinitialspace=True)
        # Normalize headers
        if reader.fieldnames:
            reader.fieldnames = [(fn or '').strip() for fn in reader.fieldnames]
        for r in reader:
            if not r:
                continue
            rows.append({(k or '').strip(): (v.strip() if isinstance(v, str) else v) for k, v in r.items()})
    return rows


def verdict_score(hw_type: str, verdict: str) -> float:
    """MCQ-only verdict mapping; non-MCQ types return 0.0 by design."""
    v = (verdict or '').strip().lower()
    if hw_type != 'mcq':
        return 0.0
    if v == 'correct':
        return 1.0
    if v == 'ambiguous':
        return 0.5
    if v == 'incorrect':
        return 0.0
    return 0.0


def compute_summary_for_judge(per_rows: List[Dict[str, Any]], judge_prefix: str) -> List[Dict[str, Any]]:
    """Aggregate per (config, topic, type, seed) using {judge_prefix}_verdict -> score.
    judge_prefix in {'judge_gemini','judge_claude','judge_deepseek'}
    """
    groups: Dict[Tuple[str, str, str, str], List[float]] = {}
    run_id = per_rows[0].get('run_id', '') if per_rows else ''

    for r in per_rows:
        config = str(r.get('config','')).strip()
        topic = str(r.get('topic','')).strip()
        hw_type = str(r.get('type','')).strip()
        seed = str(r.get('seed','')).strip()
        if not (config and topic and hw_type and seed):
            continue
        verdict = str(r.get(f'{judge_prefix}_verdict','')).strip()
        if not verdict:
            continue
        s = verdict_score(hw_type, verdict)
        key = (config, topic, hw_type, seed)
        groups.setdefault(key, []).append(s)

    out: List[Dict[str, Any]] = []
    for (config, topic, hw_type, seed), scores in sorted(groups.items()):
        n = len(scores)
        if n == 0:
            continue
        j_mean = mean(scores)
        j_std = stdev(scores) if n > 1 else 0.0
        j_se = (j_std / sqrt(n)) if n > 1 else 0.0
        j_ci = 1.96 * j_se
        row = {
            'run_id': run_id,
            'config': config,
            'topic': topic,
            'type': hw_type,
            'seed': seed,
            'n_items': n,
            'structural_pass_pct': '',
            'semantic_mean': '',
            'semantic_std': '',
            'semantic_se': '',
            'semantic_ci95_low': '',
            'semantic_ci95_high': '',
            'judge_mean': round(j_mean, 4),
            'judge_std': round(j_std, 4),
            'judge_se': round(j_se, 4),
            'judge_ci95_low': round(j_mean - j_ci, 4),
            'judge_ci95_high': round(j_mean + j_ci, 4),
            'judge2_mean': '',
            'judge2_std': '',
            'judge2_se': '',
            'judge2_ci95_low': '',
            'judge2_ci95_high': '',
        }
        out.append(row)
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser(description='Compute CSVs for triple-judge report: per-judge summaries and inter-judge pairwise stats.')
    ap.add_argument('--run-id', required=True, help='Report run id (folder under benchmark/reports)')
    args = ap.parse_args()

    run_dir = Path(f"benchmark/reports/{args.run_id}")
    per_item_csv = run_dir / 'per_item.csv'
    if not per_item_csv.exists():
        raise SystemExit(f"per_item.csv not found in {run_dir}")

    per_rows = [r for r in load_per_item(per_item_csv) if str(r.get('type','')).strip() == 'mcq']

    # Compute per-judge summaries
    for judge in ('judge_gemini', 'judge_claude', 'judge_deepseek'):
        rows = compute_summary_for_judge(per_rows, judge)
        out_csv = run_dir / f'summary_{judge.replace("judge_", "")}.csv'
        write_summary_csv(out_csv, rows)
        print(f"Wrote {len(rows)} rows -> {out_csv}")

    # Compute inter-judge pairwise by (type, topic)
    inter_rows = compute_inter_judge_by_topic_three(per_rows)
    inter_csv = run_dir / 'inter_judge_by_topic_three.csv'
    write_inter_judge_by_topic_csv_three(inter_csv, inter_rows)
    print(f"Wrote {len(inter_rows)} rows -> {inter_csv}")

    # Compute inter-judge multi-rater (3 judges) by (type, topic)
    inter_multi_rows = compute_inter_judge_by_topic_three_multi(per_rows)
    inter_multi_csv = run_dir / 'inter_judge_by_topic_three_multi.csv'
    write_inter_judge_by_topic_csv_three_multi(inter_multi_csv, inter_multi_rows)
    print(f"Wrote {len(inter_multi_rows)} rows -> {inter_multi_csv}")


if __name__ == '__main__':
    main()
