from __future__ import annotations
import csv
import json
from pathlib import Path
from typing import List, Dict, Any
import os


def write_summary_csv(path: Path, rows: List[Dict[str, Any]]):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    keys = [
        'run_id','config','topic','type','seed','n_items','structural_pass_pct',
        'semantic_mean','semantic_std','semantic_se','semantic_ci95_low','semantic_ci95_high',
        'judge_mean','judge_std','judge_se','judge_ci95_low','judge_ci95_high'
    ]
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, '') for k in keys})


def write_per_item_csv(path: Path, rows: List[Dict[str, Any]]):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    keys = [
        'run_id','config','topic','type','seed','source_text_sha','idx','qid_gold','qid_pred','structural_valid',
        'prompt_sim','ans_sim','distractor_diversity','ans_score','item_score',
        'judge_verdict','judge_score','judge_why'
    ]
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, '') for k in keys})


def write_jsonl(path: Path, rows: List[Dict[str, Any]]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


# ============
# Append/streaming variants for resilience
# ============
def _append_csv_rows(path: Path, keys: List[str], rows: List[Dict[str, Any]]):
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = path.exists() and path.stat().st_size > 0
    with path.open('a', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=keys)
        if not file_exists:
            w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, '') for k in keys})


def append_summary_rows(path: Path, rows: List[Dict[str, Any]]):
    keys = [
        'run_id','config','topic','type','seed','n_items','structural_pass_pct',
        'semantic_mean','semantic_std','semantic_se','semantic_ci95_low','semantic_ci95_high',
        'judge_mean','judge_std','judge_se','judge_ci95_low','judge_ci95_high'
    ]
    _append_csv_rows(path, keys, rows)


def append_per_item_rows(path: Path, rows: List[Dict[str, Any]]):
    keys = [
        'run_id','config','topic','type','seed','source_text_sha','idx','qid_gold','qid_pred','structural_valid',
        'prompt_sim','ans_sim','distractor_diversity','ans_score','item_score',
        'judge_verdict','judge_score','judge_why'
    ]
    _append_csv_rows(path, keys, rows)


def append_jsonl(path: Path, rows: List[Dict[str, Any]]):
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def write_paired_overall_csv(path: Path, rows: List[Dict[str, Any]]):
    """Write Δ ± CI per metric (semantic/judge) aggregated across paired sources.
    Expected row keys: run_id, metric, n_pairs, delta_mean, delta_std, delta_se, delta_ci95_low, delta_ci95_high
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    keys = [
        'run_id','metric','n_pairs',
        'delta_mean','delta_std','delta_se',
        'delta_ci95_low','delta_ci95_high','delta_ci95_halfwidth_H','delta_ci_level',
        'delta_H_target','delta_meets_H_target',
        'delta_significant'
    ]
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, '') for k in keys})


def write_winloss_csv(path: Path, rows: List[Dict[str, Any]]):
    """Write win/loss/tie and binomial p-value summary per run.
    Expected row keys: run_id, semantic_wins, semantic_losses, semantic_ties, semantic_win_rate, semantic_binomial_p,
                       judge_wins, judge_losses, judge_ties, judge_win_rate, judge_binomial_p
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    keys = [
        'run_id',
        'semantic_wins','semantic_losses','semantic_ties','semantic_n_effective','semantic_win_rate','semantic_binomial_p',
        'judge_wins','judge_losses','judge_ties','judge_n_effective','judge_win_rate','judge_binomial_p'
    ]
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, '') for k in keys})
