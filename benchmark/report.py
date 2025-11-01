from __future__ import annotations
import csv
import json
from pathlib import Path
from typing import List, Dict, Any, Tuple
import os


def write_summary_csv(path: Path, rows: List[Dict[str, Any]]):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    keys = [
        'run_id','config','topic','type','seed','n_items','structural_pass_pct',
        'semantic_mean','semantic_std','semantic_se','semantic_ci95_low','semantic_ci95_high',
        'judge_mean','judge_std','judge_se','judge_ci95_low','judge_ci95_high',
        # Optional second judge metrics (if present)
        'judge2_mean','judge2_std','judge2_se','judge2_ci95_low','judge2_ci95_high'
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
    # Base keys from legacy two-judge pipeline
    keys = [
        'run_id','config','topic','type','seed','source_text_sha','idx','qid_gold','qid_pred','structural_valid',
        'question_sim','ans_sim','distractor_diversity','ans_score','item_score',
        'judge_verdict','judge_score','judge_why',
        'judge2_verdict','judge2_score','judge2_why',
        # Extended 3-judge fields (Gemini, Claude, DeepSeek) without latency
        'row_idx',
        'judge_gemini_verdict','judge_gemini_why',
        'judge_claude_verdict','judge_claude_why',
        'judge_deepseek_verdict','judge_deepseek_why',
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


def write_inter_judge_csv(path: Path, rows: List[Dict[str, Any]]):
    """Write inter-judge reliability per type and overall.
    Fields: run_id, type, n, percent_agreement, pa_ci95_low, pa_ci95_high, kappa, ac1
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    keys = ['run_id','type','n','percent_agreement','pa_ci95_low','pa_ci95_high','kappa','ac1']
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, '') for k in keys})


def compute_inter_judge_by_topic(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Compute inter-judge reliability grouped by (type, topic).
    Returns rows with: run_id, type, topic, n, percent_agreement, pa_ci95_low, pa_ci95_high, kappa, ac1
    """
    from collections import Counter, defaultdict

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
        # Gwet's AC1 (unweighted, nominal): use pooled category proportions p_c
        # p_c = (count_rater1(c) + count_rater2(c)) / (2n)
        # Expected agreement Ae_AC1 = [sum_c p_c * (1 - p_c)] / (Q - 1), where Q = number of classes
        # (for binary Q=2, the divisor is 1 so the formula reduces to sum_c p_c*(1-p_c) = 2p(1-p))
        # Then AC1 = (Po - Ae_AC1) / (1 - Ae_AC1)
        total_ratings = 2.0 * n
        pe1 = 0.0
        if total_ratings > 0:
            for c in classes:
                p_c = (a_counts.get(c,0) + b_counts.get(c,0)) / total_ratings
                pe1 += p_c * (1.0 - p_c)
        # Normalize by (Q - 1) for nominal AC1 (no effect for binary Q=2)
        Q = max(1, len(classes))
        denom = max(1, Q - 1)
        pe1 = pe1 / denom
        ac1 = 0.0 if (1.0 - pe1) == 0 else (po - pe1) / (1.0 - pe1)
        # 95% CI normal approx
        import math
        se = math.sqrt(max(po*(1-po)/n, 0.0))
        low = max(0.0, po - 1.96*se)
        high = min(1.0, po + 1.96*se)
        return dict(n=n, pa=po, pa_low=low, pa_high=high, kappa=k, ac1=ac1)

    grouped = defaultdict(list)  # (type, topic) -> list of pairs
    for r in rows:
        a = str(r.get('judge_verdict','')).lower()
        b = str(r.get('judge2_verdict','')).lower()
        hw_type = r.get('type')
        topic = r.get('topic')
        if not hw_type or not topic:
            continue
        if a and b and a != 'error' and b != 'error':
            grouped[(hw_type, topic)].append((a,b))

    out: List[Dict[str, Any]] = []
    for (hw_type, topic), pairs in grouped.items():
        if not pairs:
            continue
        classes = ['correct','ambiguous','incorrect'] if hw_type == 'mcq' else ['acceptable','unacceptable']
        st = stats_for(pairs, classes)
        out.append({
            'run_id': rows[0].get('run_id',''),
            'type': hw_type,
            'topic': topic,
            'n': st['n'],
            'percent_agreement': round(st['pa'],4),
            'pa_ci95_low': round(st['pa_low'],4),
            'pa_ci95_high': round(st['pa_high'],4),
            'kappa': round(st['kappa'],4),
            'ac1': round(st['ac1'],4),
        })
    return out


def write_inter_judge_by_topic_csv(path: Path, rows: List[Dict[str, Any]]):
    """Write inter-judge reliability grouped by (type, topic).
    Fields: run_id, type, topic, n, percent_agreement, pa_ci95_low, pa_ci95_high, kappa, ac1
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    keys = ['run_id','type','topic','n','percent_agreement','pa_ci95_low','pa_ci95_high','kappa','ac1']
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, '') for k in keys})


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
        'judge_mean','judge_std','judge_se','judge_ci95_low','judge_ci95_high',
        # Optional second judge metrics (if present)
        'judge2_mean','judge2_std','judge2_se','judge2_ci95_low','judge2_ci95_high'
    ]
    _append_csv_rows(path, keys, rows)


def append_per_item_rows(path: Path, rows: List[Dict[str, Any]]):
    keys = [
        'run_id','config','topic','type','seed','source_text_sha','idx','qid_gold','qid_pred','structural_valid',
        'question_sim','ans_sim','distractor_diversity','ans_score','item_score',
        'judge_verdict','judge_score','judge_why',
        'judge2_verdict','judge2_score','judge2_why',
        # Extended 3-judge fields (no latency)
        'row_idx',
        'judge_gemini_verdict','judge_gemini_why',
        'judge_claude_verdict','judge_claude_why',
        'judge_deepseek_verdict','judge_deepseek_why',
    ]
    _append_csv_rows(path, keys, rows)


# ===== 3-judge inter-reliability (pairwise) =====
def compute_inter_judge_by_topic_three(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Compute inter-judge reliability grouped by (type, topic) for three judges.
    Produces pairwise stats for (gemini, claude), (gemini, deepseek), (claude, deepseek).
    Returns rows with: run_id, type, topic, judge_pair, n, percent_agreement, pa_ci95_low, pa_ci95_high, kappa, ac1
    """
    from collections import Counter, defaultdict

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
        # Gwet's AC1 (binary/nominal approx)
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
        # 95% CI (normal approx)
        import math
        se = math.sqrt(max(po*(1-po)/n, 0.0))
        low = max(0.0, po - 1.96*se)
        high = min(1.0, po + 1.96*se)
        return dict(n=n, pa=po, pa_low=low, pa_high=high, kappa=k, ac1=ac1)

    # Group rows by (type, topic) and accumulate verdict pairs for each judge pair
    grouped = {}
    for r in rows:
        hw_type = r.get('type')
        topic = r.get('topic')
        if not hw_type or not topic:
            continue
        key = (hw_type, topic)
        if key not in grouped:
            grouped[key] = {
                'gc': [], 'gd': [], 'cd': []  # (gemini,claude), (gemini,deepseek), (claude,deepseek)
            }
        g = str(r.get('judge_gemini_verdict','')).lower()
        c = str(r.get('judge_claude_verdict','')).lower()
        d = str(r.get('judge_deepseek_verdict','')).lower()
        if g and c and g != 'error' and c != 'error':
            grouped[key]['gc'].append((g,c))
        if g and d and g != 'error' and d != 'error':
            grouped[key]['gd'].append((g,d))
        if c and d and c != 'error' and d != 'error':
            grouped[key]['cd'].append((c,d))

    out: List[Dict[str, Any]] = []
    for (hw_type, topic), pairs_map in grouped.items():
        classes = ['correct','ambiguous','incorrect'] if hw_type == 'mcq' else ['acceptable','unacceptable']
        for pair_name, pairs in pairs_map.items():
            if not pairs:
                continue
            st = stats_for(pairs, classes)
            out.append({
                'run_id': rows[0].get('run_id',''),
                'type': hw_type,
                'topic': topic,
                'judge_pair': pair_name,
                'n': st['n'],
                'percent_agreement': round(st['pa'],4),
                'pa_ci95_low': round(st['pa_low'],4),
                'pa_ci95_high': round(st['pa_high'],4),
                'kappa': round(st['kappa'],4),
                'ac1': round(st['ac1'],4),
            })
    return out


def write_inter_judge_by_topic_csv_three(path: Path, rows: List[Dict[str, Any]]):
    """Write pairwise inter-judge reliability for three judges with a judge_pair column."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    keys = ['run_id','type','topic','judge_pair','n','percent_agreement','pa_ci95_low','pa_ci95_high','kappa','ac1']
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, '') for k in keys})


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


def write_latency_csv(path: Path, latency_map: Dict[str, List[float]]):
    """Write latency comparison CSV from config -> list of latency values in ms.
    Computes mean and std for each config.
    """
    from statistics import mean, stdev
    path.parent.mkdir(parents=True, exist_ok=True)
    if not latency_map:
        return
    
    rows = []
    for config, values in sorted(latency_map.items()):
        if not values:
            continue
        avg_ms = mean(values)
        std_ms = stdev(values) if len(values) > 1 else 0.0
        rows.append({
            'config': config,
            'n_samples': len(values),
            'avg_ms': round(avg_ms, 2),
            'std_ms': round(std_ms, 2),
        })
    
    if not rows:
        return
    
    keys = ['config', 'n_samples', 'avg_ms', 'std_ms']
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow(r)