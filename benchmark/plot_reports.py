from __future__ import annotations
import argparse
import csv
import os
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from math import sqrt


def find_latest_reports_dir(base: Path) -> Optional[Path]:
    if not base.exists():
        return None
    dirs = [p for p in base.iterdir() if p.is_dir()]
    if not dirs:
        return None
    # Prefer by modified time, fallback to name sort
    dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return dirs[0]


def read_summary_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding='utf-8') as f:
        return list(csv.DictReader(f))


def _to_float(d: Dict[str, str], k: str, default: float = 0.0) -> float:
    try:
        return float(d.get(k, default))
    except Exception:
        return default


def _filter_rows(rows: List[Dict[str, str]], topic: Optional[str], hw_type: Optional[str]) -> List[Dict[str, str]]:
    out = []
    for r in rows:
        if topic and r.get('topic') != topic:
            continue
        if hw_type and r.get('type') != hw_type:
            continue
        out.append(r)
    return out


def _group_by_config(rows: List[Dict[str, str]]) -> Dict[str, List[Dict[str, str]]]:
    g: Dict[str, List[Dict[str, str]]] = {}
    for r in rows:
        g.setdefault(r.get('config','unknown'), []).append(r)
    return g


def _compute_group_agg(values: List[float]) -> Tuple[float, float]:
    # mean and 95% CI width for run-level means (normal approx)
    if not values:
        return 0.0, 0.0
    m = sum(values) / len(values)
    if len(values) == 1:
        return m, 0.0
    var = sum((v - m) ** 2 for v in values) / (len(values) - 1)
    std = var ** 0.5
    se = std / sqrt(len(values))
    ci = 1.96 * se
    return m, ci


def plot_error_bars_per_seed(out_dir: Path, grouped: Dict[str, List[Dict[str, str]]], metric: str):
    try:
        import matplotlib.pyplot as plt
    except Exception:
        print("matplotlib is not installed. Please install it: pip install matplotlib")
        return

    # Build per-seed points with CI half-width from row
    configs = sorted(grouped.keys())
    xs = []
    ys = []
    yerr = []
    labels = []
    for cfg in configs:
        for r in sorted(grouped[cfg], key=lambda r: int(r.get('seed', '0'))):
            mean_k = f"{metric}_mean"
            low_k = f"{metric}_ci95_low"
            high_k = f"{metric}_ci95_high"
            m = _to_float(r, mean_k)
            lo = _to_float(r, low_k, m)
            hi = _to_float(r, high_k, m)
            hw = max(0.0, (hi - lo) / 2)
            if hw == 0.0:
                # Fallback if CI fields missing: use std and n_items if present
                std_k = f"{metric}_std"
                std = _to_float(r, std_k, 0.0)
                n_items = max(1, int(r.get('n_items', '0') or 0))
                if n_items > 1 and std > 0:
                    from math import sqrt
                    hw = 1.96 * std / sqrt(n_items)
            xs.append(cfg)
            ys.append(m)
            yerr.append(hw)
            labels.append(f"{cfg} (seed {r.get('seed','')})")

    fig, ax = plt.subplots(figsize=(max(6, len(xs)*0.4), 5))
    xpos = list(range(len(xs)))
    ax.errorbar(xpos, ys, yerr=yerr, fmt='o', ecolor='tab:blue', capsize=4, color='tab:blue')
    ax.set_xticks(xpos)
    ax.set_xticklabels(labels, rotation=45, ha='right')
    ax.set_ylabel(metric)
    ax.set_title(f"{metric} mean with 95% CI (per seed)")
    fig.tight_layout()
    out_path = out_dir / f"{metric}_per_seed_errorbars.png"
    fig.savefig(out_path, dpi=160)
    plt.close(fig)
    print(f"Wrote: {out_path}")


def plot_bars_agg_by_config(out_dir: Path, grouped: Dict[str, List[Dict[str, str]]], metric: str):
    try:
        import matplotlib.pyplot as plt
    except Exception:
        print("matplotlib is not installed. Please install it: pip install matplotlib")
        return

    cfgs = sorted(grouped.keys())
    means = []
    ci = []
    for cfg in cfgs:
        vals = [_to_float(r, f"{metric}_mean") for r in grouped[cfg]]
        m, c = _compute_group_agg(vals)
        means.append(m)
        ci.append(c)

    fig, ax = plt.subplots(figsize=(max(6, len(cfgs)*0.8), 5))
    xpos = list(range(len(cfgs)))
    ax.bar(xpos, means, yerr=ci, capsize=5, color='tab:orange', alpha=0.9)
    ax.set_xticks(xpos)
    ax.set_xticklabels(cfgs, rotation=20, ha='right')
    ax.set_ylabel(metric)
    ax.set_title(f"{metric} mean by config with 95% CI (across seeds)")
    fig.tight_layout()
    out_path = out_dir / f"{metric}_by_config_agg.png"
    fig.savefig(out_path, dpi=160)
    plt.close(fig)
    print(f"Wrote: {out_path}")


def main():
    ap = argparse.ArgumentParser(description="Plot benchmark summary with error bars and comparisons.")
    ap.add_argument('--reports-root', default='benchmark/reports', help='Root folder of reports')
    ap.add_argument('--run-id', help='Specific run id under reports; defaults to latest if omitted')
    ap.add_argument('--topic', help='Filter by topic (optional)')
    ap.add_argument('--type', dest='hw_type', help='Filter by type: mcq|fill (optional)')
    ap.add_argument('--metric', choices=['semantic','judge'], default='semantic')
    args = ap.parse_args()

    reports_root = Path(args.reports_root)
    run_dir = Path(reports_root / args.run_id) if args.run_id else find_latest_reports_dir(reports_root)
    if not run_dir:
        print("No reports directory found.")
        return
    summary_path = run_dir / 'summary.csv'
    rows = read_summary_csv(summary_path)
    if not rows:
        print(f"No summary.csv at {summary_path}")
        return

    rows = _filter_rows(rows, args.topic, args.hw_type)
    if not rows:
        print("No rows after filtering. Check --topic/--type filters.")
        return

    grouped = _group_by_config(rows)
    figs_dir = run_dir / 'figures'
    figs_dir.mkdir(parents=True, exist_ok=True)

    # Per-seed error bars using per-row CI
    plot_error_bars_per_seed(figs_dir, grouped, args.metric)
    # Aggregated across seeds by config
    plot_bars_agg_by_config(figs_dir, grouped, args.metric)

    print(f"Figures saved under: {figs_dir}")


if __name__ == '__main__':
    main()
