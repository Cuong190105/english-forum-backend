from __future__ import annotations
import os
import json
from pathlib import Path
import hashlib
from datetime import datetime
from statistics import mean, stdev
from math import sqrt
from typing import List, Dict, Any
import re

from .generate_gold import generate_gold
from .generate_pred import generate_pred
from .validate import validate_items
from .score import mcq_semantics, fill_semantics
from .judge import judge_mcq, judge_fill
from .report import (
    write_summary_csv, write_per_item_csv, write_jsonl, write_paired_overall_csv, write_winloss_csv,
    append_summary_rows, append_per_item_rows, append_jsonl
)


def run(topics: List[Dict[str,str]], configs: List[str], seeds: List[int], run_id: str | None = None, num_items: int = 10, resume: bool = False):
    now = datetime.now().strftime('%Y%m%d_%H%M%S')
    run_id = run_id or now
    out_dir = Path(f"benchmark/reports/{run_id}")

    summary_rows: List[Dict[str, Any]] = []
    per_item_rows: List[Dict[str, Any]] = []
    invalid_rows: List[Dict[str, Any]] = []

    # For paired analysis between configs (e.g., minimal vs cot)
    # Keyed by (source_text_sha, topic, type, seed) -> {config: {semantic_mean, judge_mean}}
    paired_map: Dict[tuple, Dict[str, Dict[str, float]]] = {}

    # Pre-create report directory
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_csv = out_dir / 'summary.csv'
    per_item_csv = out_dir / 'per_item.csv'
    invalid_jsonl = out_dir / 'invalid_items.jsonl'

    for t in topics:
        topic = t['topic']
        hw_type = t['type']
        post_text = t['post_text']

        # Sanitize topic for filesystem paths
        safe_topic = re.sub(r"[^A-Za-z0-9._-]+", "_", topic)
        # Precompute source text hash for tracking (per-source gold/pred)
        source_text_sha = hashlib.sha256(post_text.encode('utf-8')).hexdigest()
        gold_path = Path(f"benchmark/gold/{safe_topic}/{hw_type}/{source_text_sha}/seed0.json")
        if gold_path.exists():
            gold = json.loads(gold_path.read_text(encoding='utf-8'))
        else:
            gold = generate_gold(topic, hw_type, post_text, gold_path, num_items=num_items)

        for config in configs:
            for seed in seeds:
                pred_path = Path(f"benchmark/pred/{config}/{safe_topic}/{hw_type}/{source_text_sha}/seed{seed}.json")
                if resume and pred_path.exists():
                    # Reuse existing prediction to speed up resuming
                    meta = {'config': config, 'topic': topic, 'type': hw_type, 'seed': seed, 'n': len(json.loads(pred_path.read_text(encoding='utf-8')))}
                else:
                    meta = generate_pred(config, topic, hw_type, post_text, seed, pred_path, num_items=num_items)
                pred = json.loads(pred_path.read_text(encoding='utf-8'))

                # Structural validation (enforce exact bundle count)
                ok_pred, errs_pred, warns_pred = validate_items(pred, hw_type, expected_count=num_items)
                ok_gold, errs_gold, warns_gold = validate_items(gold, hw_type, expected_count=num_items)
                if not ok_pred:
                    for e in errs_pred:
                        invalid_rows.append({'run_id': run_id, 'where': 'pred', 'config': config, 'topic': topic, 'type': hw_type, 'seed': seed, 'error': e})
                if not ok_gold:
                    for e in errs_gold:
                        invalid_rows.append({'run_id': run_id, 'where': 'gold', 'config': 'gold', 'topic': topic, 'type': hw_type, 'seed': 0, 'error': e})
                # Log non-blocking warnings
                for w in warns_pred:
                    invalid_rows.append({'run_id': run_id, 'where': 'pred', 'config': config, 'topic': topic, 'type': hw_type, 'seed': seed, 'warning': w})
                for w in warns_gold:
                    invalid_rows.append({'run_id': run_id, 'where': 'gold', 'config': 'gold', 'topic': topic, 'type': hw_type, 'seed': 0, 'warning': w})

                # Build per-item structural validity for pred
                invalid_idx_pred = set()
                for e in errs_pred:
                    # errors shaped like "i3: ..."
                    if isinstance(e, str) and e.startswith('i') and ':' in e:
                        try:
                            idx_str = e[1:e.index(':')]
                            ii = int(idx_str)
                            invalid_idx_pred.add(ii)
                        except Exception:
                            pass

                n = min(len(pred), len(gold))
                judge_scores = []
                semantic_scores = []

                for i in range(n):
                    pi = pred[i]
                    gi = gold[i]
                    qid_pred = pi.get('question',{}).get('id', f"{i+1}")
                    qid_gold = gi.get('question',{}).get('id', f"{i+1}")
                    idx = i + 1
                    structural_valid = (idx not in invalid_idx_pred)
                    if hw_type == 'mcq':
                        ps, ans, div, item = mcq_semantics(pi, gi)
                        verdict = judge_mcq(
                            pi['question']['prompt'],
                            {o['id']: o['label'] for o in pi['question']['options']},
                            pi['correctOptionId'],
                            topic,
                        )
                        vmap = {'correct':1.0, 'ambiguous':0.5, 'incorrect':0.0}
                        jscore = vmap.get(str(verdict.get('verdict','')).lower(), 0.0)
                        jwhy = verdict.get('why', '')
                        per_item_rows.append({
                            'run_id': run_id,
                            'config': config,
                            'topic': topic,
                            'type': hw_type,
                            'seed': seed,
                            'source_text_sha': source_text_sha,
                            'idx': idx,
                            'qid_gold': qid_gold,
                            'qid_pred': qid_pred,
                            'structural_valid': 1 if structural_valid else 0,
                            'prompt_sim': round(ps,4),
                            'ans_sim': ('' if ans is None else round(ans,4)),
                            'distractor_diversity': round(div,4),
                            'ans_score': ('' if ans is None else round(ans,4)),  # MCQ: N/A → ''
                            'item_score': round(item,4),
                            'judge_verdict': verdict.get('verdict',''),
                            'judge_score': round(jscore,4),
                            'judge_why': jwhy,
                        })
                    else:
                        ps, ans, item = fill_semantics(pi, gi)
                        verdict = judge_fill(pi['question']['prompt'], pi['answer'], topic)
                        vmap = {'acceptable':1.0, 'unacceptable':0.0}
                        jscore = vmap.get(str(verdict.get('verdict','')).lower(), 0.0)
                        jwhy = verdict.get('why', '')
                        per_item_rows.append({
                            'run_id': run_id,
                            'config': config,
                            'topic': topic,
                            'type': hw_type,
                            'seed': seed,
                            'source_text_sha': source_text_sha,
                            'idx': idx,
                            'qid_gold': qid_gold,
                            'qid_pred': qid_pred,
                            'structural_valid': 1 if structural_valid else 0,
                            'prompt_sim': round(ps,4),
                            'ans_sim': round(ans,4),  # for FILL, ans_sim = ans_score
                            'distractor_diversity': '',
                            'ans_score': round(ans,4),
                            'item_score': round(item,4),
                            'judge_verdict': verdict.get('verdict',''),
                            'judge_score': round(jscore,4),
                            'judge_why': jwhy,
                        })
                    judge_scores.append(jscore)
                    semantic_scores.append(item)

                # Structural pass percent: % pred items passing structural checks
                n_items = n
                n_struct_pass = sum(1 for i in range(1, n_items+1) if i not in invalid_idx_pred)
                structural_pass_pct = (100.0 * n_struct_pass / n_items) if n_items > 0 else 0.0
                # Compute aggregates and 95% CI
                sem_mean = mean(semantic_scores) if semantic_scores else 0.0
                sem_std = stdev(semantic_scores) if len(semantic_scores) > 1 else 0.0
                sem_se = (sem_std / sqrt(n_items)) if n_items > 1 else 0.0
                def clamp01(x: float) -> float:
                    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x
                sem_ci_low = clamp01(sem_mean - 1.96 * sem_se)
                sem_ci_high = clamp01(sem_mean + 1.96 * sem_se)

                j_mean = mean(judge_scores) if judge_scores else 0.0
                j_std = stdev(judge_scores) if len(judge_scores) > 1 else 0.0
                j_se = (j_std / sqrt(n_items)) if n_items > 1 else 0.0
                j_ci_low = clamp01(j_mean - 1.96 * j_se)
                j_ci_high = clamp01(j_mean + 1.96 * j_se)

                sr = {
                    'run_id': run_id,
                    'config': config,
                    'topic': topic,
                    'type': hw_type,
                    'seed': seed,
                    'n_items': n_items,
                    'structural_pass_pct': round(structural_pass_pct, 2),
                    'semantic_mean': round(sem_mean, 4),
                    'semantic_std': round(sem_std, 4),
                    'semantic_se': round(sem_se, 4),
                    'semantic_ci95_low': round(sem_ci_low, 4),
                    'semantic_ci95_high': round(sem_ci_high, 4),
                    'judge_mean': round(j_mean, 4),
                    'judge_std': round(j_std, 4),
                    'judge_se': round(j_se, 4),
                    'judge_ci95_low': round(j_ci_low, 4),
                    'judge_ci95_high': round(j_ci_high, 4),
                }
                summary_rows.append(sr)
                # Stream append after each config/seed to persist progress
                try:
                    append_per_item_rows(per_item_csv, per_item_rows[-n_items:])
                    append_summary_rows(summary_csv, [sr])
                    if invalid_rows:
                        append_jsonl(invalid_jsonl, invalid_rows[-(len(warns_pred)+len(warns_gold)+len(errs_pred)+len(errs_gold)):])
                except Exception:
                    # Best effort: continue; we'll write full at the end too
                    pass

                # Populate paired map for later Δ and win/loss computation
                key = (source_text_sha, topic, hw_type, seed)
                if key not in paired_map:
                    paired_map[key] = {}
                paired_map[key][config] = {
                    'semantic_mean': float(sem_mean),
                    'judge_mean': float(j_mean),
                }

    # Write reports
    # Final write ensures files are consistent; may overwrite, but all progress was already streamed
    write_summary_csv(summary_csv, summary_rows)
    write_per_item_csv(per_item_csv, per_item_rows)
    write_jsonl(invalid_jsonl, invalid_rows)

    # Build paired Δ and win/loss stats between 'cot' and 'minimal' when both present
    def compute_binom_p_two_sided(wins: int, losses: int) -> float:
        import math
        n = wins + losses
        if n == 0:
            return 1.0
        # two-sided exact using 2*min(CDF(k), 1-CDF(k-1)) at p=0.5
        k = wins
        def pmf(i: int) -> float:
            return math.comb(n, i) * (0.5 ** n)
        def cdf(i: int) -> float:
            return sum(pmf(j) for j in range(0, i+1))
        c_low = cdf(k)
        c_high = 1.0 - cdf(k-1) if k > 0 else 1.0
        p = 2.0 * min(c_low, c_high)
        return min(max(p, 0.0), 1.0)

    deltas_sem: List[float] = []
    deltas_j: List[float] = []
    s_w = s_l = s_t = 0
    j_w = j_l = j_t = 0
    for key, cfgmap in paired_map.items():
        if 'minimal' in cfgmap and 'cot' in cfgmap:
            d_sem = cfgmap['cot']['semantic_mean'] - cfgmap['minimal']['semantic_mean']
            d_j = cfgmap['cot']['judge_mean'] - cfgmap['minimal']['judge_mean']
            deltas_sem.append(d_sem)
            deltas_j.append(d_j)
            # Win/loss/tie with a tiny tolerance for float equality
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
                j_t += 1

    # Compute Δ ± CI for semantic and judge (use module-level mean, stdev, sqrt)
    def ci_stats(arr: List[float]) -> Dict[str, float]:
        if not arr:
            return dict(mean=0.0, std=0.0, se=0.0, low=0.0, high=0.0)
        m = mean(arr)
        sd = stdev(arr) if len(arr) > 1 else 0.0
        se = (sd / sqrt(len(arr))) if len(arr) > 1 else 0.0
        # Clamp to [-1, 1] because deltas of probabilities are within this
        low = max(-1.0, m - 1.96 * se)
        high = min(1.0, m + 1.96 * se)
        return dict(mean=m, std=sd, se=se, low=low, high=high)

    s_stats = ci_stats(deltas_sem)
    j_stats = ci_stats(deltas_j)
    s_H = max(0.0, (s_stats['high'] - s_stats['low'])/2.0)
    j_H = max(0.0, (j_stats['high'] - j_stats['low'])/2.0)
    # CI level used throughout (fixed at 0.95 for now)
    ci_level = 0.95
    # Choose H_target defaults by metric
    H_target_sem = 0.04
    H_target_j = 0.05
    s_meets = 1 if s_H <= H_target_sem else 0
    j_meets = 1 if j_H <= H_target_j else 0
    # Statistical significance: CI excludes 0, independent of H_target
    s_sig = 1 if (s_stats['low'] > 0.0 or s_stats['high'] < 0.0) else 0
    j_sig = 1 if (j_stats['low'] > 0.0 or j_stats['high'] < 0.0) else 0
    paired_rows = [
        {
            'run_id': run_id,
            'metric': 'semantic',
            'n_pairs': len(deltas_sem),
            'delta_mean': round(s_stats['mean'], 4),
            'delta_std': round(s_stats['std'], 4),
            'delta_se': round(s_stats['se'], 4),
            'delta_ci95_low': round(s_stats['low'], 4),
            'delta_ci95_high': round(s_stats['high'], 4),
            'delta_ci95_halfwidth_H': round(s_H, 4),
            'delta_ci_level': ci_level,
            'delta_H_target': H_target_sem,
            'delta_meets_H_target': s_meets,
            'delta_significant': s_sig,
        },
        {
            'run_id': run_id,
            'metric': 'judge',
            'n_pairs': len(deltas_j),
            'delta_mean': round(j_stats['mean'], 4),
            'delta_std': round(j_stats['std'], 4),
            'delta_se': round(j_stats['se'], 4),
            'delta_ci95_low': round(j_stats['low'], 4),
            'delta_ci95_high': round(j_stats['high'], 4),
            'delta_ci95_halfwidth_H': round(j_H, 4),
            'delta_ci_level': ci_level,
            'delta_H_target': H_target_j,
            'delta_meets_H_target': j_meets,
            'delta_significant': j_sig,
        },
    ]

    # Win/loss and binomial p-values (exclude ties in rate; H0: p=0.5)
    s_n_eff = s_w + s_l
    j_n_eff = j_w + j_l
    s_rate = (s_w / s_n_eff) if s_n_eff > 0 else 0.0
    j_rate = (j_w / j_n_eff) if j_n_eff > 0 else 0.0
    s_p = compute_binom_p_two_sided(s_w, s_l)
    j_p = compute_binom_p_two_sided(j_w, j_l)
    winloss_rows = [
        {
            'run_id': run_id,
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
        }
    ]

    write_paired_overall_csv(out_dir / 'paired_overall.csv', paired_rows)
    write_winloss_csv(out_dir / 'winloss.csv', winloss_rows)
    print(f"Reports written to: {out_dir}")


if __name__ == '__main__':
    # Example topics list; in practice, load from a file or task input
    topics = [
        {'topic': 'Passive Voice', 'type': 'mcq', 'post_text': 'The homework is being checked by the teacher.'},
        {'topic': 'Conditionals Type 2', 'type': 'fill', 'post_text': 'If I ____ (be) you, I would study harder.'},
    ]
    configs = ['flash_cot','flash_minimal','flashlite_cot','flashlite_minimal']
    seeds = [0,1,2]
    run(topics, configs, seeds)
