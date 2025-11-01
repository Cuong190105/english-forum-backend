"""Reparse Claude batch results from results.jsonl file."""
import json
import csv
import sys
from pathlib import Path
import re
from typing import Dict, Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def _parse_json_strict(text: str) -> Dict[str, Any]:
    """Parse JSON strictly from Claude output. Remove code fences if present."""
    import json
    
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
    except json.JSONDecodeError:
        # Try to find JSON object in text
        start = cleaned.find('{')
        end = cleaned.rfind('}')
        if start >= 0 and end > start:
            candidate = cleaned[start:end+1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass
    
    # If still fails, raise error (no fallback guessing)
    raise ValueError(f"Could not parse valid JSON from text: {text[:200]}")


def reparse_from_jsonl(run_id: str):
    """Reparse Claude batch results from results.jsonl and update per_item_claude.csv."""
    run_dir = Path(f"benchmark/reports/{run_id}_claude")
    
    # Find results.jsonl file
    results_files = list(run_dir.glob("*_results.jsonl"))
    if not results_files:
        raise FileNotFoundError(f"No results.jsonl file found in {run_dir}")
    
    results_file = results_files[0]
    print(f"Reading results from {results_file}...")
    
    # Load results.jsonl
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
    
    # Load original per_item_claude.csv
    per_item_claude_csv = run_dir / 'per_item_claude.csv'
    if not per_item_claude_csv.exists():
        raise FileNotFoundError(f"per_item_claude.csv not found: {per_item_claude_csv}")
    
    rows = []
    with per_item_claude_csv.open('r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)
    
    print(f"Loaded {len(rows)} rows from {per_item_claude_csv}")
    
    # Parse results and update rows
    results_map = {}
    for result_item in all_results:
        custom_id = result_item.get('custom_id', '')
        if not custom_id:
            continue
        
        # Structure: {"custom_id": "...", "result": {"type": "succeeded", "message": {...}}}
        result = result_item.get('result', {})
        
        if not result:
            results_map[custom_id] = {'verdict': 'error', 'why': 'No result field'}
            continue
        
        result_type = result.get('type', '')
        if result_type != 'succeeded':
            error = result.get('error', {})
            results_map[custom_id] = {
                'verdict': 'error',
                'why': json.dumps(error) if error else f"Result type: {result_type}"
            }
            continue
        
        # Get message.content[0].text
        message = result.get('message', {})
        content_list = message.get('content', [])
        if not content_list:
            results_map[custom_id] = {'verdict': 'error', 'why': 'No content'}
            continue
        
        first_content = content_list[0]
        if isinstance(first_content, dict):
            text = first_content.get('text', '')
        else:
            text = str(first_content)
        
        if not text:
            results_map[custom_id] = {'verdict': 'error', 'why': 'No text'}
            continue
        
        # Parse JSON from text (may have code fences)
        try:
            parsed = _parse_json_strict(text)
            # Validate required fields
            if 'verdict' not in parsed or 'why' not in parsed:
                raise ValueError(f"Missing required fields: {list(parsed.keys())}")
            results_map[custom_id] = parsed
        except Exception as e:
            results_map[custom_id] = {
                'verdict': 'error',
                'why': f"Parse error: {str(e)}"
            }
    
    print(f"Parsed {len(results_map)} results")
    
    # Update rows
    updated_rows = []
    missing_count = 0
    error_count = 0
    success_count = 0
    
    for i, row in enumerate(rows):
        custom_id = f"{run_id}_{i}"
        result = results_map.get(custom_id, {})
        
        if not result:
            missing_count += 1
        
        verdict = result.get('verdict', 'error')
        why = result.get('why', 'No response')
        
        if verdict == 'error':
            error_count += 1
        else:
            success_count += 1
        
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
    
    print(f"\nResults summary:")
    print(f"  Success: {success_count}")
    print(f"  Errors: {error_count}")
    print(f"  Missing: {missing_count}")
    
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
    return success_count, error_count, missing_count


if __name__ == '__main__':
    run_id = sys.argv[1] if len(sys.argv) > 1 else '20251029_161124'
    reparse_from_jsonl(run_id)

