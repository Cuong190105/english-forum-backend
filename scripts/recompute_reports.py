from __future__ import annotations
import os
import sys
import csv
import json
import argparse
from pathlib import Path
from typing import Dict, Any, List, Tuple


def _ensure_repo_root_on_path() -> None:
    try:
        here = Path(__file__).resolve()
        repo_root = here.parent.parent  # scripts/ -> project root
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
    except Exception:
        pass


_ensure_repo_root_on_path()


def load_env(dotenv_path: str | None):
    try:
        from dotenv import load_dotenv  # type: ignore
        if dotenv_path and Path(dotenv_path).exists():
            load_dotenv(dotenv_path)
        else:
            load_dotenv()
    except Exception:
        pass


def compute_group_stats(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    from statistics import mean, stdev
    from math import sqrt

    def clamp01(x: float) -> float:
        return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x

    groups: Dict[Tuple[str, str, str, str, str], List[Dict[str, Any]]] = {}
    for r in rows:
        key = (r.get('run_id',''), r.get('config',''), r.get('topic',''), r.get('type',''), str(r.get('seed','')))
        groups.setdefault(key, []).append(r)

    out: List[Dict[str, Any]] = []
    for (run_id, config, topic, hw_type, seed), arr in groups.items():
        n_items = len(arr)
        try:
            n_struct_pass = sum(int(x.get('structural_valid') or 0) for x in arr)
        except Exception:
            n_struct_pass = 0
        structural_pass_pct = (100.0 * n_struct_pass / n_items) if n_items > 0 else 0.0

        sem_vals = [float(x['item_score']) for x in arr if str(x.get('item_score','')).strip() != '']
        sem_mean = mean(sem_vals) if sem_vals else 0.0
        sem_std = stdev(sem_vals) if len(sem_vals) > 1 else 0.0
        sem_se = (sem_std / sqrt(n_items)) if n_items > 1 else 0.0
        sem_ci_low = clamp01(sem_mean - 1.96 * sem_se)
        sem_ci_high = clamp01(sem_mean + 1.96 * sem_se)

        j1_vals = [float(x['judge_score']) for x in arr if str(x.get('judge_score','')).strip() != '']
        j1_mean = mean(j1_vals) if j1_vals else 0.0
        j1_std = stdev(j1_vals) if len(j1_vals) > 1 else 0.0
        j1_se = (j1_std / sqrt(n_items)) if n_items > 1 else 0.0
        j1_ci_low = clamp01(j1_mean - 1.96 * j1_se)
        j1_ci_high = clamp01(j1_mean + 1.96 * j1_se)

        j2_vals = [float(x['judge2_score']) for x in arr if str(x.get('judge2_score','')).strip() != '']
        has_j2 = len(j2_vals) > 0
        if has_j2:
            j2_mean = mean(j2_vals) if j2_vals else 0.0
            j2_std = stdev(j2_vals) if len(j2_vals) > 1 else 0.0
            j2_se = (j2_std / sqrt(n_items)) if n_items > 1 else 0.0
            j2_ci_low = clamp01(j2_mean - 1.96 * j2_se)
            j2_ci_high = clamp01(j2_mean + 1.96 * j2_se)
        else:
            j2_mean = j2_std = j2_se = j2_ci_low = j2_ci_high = ''

        out.append({
            'run_id': run_id,
            'config': config,
            'topic': topic,
            'type': hw_type,
            'seed': int(seed) if str(seed).isdigit() else seed,
            'n_items': n_items,
            'structural_pass_pct': round(structural_pass_pct, 2),
            'semantic_mean': round(sem_mean, 4),
            'semantic_std': round(sem_std, 4),
            'semantic_se': round(sem_se, 4),
            'semantic_ci95_low': round(sem_ci_low, 4),
            'semantic_ci95_high': round(sem_ci_high, 4),
            'judge_mean': round(j1_mean, 4),
            'judge_std': round(j1_std, 4),
            'judge_se': round(j1_se, 4),
            'judge_ci95_low': round(j1_ci_low, 4),
            'judge_ci95_high': round(j1_ci_high, 4),
            'judge2_mean': ('' if not has_j2 else round(j2_mean, 4)),
            'judge2_std': ('' if not has_j2 else round(j2_std, 4)),
            'judge2_se': ('' if not has_j2 else round(j2_se, 4)),
            'judge2_ci95_low': ('' if not has_j2 else round(j2_ci_low, 4)),
            'judge2_ci95_high': ('' if not has_j2 else round(j2_ci_high, 4)),
        })
    return out


def compute_inter_judge(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    from collections import Counter
    def _wilson_ci(p_hat: float, n: int, z: float = 1.96) -> Tuple[float, float]:
        if n <= 0:
            return (0.0, 0.0)
        denom = 1.0 + (z*z)/n
        center = (p_hat + (z*z)/(2.0*n)) / denom
        import math
        half = z * math.sqrt(max(p_hat*(1.0 - p_hat)/n + (z*z)/(4.0*n*n), 0.0)) / denom
        low = max(0.0, center - half)
        high = min(1.0, center + half)
        return (low, high)

    def stats_for(pairs: List[Tuple[str, str]], classes: List[str]):
        n = len(pairs)
        if n == 0:
            return dict(n=0, pa=0.0, pa_low=0.0, pa_high=0.0, kappa=0.0, ac1=0.0)
        po = sum(1 for a,b in pairs if a == b) / n
        a_counts = Counter(a for a,_ in pairs)
        b_counts = Counter(b for _,b in pairs)
        pe = 0.0
        for c in classes:
            pa_c = a_counts.get(c,0)/n
            pb_c = b_counts.get(c,0)/n
            pe += pa_c * pb_c
        k = 0.0 if (1.0 - pe) == 0 else (po - pe) / (1.0 - pe)
        # Gwet's AC1 expected agreement using pooled category proportions
        # Ae_AC1 = [sum_c p_c * (1 - p_c)] / (Q - 1)
        total_ratings = 2.0 * n
        pe1 = 0.0
        if total_ratings > 0:
            for c in classes:
                p_c = (a_counts.get(c,0) + b_counts.get(c,0)) / total_ratings
                pe1 += p_c * (1.0 - p_c)
        Q = max(1, len(classes))
        denom = max(1, Q - 1)
        pe1 = pe1 / denom
        ac1 = 0.0 if (1.0 - pe1) == 0 else (po - pe1) / (1.0 - pe1)
        low, high = _wilson_ci(po, n)
        return dict(n=n, pa=po, pa_low=low, pa_high=high, kappa=k, ac1=ac1)

    out: List[Dict[str, Any]] = []
    for hw_type in ['mcq','fill']:
        pairs: List[Tuple[str,str]] = []
        for r in rows:
            if r.get('type') != hw_type:
                continue
            a = str(r.get('judge_verdict','')).lower()
            b = str(r.get('judge2_verdict','')).lower()
            if a and b and a != 'error' and b != 'error':
                pairs.append((a,b))
        if not pairs:
            continue
        classes = ['correct','ambiguous','incorrect'] if hw_type == 'mcq' else ['acceptable','unacceptable']
        st = stats_for(pairs, classes)
        out.append({
            'run_id': rows[0].get('run_id',''),
            'type': hw_type,
            'n': st['n'],
            'percent_agreement': round(st['pa'],4),
            'pa_ci95_low': round(st['pa_low'],4),
            'pa_ci95_high': round(st['pa_high'],4),
            'kappa': round(st['kappa'],4),
            'ac1': round(st['ac1'],4),
        })
    return out


def load_per_item(per_item_csv: Path) -> List[Dict[str, Any]]:
    with per_item_csv.open('r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f, skipinitialspace=True)
        if reader.fieldnames:
            reader.fieldnames = [(fn or '').strip() for fn in reader.fieldnames]
        rows: List[Dict[str, Any]] = []
        for r in reader:
            if r is None:
                continue
            norm: Dict[str, Any] = {}
            for k, v in r.items():
                kk = (k or '').strip()
                if isinstance(v, str):
                    vv = v.strip()
                else:
                    vv = v
                norm[kk] = vv
            if not any(str(v).strip() for v in norm.values()):
                continue
            rows.append(norm)
        return rows


def main():
    ap = argparse.ArgumentParser(description='Recompute summary.csv and inter_judge.csv from an existing per_item.csv.')
    ap.add_argument('--run-id', help='Run id folder name under benchmark/reports')
    ap.add_argument('--run-dir', help='Explicit path to reports dir (overrides --run-id)')
    ap.add_argument('--dotenv', default='.env', help='Path to .env to load (optional)')
    ap.add_argument('--verbose', action='store_true', help='Verbose logging')
    args = ap.parse_args()

    load_env(args.dotenv)

    if not args.run_dir and not args.run_id:
        ap.error('Provide --run-id or --run-dir')
    run_dir = Path(args.run_dir) if args.run_dir else Path('benchmark/reports') / args.run_id  # type: ignore[arg-type]
    per_item_csv = run_dir / 'per_item.csv'
    summary_csv = run_dir / 'summary.csv'
    inter_judge_csv = run_dir / 'inter_judge.csv'

    if not per_item_csv.exists():
        raise FileNotFoundError(f'per_item.csv not found at {per_item_csv}')

    rows = load_per_item(per_item_csv)
    if args.verbose:
        print(f"[recompute] loaded rows={len(rows)} from {per_item_csv}")

    summary_rows = compute_group_stats(rows)
    if args.verbose:
        print(f"[recompute] summary groups={len(summary_rows)} to {summary_csv}")

    try:
        from benchmark.report import write_summary_csv, write_inter_judge_csv, compute_inter_judge_by_topic, write_inter_judge_by_topic_csv
        write_summary_csv(summary_csv, summary_rows)
    except Exception:
        # Minimal fallback writer
        with summary_csv.open('w', encoding='utf-8', newline='') as f:
            if summary_rows:
                keys = list(summary_rows[0].keys())
                w = csv.DictWriter(f, fieldnames=keys)
                w.writeheader()
                for r in summary_rows:
                    w.writerow(r)

    ij_rows = compute_inter_judge(rows)
    if args.verbose:
        print(f"[recompute] inter-judge rows={len(ij_rows)} to {inter_judge_csv}")

    try:
        from benchmark.report import write_inter_judge_csv, compute_inter_judge_by_topic, write_inter_judge_by_topic_csv
        if ij_rows:
            write_inter_judge_csv(inter_judge_csv, ij_rows)
        else:
            # Create empty file with header
            with inter_judge_csv.open('w', encoding='utf-8', newline='') as f:
                w = csv.DictWriter(f, fieldnames=['run_id','type','n','percent_agreement','pa_ci95_low','pa_ci95_high','kappa','ac1'])
                w.writeheader()
        # Also compute inter-judge by topic
        ij_topic_rows = compute_inter_judge_by_topic(rows)
        inter_by_topic_csv = run_dir / 'inter_judge_by_topic.csv'
        if ij_topic_rows:
            write_inter_judge_by_topic_csv(inter_by_topic_csv, ij_topic_rows)
        else:
            with inter_by_topic_csv.open('w', encoding='utf-8', newline='') as f:
                w = csv.DictWriter(f, fieldnames=['run_id','type','topic','n','percent_agreement','pa_ci95_low','pa_ci95_high','kappa','ac1'])
                w.writeheader()
    except Exception:
        with inter_judge_csv.open('w', encoding='utf-8', newline='') as f:
            if ij_rows:
                keys = list(ij_rows[0].keys())
                w = csv.DictWriter(f, fieldnames=keys)
                w.writeheader()
                for r in ij_rows:
                    w.writerow(r)
            else:
                w = csv.DictWriter(f, fieldnames=['run_id','type','n','percent_agreement','pa_ci95_low','pa_ci95_high','kappa','ac1'])
                w.writeheader()
        # best-effort for by-topic
        inter_by_topic_csv = run_dir / 'inter_judge_by_topic.csv'
        try:
            ij_topic_rows = compute_inter_judge_by_topic(rows)
            if ij_topic_rows:
                keys = ['run_id','type','topic','n','percent_agreement','pa_ci95_low','pa_ci95_high','kappa','ac1']
                with inter_by_topic_csv.open('w', encoding='utf-8', newline='') as f:
                    w = csv.DictWriter(f, fieldnames=keys)
                    w.writeheader()
                    for r in ij_topic_rows:
                        w.writerow({k: r.get(k,'') for k in keys})
            else:
                with inter_by_topic_csv.open('w', encoding='utf-8', newline='') as f:
                    w = csv.DictWriter(f, fieldnames=['run_id','type','topic','n','percent_agreement','pa_ci95_low','pa_ci95_high','kappa','ac1'])
                    w.writeheader()
        except Exception:
            pass

    print(json.dumps({
        'status': 'ok',
        'run_dir': str(run_dir),
        'rows': len(rows),
        'summary_path': str(summary_csv),
        'inter_judge_path': str(inter_judge_csv),
        'inter_judge_by_topic_path': str((run_dir / 'inter_judge_by_topic.csv')),
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()
