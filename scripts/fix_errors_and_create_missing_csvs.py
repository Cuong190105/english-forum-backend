"""Fix Claude judge errors and create missing CSV files for Claude report."""
import json
import csv
import sys
import os
from pathlib import Path
from typing import Dict, Any, List, Tuple
from collections import defaultdict, Counter
from math import sqrt

# Fix encoding for Windows
os.environ['PYTHONIOENCODING'] = 'utf-8'

sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmark.report import write_inter_judge_csv, write_inter_judge_by_topic_csv, write_latency_csv


def _parse_json_strict(text: str) -> Dict[str, Any]:
    """Parse JSON strictly from Claude output. Remove code fences if present."""
    import json
    import re
    
    # Remove code fences (```json ... ``` or ``` ... ```)
    cleaned = text.strip()
    if cleaned.startswith('```'):
        # Find first newline after ```
        first_nl = cleaned.find('\n')
        if first_nl > 0:
            cleaned = cleaned[first_nl:].strip()
        # Remove trailing ```
        if cleaned.endswith('```'):
            cleaned = cleaned[:-3].strip()
        # Remove any remaining backticks
        cleaned = cleaned.strip('`')
    
    # Try to parse JSON directly
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        # Try to find JSON object in text
        start = cleaned.find('{')
        end = cleaned.rfind('}')
        if start >= 0 and end > start:
            candidate = cleaned[start:end+1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                # If candidate fails, try to fix common issues
                # Remove any trailing commas before closing brace
                candidate_fixed = re.sub(r',\s*}', '}', candidate)
                candidate_fixed = re.sub(r',\s*]', ']', candidate_fixed)
                try:
                    return json.loads(candidate_fixed)
                except json.JSONDecodeError:
                    pass
    
    # If still fails, try to extract just the verdict and why fields
    # This is a last resort but should not be needed if response_format works
    verdict_match = re.search(r'"verdict"\s*:\s*"([^"]+)"', cleaned, re.IGNORECASE)
    why_match = re.search(r'"why"\s*:\s*"([^"]*)"', cleaned, re.IGNORECASE | re.DOTALL)
    
    if verdict_match:
        verdict = verdict_match.group(1)
        why = why_match.group(1) if why_match else ''
        return {"verdict": verdict, "why": why}
    
    # If still fails, raise error (no fallback guessing)
    preview = text[:200].encode('ascii', errors='replace').decode('ascii')
    raise ValueError(f"Could not parse valid JSON from text: {preview}")


def fix_errors_and_reparse(run_id: str):
    """Fix errors in Claude batch results by re-parsing from results.jsonl."""
    run_dir = Path(f"benchmark/reports/{run_id}_claude")
    per_item_csv = run_dir / 'per_item_claude.csv'
    results_file = list(run_dir.glob("*_results.jsonl"))[0]
    
    # Load results.jsonl
    print(f"Reading results from {results_file}...")
    all_results = []
    with results_file.open('r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    all_results.append(json.loads(line))
                except Exception as e:
                    print(f"Warning: Failed to parse line: {e}")
    
    print(f"Loaded {len(all_results)} results")
    
    # Load per_item_claude.csv
    rows = []
    with per_item_csv.open('r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)
    
    print(f"Loaded {len(rows)} rows from {per_item_csv}")
    
    # Build results map
    results_map = {}
    for result_item in all_results:
        custom_id = result_item.get('custom_id', '')
        if not custom_id:
            continue
        
        result = result_item.get('result', {})
        if not result:
            continue
        
        result_type = result.get('type', '')
        if result_type != 'succeeded':
            continue
        
        # Get message.content[0].text
        message = result.get('message', {})
        content_list = message.get('content', [])
        if not content_list:
            continue
        
        first_content = content_list[0]
        if isinstance(first_content, dict):
            text = first_content.get('text', '')
        else:
            text = str(first_content)
        
        if not text:
            continue
        
        # Parse JSON from text (may have code fences)
        try:
            parsed = _parse_json_strict(text)
            # Validate required fields
            if 'verdict' not in parsed or 'why' not in parsed:
                continue
            results_map[custom_id] = parsed
        except Exception as e:
            # Store error for debugging (safe encoding)
            try:
                error_msg = str(e).encode('ascii', errors='replace').decode('ascii')
                print(f"Warning: Failed to parse {custom_id}: {error_msg}")
            except:
                print(f"Warning: Failed to parse {custom_id}")
            continue
    
    print(f"Parsed {len(results_map)} results")
    
    # Update rows - fix errors
    updated_rows = []
    fixed_count = 0
    still_error_count = 0
    
    for i, row in enumerate(rows):
        custom_id = f"{run_id}_{i}"
        result = results_map.get(custom_id, {})
        
        verdict = result.get('verdict', 'error')
        why = result.get('why', 'No response')
        
        # Check if this was an error and we fixed it
        if row.get('claude_judge_verdict', '').strip() == 'error' and verdict != 'error':
            fixed_count += 1
        
        if verdict == 'error':
            still_error_count += 1
        
        # Score mapping
        if row.get('type', '').strip() == 'mcq':
            vmap = {'correct': 1.0, 'ambiguous': 0.5, 'incorrect': 0.0}
        else:
            vmap = {'acceptable': 1.0, 'unacceptable': 0.0}
        
        score = vmap.get(verdict.lower(), 0.0)
        
        new_row = row.copy()
        new_row['claude_judge_verdict'] = verdict
        new_row['claude_judge_score'] = round(score, 4)
        new_row['claude_judge_why'] = why
        updated_rows.append(new_row)
    
    print(f"\nFixed {fixed_count} errors")
    print(f"Still {still_error_count} errors remaining")
    
    # Save updated per_item_claude.csv
    output_csv = run_dir / 'per_item_claude.csv'
    print(f"\nSaving updated per_item_claude.csv to {output_csv}...")
    
    fieldnames = [
        'run_id', 'config', 'topic', 'type', 'seed', 'source_text_sha', 'idx',
        'qid_gold', 'qid_pred', 'structural_valid',
        'question_sim', 'ans_sim', 'distractor_diversity', 'ans_score', 'item_score',
        'judge_verdict', 'judge_score', 'judge_why',
        'judge2_verdict', 'judge2_score', 'judge2_why',
        'claude_judge_verdict', 'claude_judge_score', 'claude_judge_why'
    ]
    
    with output_csv.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        for row in updated_rows:
            writer.writerow(row)
    
    print(f"Saved {len(updated_rows)} rows")
    return updated_rows


def create_inter_judge_csvs(run_id: str):
    """Create inter_judge.csv and inter_judge_by_topic.csv for Claude judge vs judge2."""
    # Check if run_id already ends with _claude or not
    if run_id.endswith('_claude'):
        run_dir = Path(f"benchmark/reports/{run_id}")
    else:
        run_dir = Path(f"benchmark/reports/{run_id}")
    per_item_csv = run_dir / 'per_item.csv'
    
    # Load per_item.csv (with Claude as judge_verdict)
    rows = []
    with per_item_csv.open('r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)
    
    print(f"\nLoaded {len(rows)} rows from {per_item_csv}")
    
    # Collect pairs: Claude judge (judge_verdict) vs judge2 (judge2_verdict)
    mcq_pairs = []
    fill_pairs = []
    
    for row in rows:
        hw_type = row.get('type', '').strip()
        a = str(row.get('judge_verdict', '')).lower().strip()  # Claude judge
        b = str(row.get('judge2_verdict', '')).lower().strip()  # Judge2
        
        if not a or not b or a == 'error' or b == 'error':
            continue
        
        if hw_type == 'mcq':
            mcq_pairs.append((a, b))
        elif hw_type == 'fill':
            fill_pairs.append((a, b))
    
    print(f"MCQ pairs: {len(mcq_pairs)}, Fill pairs: {len(fill_pairs)}")
    
    def compute_agree_kappa(pairs: List[Tuple[str, str]], classes: List[str]) -> Dict[str, float]:
        """Compute agreement statistics."""
        n = len(pairs)
        if n == 0:
            return dict(n=0, pa=0.0, pa_low=0.0, pa_high=0.0, kappa=0.0, ac1=0.0)
        
        po = sum(1 for a, b in pairs if a == b) / n
        a_counts = Counter(a for a, _ in pairs)
        b_counts = Counter(b for _, b in pairs)
        
        pe = 0.0
        for c in classes:
            pa_c = a_counts.get(c, 0) / n
            pb_c = b_counts.get(c, 0) / n
            pe += pa_c * pb_c
        
        k = 0.0 if (1.0 - pe) == 0 else (po - pe) / (1.0 - pe)
        
        # Gwet's AC1
        total_ratings = 2.0 * n
        pe1 = 0.0
        if total_ratings > 0:
            for c in classes:
                p_c = (a_counts.get(c, 0) + b_counts.get(c, 0)) / total_ratings
                pe1 += p_c * (1.0 - p_c)
        
        Q = max(1, len(classes))
        denom = max(1, Q - 1)
        pe1 = pe1 / denom if denom > 0 else 0.0
        ac1 = 0.0 if (1.0 - pe1) == 0 else (po - pe1) / (1.0 - pe1)
        
        # 95% CI
        se = sqrt(max(po * (1 - po) / n, 0.0))
        low = max(0.0, po - 1.96 * se)
        high = min(1.0, po + 1.96 * se)
        
        return dict(n=n, pa=po, pa_low=low, pa_high=high, kappa=k, ac1=ac1)
    
    # Create inter_judge.csv
    inter_rows = []
    run_id_val = rows[0].get('run_id', '') if rows else run_id
    
    if mcq_pairs:
        stats = compute_agree_kappa(mcq_pairs, ['correct', 'ambiguous', 'incorrect'])
        inter_rows.append({
            'run_id': run_id_val,
            'type': 'mcq',
            'n': stats['n'],
            'percent_agreement': round(stats['pa'], 4),
            'pa_ci95_low': round(stats['pa_low'], 4),
            'pa_ci95_high': round(stats['pa_high'], 4),
            'kappa': round(stats['kappa'], 4),
            'ac1': round(stats['ac1'], 4),
        })
    
    if fill_pairs:
        stats = compute_agree_kappa(fill_pairs, ['acceptable', 'unacceptable'])
        inter_rows.append({
            'run_id': run_id_val,
            'type': 'fill',
            'n': stats['n'],
            'percent_agreement': round(stats['pa'], 4),
            'pa_ci95_low': round(stats['pa_low'], 4),
            'pa_ci95_high': round(stats['pa_high'], 4),
            'kappa': round(stats['kappa'], 4),
            'ac1': round(stats['ac1'], 4),
        })
    
    if inter_rows:
        inter_judge_csv = run_dir / 'inter_judge.csv'
        print(f"\nWriting inter_judge.csv to {inter_judge_csv}...")
        write_inter_judge_csv(inter_judge_csv, inter_rows)
        print(f"Saved {len(inter_rows)} rows")
    
    # Create inter_judge_by_topic.csv
    grouped = defaultdict(list)
    for row in rows:
        a = str(row.get('judge_verdict', '')).lower().strip()
        b = str(row.get('judge2_verdict', '')).lower().strip()
        hw_type = row.get('type', '').strip()
        topic = row.get('topic', '').strip()
        
        if not hw_type or not topic:
            continue
        if a and b and a != 'error' and b != 'error':
            grouped[(hw_type, topic)].append((a, b))
    
    rows_by_topic = []
    for (hw_type, topic), pairs in grouped.items():
        if not pairs:
            continue
        
        classes = ['correct', 'ambiguous', 'incorrect'] if hw_type == 'mcq' else ['acceptable', 'unacceptable']
        stats = compute_agree_kappa(pairs, classes)
        rows_by_topic.append({
            'run_id': run_id_val,
            'type': hw_type,
            'topic': topic,
            'n': stats['n'],
            'percent_agreement': round(stats['pa'], 4),
            'pa_ci95_low': round(stats['pa_low'], 4),
            'pa_ci95_high': round(stats['pa_high'], 4),
            'kappa': round(stats['kappa'], 4),
            'ac1': round(stats['ac1'], 4),
        })
    
    if rows_by_topic:
        inter_judge_by_topic_csv = run_dir / 'inter_judge_by_topic.csv'
        print(f"\nWriting inter_judge_by_topic.csv to {inter_judge_by_topic_csv}...")
        write_inter_judge_by_topic_csv(inter_judge_by_topic_csv, rows_by_topic)
        print(f"Saved {len(rows_by_topic)} rows")
    
    # Create latency.csv (empty - no latency data for Claude judge since we only re-judged)
    # write_latency_csv expects a dict: config -> list of latency values
    # For Claude report, we have no latency data, so create empty dict
    latency_csv = run_dir / 'latency.csv'
    latency_map = {
        'minimal': [],
        'cot': [],
    }
    # Create latency.csv manually (empty since we have no latency data)
    print(f"\nWriting latency.csv to {latency_csv}...")
    with latency_csv.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['config', 'n_samples', 'avg_ms', 'std_ms'])
        writer.writeheader()
        # Empty file - no latency data for Claude judge
    print("Created empty latency.csv (no latency data for Claude judge)")


if __name__ == '__main__':
    run_id = sys.argv[1] if len(sys.argv) > 1 else '20251029_161124'
    
    print(f"Fixing errors and creating missing CSVs for {run_id}_claude")
    
    # Step 1: Fix errors
    print("\n=== Step 1: Fixing errors ===")
    updated_rows = fix_errors_and_reparse(run_id)
    
    # Step 2: Update per_item.csv with fixed Claude judge
    print("\n=== Step 2: Updating per_item.csv ===")
    from scripts.recompute_report_with_claude import recompute_report_with_claude
    recompute_report_with_claude(run_id)
    
    # Step 3: Create missing CSV files
    print("\n=== Step 3: Creating missing CSV files ===")
    create_inter_judge_csvs(run_id)
    
    print("\nDone!")

