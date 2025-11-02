from __future__ import annotations
import csv
import json
import re
from pathlib import Path
from typing import Dict, Any, List, Tuple
from statistics import mean, stdev
from math import sqrt

import sys
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmark.score import mcq_semantics, fill_semantics
from benchmark.validate import validate_items
from benchmark.report import write_per_item_csv, write_summary_csv, write_paired_overall_csv, write_winloss_csv


def safe_topic(topic: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", topic)


def load_csv(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open('r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f, skipinitialspace=True)
        if reader.fieldnames:
            reader.fieldnames = [(fn or '').strip() for fn in reader.fieldnames]
        for r in reader:
            if r is None:
                continue
            rows.append({(k or '').strip(): (v.strip() if isinstance(v, str) else v) for k, v in r.items()})
    return rows


def verdict_to_score(hw_type: str, verdict: str) -> float:
    v = (verdict or '').strip().lower()
    if hw_type == 'mcq':
        return {'correct':1.0, 'ambiguous':0.5, 'incorrect':0.0}.get(v, 0.0)
    else:
        return {'acceptable':1.0, 'unacceptable':0.0}.get(v, 0.0)


def backfill_per_item(run_dir: Path) -> List[Dict[str, Any]]:
    per_item_csv = run_dir / 'per_item.csv'
    rows = load_csv(per_item_csv)

    # Group by (config, topic, type, seed, sha) to load pred/gold once
    groups: Dict[Tuple[str,str,str,str,str], List[int]] = {}
    for i, r in enumerate(rows):
        key = (
            str(r.get('config','')).strip(),
            str(r.get('topic','')).strip(),
            str(r.get('type','')).strip(),
            str(r.get('seed','')).strip(),
            str(r.get('source_text_sha','')).strip(),
        )
        groups.setdefault(key, []).append(i)

    for (config, topic, hw_type, seed, sha), idxs in groups.items():
        if not (config and topic and hw_type and seed and sha):
            continue
        st = safe_topic(topic)
        pred_path = Path(f"benchmark/pred/{config}/{st}/{hw_type}/{sha}/seed{seed}.json")
        gold_path = Path(f"benchmark/gold/{st}/{hw_type}/{sha}/seed0.json")
        pred = json.loads(pred_path.read_text(encoding='utf-8')) if pred_path.exists() else []
        gold = json.loads(gold_path.read_text(encoding='utf-8')) if gold_path.exists() else []

        # Structural validation to mark invalid indices from pred
        ok_pred, errs_pred, _ = validate_items(pred, hw_type, expected_count=None)
        invalid_idx_pred = set()
        for e in errs_pred:
            if isinstance(e, str) and e.startswith('i') and ':' in e:
                try:
                    idx_str = e[1:e.index(':')]
                    ii = int(idx_str)
                    invalid_idx_pred.add(ii)
                except Exception:
                    pass

        for i in idxs:
            r = rows[i]
            try:
                idx = int(str(r.get('idx','')).strip() or '0')
            except Exception:
                continue
            if idx <= 0:
                continue
            pi = pred[idx-1] if idx-1 < len(pred) else {}
            gi = gold[idx-1] if idx-1 < len(gold) else {}

            # structural_valid
            r['structural_valid'] = 0 if (idx in invalid_idx_pred) else 1

            # semantics
            if hw_type == 'mcq' and pi and gi:
                ps, ans, div, item = mcq_semantics(pi, gi)
                r['question_sim'] = round(ps, 4)
                r['ans_sim'] = ('' if ans is None else round(ans, 4))
                r['distractor_diversity'] = round(div, 4)
                r['ans_score'] = ('' if ans is None else round(ans, 4))
                r['item_score'] = round(item, 4)
            elif hw_type == 'fill' and pi and gi:
                ps, ans, item = fill_semantics(pi, gi)
                r['question_sim'] = round(ps, 4)
                r['ans_sim'] = round(ans, 4)
                r['distractor_diversity'] = ''
                r['ans_score'] = round(ans, 4)
                r['item_score'] = round(item, 4)

            # Map primary judge columns from Gemini for compatibility with paired_overall
            if not str(r.get('judge_verdict','')).strip():
                r['judge_verdict'] = r.get('judge_gemini_verdict','')
            try:
                r['judge_score'] = round(float(verdict_to_score(hw_type, r.get('judge_verdict',''))), 4)
            except Exception:
                r['judge_score'] = ''

            rows[i] = r

    # Write back
    write_per_item_csv(per_item_csv, rows)
    return rows


def recompute_summary_and_pairs(run_dir: Path, rows: List[Dict[str, Any]]):
    # Summary per (config, topic, type, seed)
    from scripts.recompute_reports import compute_group_stats
    summary_rows = compute_group_stats(rows)
    write_summary_csv(run_dir / 'summary.csv', summary_rows)

    # Paired deltas & winloss between minimal and cot at (sha, topic, type, seed)
    # Build map similar to benchmark/run_benchmark.py
    groups: Dict[Tuple[str,str,str,str], Dict[str, Dict[str, float]]] = {}
    for r in rows:
        sha = str(r.get('source_text_sha','')).strip()
        topic = str(r.get('topic','')).strip()
        hw_type = str(r.get('type','')).strip()
        seed = str(r.get('seed','')).strip()
        config = str(r.get('config','')).strip()
        if not (sha and topic and hw_type and seed and config):
            continue
        try:
            item_score = float(r.get('item_score','')) if str(r.get('item_score','')).strip() != '' else None
            judge_score = float(r.get('judge_score','')) if str(r.get('judge_score','')).strip() != '' else None
        except Exception:
            item_score = None
            judge_score = None
        key = (sha, topic, hw_type, seed)
        groups.setdefault(key, {})
        if config not in groups[key]:
            groups[key][config] = {'semantic_sum':0.0, 'semantic_n':0, 'judge_sum':0.0, 'judge_n':0}
        if item_score is not None:
            groups[key][config]['semantic_sum'] += item_score
            groups[key][config]['semantic_n'] += 1
        if judge_score is not None:
            groups[key][config]['judge_sum'] += judge_score
            groups[key][config]['judge_n'] += 1

    deltas_sem: List[float] = []
    deltas_j: List[float] = []
    s_w = s_l = s_t = 0
    j_w = j_l = j_t = 0
    for pair_key, cfgmap in groups.items():
        if 'minimal' in cfgmap and 'cot' in cfgmap:
            def avg(d: Dict[str,float], s: str, n: str) -> float:
                return (d.get(s,0.0) / d.get(n,1)) if d.get(n,0) > 0 else 0.0
            min_sem = avg(cfgmap['minimal'], 'semantic_sum', 'semantic_n')
            cot_sem = avg(cfgmap['cot'], 'semantic_sum', 'semantic_n')
            min_j = avg(cfgmap['minimal'], 'judge_sum', 'judge_n')
            cot_j = avg(cfgmap['cot'], 'judge_sum', 'judge_n')
            d_sem = cot_sem - min_sem
            d_j = cot_j - min_j
            deltas_sem.append(d_sem)
            deltas_j.append(d_j)
            eps = 1e-12
            if d_sem > eps:
                s_w += 1
            elif d_sem < -eps:
                s_l += 1
            else:
                s_t += 1
            if d_j > eps:
                j_w += 1
            elif d_j < -eps:
                j_l += 1
            else:
                # tiebreak by semantic
                eps_sem = 1e-6
                if d_sem > eps_sem:
                    j_w += 1
                elif d_sem < -eps_sem:
                    j_l += 1
                else:
                    j_t += 1

    def ci_stats(arr: List[float]) -> Dict[str, float]:
        if not arr:
            return dict(mean=0.0, std=0.0, se=0.0, low=0.0, high=0.0)
        m = mean(arr)
        sd = stdev(arr) if len(arr) > 1 else 0.0
        se = (sd / sqrt(len(arr))) if len(arr) > 1 else 0.0
        low = max(-1.0, m - 1.96 * se)
        high = min(1.0, m + 1.96 * se)
        return dict(mean=m, std=sd, se=se, low=low, high=high)

    s_stats = ci_stats(deltas_sem)
    j_stats = ci_stats(deltas_j)
    s_H = max(0.0, (s_stats['high'] - s_stats['low'])/2.0)
    j_H = max(0.0, (j_stats['high'] - j_stats['low'])/2.0)
    paired_rows = [
        {
            'run_id': rows[0].get('run_id','') if rows else '',
            'metric': 'semantic',
            'n_pairs': len(deltas_sem),
            'delta_mean': round(s_stats['mean'], 4),
            'delta_std': round(s_stats['std'], 4),
            'delta_se': round(s_stats['se'], 4),
            'delta_ci95_low': round(s_stats['low'], 4),
            'delta_ci95_high': round(s_stats['high'], 4),
            'delta_ci95_halfwidth_H': round(s_H, 4),
            'delta_ci_level': 0.95,
            'delta_H_target': 0.04,
            'delta_meets_H_target': 1 if s_H <= 0.04 else 0,
            'delta_significant': 1 if (s_stats['low'] > 0.0 or s_stats['high'] < 0.0) else 0,
        },
        {
            'run_id': rows[0].get('run_id','') if rows else '',
            'metric': 'judge',
            'n_pairs': len(deltas_j),
            'delta_mean': round(j_stats['mean'], 4),
            'delta_std': round(j_stats['std'], 4),
            'delta_se': round(j_stats['se'], 4),
            'delta_ci95_low': round(j_stats['low'], 4),
            'delta_ci95_high': round(j_stats['high'], 4),
            'delta_ci95_halfwidth_H': round(j_H, 4),
            'delta_ci_level': 0.95,
            'delta_H_target': 0.05,
            'delta_meets_H_target': 1 if j_H <= 0.05 else 0,
            'delta_significant': 1 if (j_stats['low'] > 0.0 or j_stats['high'] < 0.0) else 0,
        },
    ]
    write_paired_overall_csv(run_dir / 'paired_overall.csv', paired_rows)

    # Winloss
    def compute_binom_p_two_sided(wins: int, losses: int) -> float:
        import math
        n = wins + losses
        if n == 0:
            return 1.0
        k = wins
        def pmf(i: int) -> float:
            return math.comb(n, i) * (0.5 ** n)
        def cdf(i: int) -> float:
            return sum(pmf(j) for j in range(0, i+1))
        c_low = cdf(k)
        c_high = 1.0 - cdf(k-1) if k > 0 else 1.0
        p = 2.0 * min(c_low, c_high)
        return min(max(p, 0.0), 1.0)

    s_n_eff = s_w + s_l
    j_n_eff = j_w + j_l
    s_rate = (s_w / s_n_eff) if s_n_eff > 0 else 0.0
    j_rate = (j_w / j_n_eff) if j_n_eff > 0 else 0.0
    s_p = compute_binom_p_two_sided(s_w, s_l)
    j_p = compute_binom_p_two_sided(j_w, j_l)
    winloss_rows = [{
        'run_id': rows[0].get('run_id','') if rows else '',
        'semantic_wins': s_w,
        'semantic_losses': s_l,
        'semantic_ties': s_t,
        'semantic_n_effective': s_n_eff,
        'semantic_win_rate': round(s_rate, 4),
        'semantic_binomial_p': round(s_p, 6),
        'judge_wins': j_w,
        'judge_losses': j_l,
        'judge_ties': j_t,
        'judge_n_effective': j_n_eff,
        'judge_win_rate': round(j_rate, 4),
        'judge_binomial_p': round(j_p, 6),
    }]
    write_winloss_csv(run_dir / 'winloss.csv', winloss_rows)


def main():
    import argparse
    ap = argparse.ArgumentParser(description='Backfill per_item.csv with structural/semantic metrics for triple-judge runs and compute paired_overall/winloss/summary.')
    ap.add_argument('--run-id', required=True, help='Report run id (folder under benchmark/reports)')
    args = ap.parse_args()

    run_dir = Path(f"benchmark/reports/{args.run_id}")
    if not (run_dir / 'per_item.csv').exists():
        raise SystemExit(f"per_item.csv not found in {run_dir}")

    rows = backfill_per_item(run_dir)
    recompute_summary_and_pairs(run_dir, rows)
    print(f"Backfilled per_item + recomputed summary/paired_overall/winloss for run {args.run_id}")


if __name__ == '__main__':
    main()
