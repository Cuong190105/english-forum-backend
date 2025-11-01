"""Replace judge1 with Claude judge in the original report 20251029_161124."""
from __future__ import annotations
import sys
import csv
from pathlib import Path
from typing import List, Dict, Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.recompute_report_with_claude import recompute_report_with_claude
from scripts.recompute_semantic_simple import recompute_semantic_with_weights, recompute_summary_with_new_semantic

def replace_judge1_with_claude_in_original_report(source_run_id: str):
    """Replace judge1 with Claude judge in the original report."""
    original_run_id = source_run_id  # e.g., 20251029_161124
    claude_run_id = f"{source_run_id}_claude"  # e.g., 20251029_161124_claude
    
    print(f"Replacing judge1 with Claude judge in report {original_run_id}")
    print(f"Claude judge data from: {claude_run_id}")
    
    # Step 1: Copy Claude judge data from _claude report to original report
    claude_dir = Path(f"benchmark/reports/{claude_run_id}")
    original_dir = Path(f"benchmark/reports/{original_run_id}")
    
    if not claude_dir.exists():
        raise FileNotFoundError(f"Claude report not found: {claude_dir}")
    if not original_dir.exists():
        raise FileNotFoundError(f"Original report not found: {original_dir}")
    
    # Load per_item_claude.csv
    claude_per_item_csv = claude_dir / 'per_item_claude.csv'
    if not claude_per_item_csv.exists():
        # Fallback to per_item.csv if per_item_claude.csv doesn't exist
        claude_per_item_csv = claude_dir / 'per_item.csv'
    
    print(f"\nStep 1: Loading Claude judge data from {claude_per_item_csv}...")
    claude_rows = []
    with claude_per_item_csv.open('r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        for r in reader:
            claude_rows.append(r)
    
    print(f"Loaded {len(claude_rows)} rows from Claude report")
    
    # Load original per_item.csv
    original_per_item_csv = original_dir / 'per_item.csv'
    print(f"\nStep 2: Loading original per_item.csv from {original_per_item_csv}...")
    original_rows = []
    with original_per_item_csv.open('r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        for r in reader:
            original_rows.append(r)
    
    print(f"Loaded {len(original_rows)} rows from original report")
    
    # Create a map from (config, topic, type, seed, source_text_sha, idx) -> Claude judge data
    claude_map = {}
    for row in claude_rows:
        key = (
            row.get('config', '').strip(),
            row.get('topic', '').strip(),
            row.get('type', '').strip(),
            row.get('seed', '').strip(),
            row.get('source_text_sha', '').strip(),
            row.get('idx', '').strip(),
        )
        if all(key):
            claude_map[key] = row
    
    print(f"Created map with {len(claude_map)} Claude judge entries")
    
    # Update original rows with Claude judge
    print(f"\nStep 3: Updating original rows with Claude judge...")
    updated_rows = []
    matched = 0
    not_matched = 0
    
    for row in original_rows:
        key = (
            row.get('config', '').strip(),
            row.get('topic', '').strip(),
            row.get('type', '').strip(),
            row.get('seed', '').strip(),
            row.get('source_text_sha', '').strip(),
            row.get('idx', '').strip(),
        )
        
        new_row = row.copy()
        
        # Get Claude judge data
        claude_row = claude_map.get(key)
        if claude_row:
            # Replace judge1 with Claude judge
            claude_verdict = claude_row.get('claude_judge_verdict', '').strip() or claude_row.get('judge_verdict', '').strip()
            claude_score = claude_row.get('claude_judge_score', '').strip() or claude_row.get('judge_score', '').strip()
            claude_why = claude_row.get('claude_judge_why', '').strip() or claude_row.get('judge_why', '').strip()
            
            new_row['judge_verdict'] = claude_verdict
            new_row['judge_score'] = claude_score
            new_row['judge_why'] = claude_why
            
            matched += 1
        else:
            not_matched += 1
            print(f"Warning: No Claude judge data found for key: {key}")
        
        updated_rows.append(new_row)
    
    print(f"Matched: {matched}, Not matched: {not_matched}")
    
    # Save updated per_item.csv
    print(f"\nStep 4: Saving updated per_item.csv to {original_per_item_csv}...")
    fieldnames = [
        'run_id', 'config', 'topic', 'type', 'seed', 'source_text_sha', 'idx',
        'qid_gold', 'qid_pred', 'structural_valid',
        'question_sim', 'ans_sim', 'distractor_diversity', 'ans_score', 'item_score',
        'judge_verdict', 'judge_score', 'judge_why',
        'judge2_verdict', 'judge2_score', 'judge2_why'
    ]
    
    with original_per_item_csv.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        for row in updated_rows:
            writer.writerow(row)
    
    print(f"Saved {len(updated_rows)} rows")
    
    # Step 5: Recompute semantic scores with weights 0.75/0.25
    print(f"\nStep 5: Recomputing semantic scores with weights 0.75/0.25...")
    recompute_semantic_with_weights(original_run_id, w_prompt=0.75, w_div=0.25)
    
    # Step 6: Recompute summary.csv
    print(f"\nStep 6: Recomputing summary.csv...")
    recompute_summary_with_new_semantic(original_run_id)
    
    # Step 7: Recompute paired_overall and winloss directly from original per_item.csv
    print(f"\nStep 7: Recomputing paired_overall.csv and winloss.csv...")
    from scripts.recompute_report_with_claude import compute_binom_p_two_sided, clamp01
    from statistics import mean, stdev
    from math import sqrt
    from collections import defaultdict
    
    # Load updated per_item.csv
    rows = updated_rows
    
    # Group by (config, topic, type, seed)
    groups: Dict[tuple, List[Dict[str, Any]]] = {}
    for row in rows:
        key = (
            row.get('config', '').strip(),
            row.get('topic', '').strip(),
            row.get('type', '').strip(),
            row.get('seed', '').strip(),
        )
        if all(key):
            if key not in groups:
                groups[key] = []
            groups[key].append(row)
    
    # Build paired_map for paired analysis
    paired_map: Dict[tuple, Dict[str, Dict[str, float]]] = {}
    
    for (config, topic, hw_type, seed), group_rows in groups.items():
        sorted_rows = sorted(group_rows, key=lambda r: int(r.get('idx', '0') or '0'))
        
        # Extract scores per item
        for row in sorted_rows:
            source_text_sha = row.get('source_text_sha', '').strip()
            if not source_text_sha:
                continue
            
            semantic_score = float(row.get('item_score', '0') or '0')
            judge_score = float(row.get('judge_score', '0') or '0')
            
            pair_key = (source_text_sha, topic, hw_type, seed)
            if pair_key not in paired_map:
                paired_map[pair_key] = {}
            
            if config not in paired_map[pair_key]:
                paired_map[pair_key][config] = {}
            
            if 'semantic_mean' not in paired_map[pair_key][config]:
                paired_map[pair_key][config]['semantic_mean'] = []
                paired_map[pair_key][config]['judge_mean'] = []
            
            paired_map[pair_key][config]['semantic_mean'].append(semantic_score)
            paired_map[pair_key][config]['judge_mean'].append(judge_score)
    
    # Compute paired_overall.csv
    print(f"Computing paired_overall.csv...")
    paired_rows = []
    semantic_deltas = []
    judge_deltas = []
    
    for pair_key, config_map in paired_map.items():
        if 'minimal' in config_map and 'cot' in config_map:
            min_sem = mean(config_map['minimal']['semantic_mean'])
            cot_sem = mean(config_map['cot']['semantic_mean'])
            min_judge = mean(config_map['minimal']['judge_mean'])
            cot_judge = mean(config_map['cot']['judge_mean'])
            
            semantic_deltas.append(cot_sem - min_sem)
            judge_deltas.append(cot_judge - min_judge)
    
    if semantic_deltas:
        sem_delta_mean = mean(semantic_deltas)
        sem_delta_std = stdev(semantic_deltas) if len(semantic_deltas) > 1 else 0.0
        sem_delta_se = (sem_delta_std / sqrt(len(semantic_deltas))) if len(semantic_deltas) > 1 else 0.0
        sem_delta_ci_low = sem_delta_mean - 1.96 * sem_delta_se
        sem_delta_ci_high = sem_delta_mean + 1.96 * sem_delta_se
        
        paired_rows.append({
            'run_id': original_run_id,
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
            'run_id': original_run_id,
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
    
    # Write paired_overall.csv
    from benchmark.report import write_paired_overall_csv
    paired_overall_csv = original_dir / 'paired_overall.csv'
    write_paired_overall_csv(paired_overall_csv, paired_rows)
    print(f"Saved paired_overall.csv")
    
    # Compute winloss.csv
    print(f"Computing winloss.csv...")
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
        'run_id': original_run_id,
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
    winloss_csv = original_dir / 'winloss.csv'
    write_winloss_csv(winloss_csv, winloss_rows)
    print(f"Saved winloss.csv")
    
    print(f"\nDone! Report {original_run_id} now uses Claude judge as judge1")
    print(f"All CSV files updated in {original_dir}")


if __name__ == '__main__':
    run_id = sys.argv[1] if len(sys.argv) > 1 else '20251029_161124'
    replace_judge1_with_claude_in_original_report(run_id)

