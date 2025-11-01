"""Create two reports from 20251029_161124:
1. Report with judge1=Gemini Pro, judge2=DeepSeek
2. Report with judge1=Claude, judge2=DeepSeek
"""
from __future__ import annotations
import sys
import csv
import shutil
from pathlib import Path
from typing import List, Dict, Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.backfill_judge2 import load_env, vmap_for, find_pred_item, judge2_call
from scripts.recompute_report_with_claude import compute_binom_p_two_sided
from scripts.recompute_reports import compute_group_stats
from scripts.fix_errors_and_create_missing_csvs import create_inter_judge_csvs
from statistics import mean, stdev
from math import sqrt
from collections import defaultdict
import json
import re
import os


def load_per_item_data(run_id: str) -> List[Dict[str, Any]]:
    """Load per_item.csv from a report."""
    run_dir = Path(f"benchmark/reports/{run_id}")
    per_item_csv = run_dir / 'per_item.csv'
    
    if not per_item_csv.exists():
        raise FileNotFoundError(f"per_item.csv not found: {per_item_csv}")
    
    rows = []
    with per_item_csv.open('r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)
    
    return rows


def load_claude_judge_data(claude_run_id: str) -> Dict[tuple, Dict[str, Any]]:
    """Load Claude judge data from _claude report and map by (config, topic, type, seed, source_text_sha, idx)."""
    claude_dir = Path(f"benchmark/reports/{claude_run_id}")
    per_item_csv = claude_dir / 'per_item_claude.csv'
    
    if not per_item_csv.exists():
        # Fallback to per_item.csv
        per_item_csv = claude_dir / 'per_item.csv'
    
    if not per_item_csv.exists():
        raise FileNotFoundError(f"Claude per_item.csv not found: {per_item_csv}")
    
    claude_map = {}
    with per_item_csv.open('r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (
                row.get('config', '').strip(),
                row.get('topic', '').strip(),
                row.get('type', '').strip(),
                row.get('seed', '').strip(),
                row.get('source_text_sha', '').strip(),
                row.get('idx', '').strip(),
            )
            # Prefer claude_judge columns, fallback to judge columns
            claude_map[key] = {
                'verdict': row.get('claude_judge_verdict', '').strip() or row.get('judge_verdict', '').strip(),
                'score': row.get('claude_judge_score', '').strip() or row.get('judge_score', '').strip(),
                'why': row.get('claude_judge_why', '').strip() or row.get('judge_why', '').strip(),
            }
    
    return claude_map


def create_report_with_judges(
    source_run_id: str,
    new_run_id: str,
    judge1_source: str = 'gemini',  # 'gemini' or 'claude'
    judge2_source: str = 'deepseek',
    claude_run_id: str | None = None
):
    """Create a new report with specified judge1 and judge2 sources.
    
    Args:
        source_run_id: Source report ID (e.g., '20251029_161124')
        new_run_id: New report ID to create
        judge1_source: 'gemini' to keep from source, 'claude' to use Claude from claude_run_id
        judge2_source: 'deepseek' to backfill with DeepSeek
        claude_run_id: Report ID with Claude judge data (required if judge1_source='claude')
    """
    source_dir = Path(f"benchmark/reports/{source_run_id}")
    new_dir = Path(f"benchmark/reports/{new_run_id}")
    
    if not source_dir.exists():
        raise FileNotFoundError(f"Source report not found: {source_dir}")
    
    print(f"Creating report {new_run_id} with judge1={judge1_source}, judge2={judge2_source}")
    print(f"Source: {source_run_id}")
    
    # Step 1: Copy per_item.csv from source
    print(f"\nStep 1: Copying per_item.csv from source...")
    new_dir.mkdir(parents=True, exist_ok=True)
    source_per_item = source_dir / 'per_item.csv'
    new_per_item = new_dir / 'per_item.csv'
    
    if not source_per_item.exists():
        raise FileNotFoundError(f"Source per_item.csv not found: {source_per_item}")
    
    rows = load_per_item_data(source_run_id)
    print(f"Loaded {len(rows)} rows from source")
    
    # Step 2: Load Claude judge data if needed
    claude_map = {}
    if judge1_source == 'claude':
        if not claude_run_id:
            claude_run_id = f"{source_run_id}_claude"
        print(f"\nStep 2: Loading Claude judge data from {claude_run_id}...")
        claude_map = load_claude_judge_data(claude_run_id)
        print(f"Loaded {len(claude_map)} Claude judge entries")
    
    # Step 3: Update judge1 if needed (for Claude)
    updated_rows = []
    if judge1_source == 'claude':
        print(f"\nStep 3: Updating judge1 with Claude judge data...")
        matched = 0
        not_matched = 0
        
        for row in rows:
            new_row = row.copy()
            key = (
                row.get('config', '').strip(),
                row.get('topic', '').strip(),
                row.get('type', '').strip(),
                row.get('seed', '').strip(),
                row.get('source_text_sha', '').strip(),
                row.get('idx', '').strip(),
            )
            
            claude_data = claude_map.get(key)
            if claude_data:
                new_row['judge_verdict'] = claude_data['verdict']
                new_row['judge_score'] = claude_data['score']
                new_row['judge_why'] = claude_data['why']
                matched += 1
            else:
                not_matched += 1
                # Keep original judge1 if no Claude data found
            
            updated_rows.append(new_row)
        
        print(f"Matched: {matched}, Not matched: {not_matched}")
    else:
        # Keep original judge1 (Gemini)
        updated_rows = rows
        print(f"\nStep 3: Keeping original Gemini judge1")
    
    # Step 4: Backfill judge2 with DeepSeek
    if judge2_source == 'deepseek':
        print(f"\nStep 4: Backfilling judge2 with DeepSeek...")
        load_env('.env')
        
        if not os.getenv('DEEPSEEK_API_KEY'):
            raise RuntimeError("DEEPSEEK_API_KEY not set. Cannot backfill DeepSeek judge2.")
        
        vmap = {'mcq': {'correct': 1.0, 'ambiguous': 0.5, 'incorrect': 0.0},
                'fill': {'acceptable': 1.0, 'unacceptable': 0.0}}
        
        backfilled = 0
        errors = 0
        
        for i, row in enumerate(updated_rows):
            hw_type = row.get('type', '').strip()
            topic = row.get('topic', '').strip()
            config = row.get('config', '').strip()
            seed = row.get('seed', '').strip()
            source_text_sha = row.get('source_text_sha', '').strip()
            qid_pred = row.get('qid_pred', '').strip()
            idx = int(row.get('idx', '0') or '0')
            
            if not all([hw_type, topic, config, seed, source_text_sha, qid_pred]):
                continue
            
            # Find pred item
            safe_topic = re.sub(r"[^A-Za-z0-9._-]+", "_", topic)
            pred_path = Path(f"benchmark/pred/{config}/{safe_topic}/{hw_type}/{source_text_sha}/seed{seed}.json")
            
            if not pred_path.exists():
                print(f"Warning: pred file not found: {pred_path}")
                continue
            
            try:
                pred_item = find_pred_item(pred_path, qid_pred)
                
                # Call DeepSeek judge
                result = judge2_call(hw_type, pred_item, topic, context=None)
                
                verdict = result.get('verdict', '').lower()
                why = result.get('why', '')
                
                score_map = vmap.get(hw_type, {})
                score = score_map.get(verdict, 0.0)
                
                row['judge2_verdict'] = verdict
                row['judge2_score'] = str(score)
                row['judge2_why'] = why
                
                backfilled += 1
                
                if (i + 1) % 50 == 0:
                    print(f"  Processed {i + 1}/{len(updated_rows)} rows...")
                    
            except Exception as e:
                print(f"Error processing row {i}: {e}")
                row['judge2_verdict'] = 'error'
                row['judge2_score'] = ''
                row['judge2_why'] = str(e)
                errors += 1
        
        print(f"Backfilled: {backfilled}, Errors: {errors}")
    
    # Step 5: Save updated per_item.csv
    print(f"\nStep 5: Saving updated per_item.csv...")
    fieldnames = [
        'run_id', 'config', 'topic', 'type', 'seed', 'source_text_sha', 'idx',
        'qid_gold', 'qid_pred', 'structural_valid',
        'question_sim', 'ans_sim', 'distractor_diversity', 'ans_score', 'item_score',
        'judge_verdict', 'judge_score', 'judge_why',
        'judge2_verdict', 'judge2_score', 'judge2_why'
    ]
    
    # Update run_id
    for row in updated_rows:
        row['run_id'] = new_run_id
    
    with new_per_item.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(updated_rows)
    
    print(f"Saved {len(updated_rows)} rows to {new_per_item}")
    
    # Step 6: Recompute semantic scores (already computed, but ensure they're saved)
    print(f"\nStep 6: Semantic scores already computed with 0.75/0.25 weights")
    
    # Step 7: Recompute summary.csv
    print(f"\nStep 7: Recomputing summary.csv...")
    rows = load_per_item_data(new_run_id)
    summary_rows = compute_group_stats(rows)
    from benchmark.report import write_summary_csv
    summary_csv = new_dir / 'summary.csv'
    write_summary_csv(summary_csv, summary_rows)
    print(f"Saved summary.csv with {len(summary_rows)} rows")
    
    # Step 8: Recompute paired_overall and winloss
    print(f"\nStep 8: Recomputing paired_overall.csv and winloss.csv...")
    rows = load_per_item_data(new_run_id)
    
    # Group by (source_text_sha, topic, type, seed, config)
    groups: Dict[tuple, List[Dict[str, Any]]] = {}
    for row in rows:
        sha = row.get('source_text_sha', '').strip()
        topic = row.get('topic', '').strip()
        hw_type = row.get('type', '').strip()
        seed = row.get('seed', '').strip()
        config = row.get('config', '').strip()
        
        if not all([sha, topic, hw_type, seed, config]):
            continue
        
        key = (sha, topic, hw_type, seed, config)
        if key not in groups:
            groups[key] = []
        groups[key].append(row)
    
    # Build paired_map
    paired_map: Dict[tuple, Dict[str, Dict[str, float]]] = {}
    
    for key, group_rows in groups.items():
        sha, topic, hw_type, seed, config = key
        pair_key = (sha, topic, hw_type, seed)
        
        if pair_key not in paired_map:
            paired_map[pair_key] = {}
        
        semantic_scores = []
        judge_scores = []
        for row in group_rows:
            item_score_s = row.get('item_score', '').strip()
            judge_score_s = row.get('judge_score', '').strip()
            
            if item_score_s:
                try:
                    semantic_scores.append(float(item_score_s))
                except Exception:
                    pass
            if judge_score_s:
                try:
                    judge_scores.append(float(judge_score_s))
                except Exception:
                    pass
        
        sem_mean = mean(semantic_scores) if semantic_scores else 0.0
        judge_mean = mean(judge_scores) if judge_scores else 0.0
        
        paired_map[pair_key][config] = {
            'semantic_mean': sem_mean,
            'judge_mean': judge_mean,
        }
    
    # Compute paired_overall
    semantic_deltas = []
    judge_deltas = []
    
    for pair_key, config_map in paired_map.items():
        if 'minimal' in config_map and 'cot' in config_map:
            min_sem = config_map['minimal']['semantic_mean']
            cot_sem = config_map['cot']['semantic_mean']
            min_judge = config_map['minimal']['judge_mean']
            cot_judge = config_map['cot']['judge_mean']
            
            semantic_deltas.append(cot_sem - min_sem)
            judge_deltas.append(cot_judge - min_judge)
    
    # Write paired_overall.csv
    paired_rows = []
    if semantic_deltas:
        sem_delta_mean = mean(semantic_deltas)
        sem_delta_std = stdev(semantic_deltas) if len(semantic_deltas) > 1 else 0.0
        sem_delta_se = (sem_delta_std / sqrt(len(semantic_deltas))) if len(semantic_deltas) > 1 else 0.0
        sem_delta_ci_low = sem_delta_mean - 1.96 * sem_delta_se
        sem_delta_ci_high = sem_delta_mean + 1.96 * sem_delta_se
        
        paired_rows.append({
            'run_id': new_run_id,
            'metric': 'semantic',
            'n_pairs': len(semantic_deltas),
            'delta_mean': round(sem_delta_mean, 4),
            'delta_std': round(sem_delta_std, 4),
            'delta_se': round(sem_delta_se, 4),
            'delta_ci95_low': round(sem_delta_ci_low, 4),
            'delta_ci95_high': round(sem_delta_ci_high, 4),
            'delta_ci95_halfwidth_H': round(1.96 * sem_delta_se, 4),
            'delta_ci_level': 0.95,
            'delta_H_target': 0.04,
            'delta_meets_H_target': 1 if (1.96 * sem_delta_se) < 0.04 else 0,
            'delta_significant': 1 if sem_delta_ci_low > 0 or sem_delta_ci_high < 0 else 0,
        })
    
    if judge_deltas:
        j_delta_mean = mean(judge_deltas)
        j_delta_std = stdev(judge_deltas) if len(judge_deltas) > 1 else 0.0
        j_delta_se = (j_delta_std / sqrt(len(judge_deltas))) if len(judge_deltas) > 1 else 0.0
        j_delta_ci_low = j_delta_mean - 1.96 * j_delta_se
        j_delta_ci_high = j_delta_mean + 1.96 * j_delta_se
        
        paired_rows.append({
            'run_id': new_run_id,
            'metric': 'judge',
            'n_pairs': len(judge_deltas),
            'delta_mean': round(j_delta_mean, 4),
            'delta_std': round(j_delta_std, 4),
            'delta_se': round(j_delta_se, 4),
            'delta_ci95_low': round(j_delta_ci_low, 4),
            'delta_ci95_high': round(j_delta_ci_high, 4),
            'delta_ci95_halfwidth_H': round(1.96 * j_delta_se, 4),
            'delta_ci_level': 0.95,
            'delta_H_target': 0.05,
            'delta_meets_H_target': 1 if (1.96 * j_delta_se) < 0.05 else 0,
            'delta_significant': 1 if j_delta_ci_low > 0 or j_delta_ci_high < 0 else 0,
        })
    
    from benchmark.report import write_paired_overall_csv
    paired_overall_csv = new_dir / 'paired_overall.csv'
    write_paired_overall_csv(paired_overall_csv, paired_rows)
    print(f"Saved paired_overall.csv")
    
    # Compute winloss.csv
    semantic_wins = sum(1 for d in semantic_deltas if d > 0)
    semantic_losses = sum(1 for d in semantic_deltas if d < 0)
    semantic_ties = len(semantic_deltas) - semantic_wins - semantic_losses
    semantic_n_effective = semantic_wins + semantic_losses
    semantic_win_rate = (semantic_wins / semantic_n_effective) if semantic_n_effective > 0 else 0.0
    semantic_binomial_p = compute_binom_p_two_sided(semantic_wins, semantic_losses)
    
    judge_wins = sum(1 for d in judge_deltas if d > 0)
    judge_losses = sum(1 for d in judge_deltas if d < 0)
    judge_ties = len(judge_deltas) - judge_wins - judge_losses
    judge_n_effective = judge_wins + judge_losses
    judge_win_rate = (judge_wins / judge_n_effective) if judge_n_effective > 0 else 0.0
    judge_binomial_p = compute_binom_p_two_sided(judge_wins, judge_losses)
    
    winloss_rows = [{
        'run_id': new_run_id,
        'semantic_wins': semantic_wins,
        'semantic_losses': semantic_losses,
        'semantic_ties': semantic_ties,
        'semantic_n_effective': semantic_n_effective,
        'semantic_win_rate': round(semantic_win_rate, 4),
        'semantic_binomial_p': round(semantic_binomial_p, 4),
        'judge_wins': judge_wins,
        'judge_losses': judge_losses,
        'judge_ties': judge_ties,
        'judge_n_effective': judge_n_effective,
        'judge_win_rate': round(judge_win_rate, 4),
        'judge_binomial_p': round(judge_binomial_p, 4),
    }]
    
    from benchmark.report import write_winloss_csv
    winloss_csv = new_dir / 'winloss.csv'
    write_winloss_csv(winloss_csv, winloss_rows)
    print(f"Saved winloss.csv")
    
    # Step 9: Create inter_judge.csv
    print(f"\nStep 9: Creating inter_judge.csv...")
    create_inter_judge_csvs(new_run_id)
    
    print(f"\nDone! Report {new_run_id} created with judge1={judge1_source}, judge2={judge2_source}")


def main():
    import argparse
    ap = argparse.ArgumentParser(description='Create reports with specified judge combinations')
    ap.add_argument('--source-run-id', default='20251029_161124', help='Source report ID')
    ap.add_argument('--gemini-deepseek-id', default='20251029_161124_gemini_deepseek', help='Report ID for Gemini+DeepSeek')
    ap.add_argument('--claude-deepseek-id', default='20251029_161124_claude_deepseek', help='Report ID for Claude+DeepSeek')
    ap.add_argument('--claude-run-id', default='20251029_161124_claude', help='Claude report ID to get judge1 data')
    ap.add_argument('--only', choices=['gemini', 'claude'], help='Only create one report')
    args = ap.parse_args()
    
    if args.only == 'gemini' or not args.only:
        print("=" * 70)
        print("Creating Report 1: Gemini Pro + DeepSeek")
        print("=" * 70)
        create_report_with_judges(
            source_run_id=args.source_run_id,
            new_run_id=args.gemini_deepseek_id,
            judge1_source='gemini',
            judge2_source='deepseek',
        )
        print("\n")
    
    if args.only == 'claude' or not args.only:
        print("=" * 70)
        print("Creating Report 2: Claude + DeepSeek")
        print("=" * 70)
        create_report_with_judges(
            source_run_id=args.source_run_id,
            new_run_id=args.claude_deepseek_id,
            judge1_source='claude',
            judge2_source='deepseek',
            claude_run_id=args.claude_run_id,
        )
        print("\n")
    
    print("=" * 70)
    print("All reports created successfully!")
    print("=" * 70)


if __name__ == '__main__':
    main()

