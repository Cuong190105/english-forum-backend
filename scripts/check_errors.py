"""Check errors in Claude batch results."""
import json
import csv
from pathlib import Path

run_dir = Path("benchmark/reports/20251029_161124_claude")
per_item_csv = run_dir / 'per_item_claude.csv'
results_file = list(run_dir.glob("*_results.jsonl"))[0]

# Load per_item_claude.csv
rows = []
with per_item_csv.open('r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for r in reader:
        rows.append(r)

# Find errors
errors = [r for r in rows if r.get('claude_judge_verdict', '').strip() == 'error']
print(f"Total errors: {len(errors)}")

# Load results.jsonl to check what's wrong
results_map = {}
with results_file.open('r', encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if line:
            item = json.loads(line)
            custom_id = item.get('custom_id', '')
            if custom_id:
                results_map[custom_id] = item

# Check error rows
print("\nError details:")
for i, row in enumerate(errors[:10]):
    idx = int(row.get('idx', 0))
    custom_id = f"20251029_161124_{idx-1}"  # 0-based
    result_item = results_map.get(custom_id)
    
    print(f"\nRow {idx} (custom_id: {custom_id}):")
    print(f"  Verdict: {row.get('claude_judge_verdict')}")
    print(f"  Why: {row.get('claude_judge_why', '')[:200]}")
    
    if result_item:
        result = result_item.get('result', {})
        result_type = result.get('type', '')
        print(f"  Result type: {result_type}")
        
        if result_type == 'succeeded':
            message = result.get('message', {})
            content = message.get('content', [])
            if content:
                text = content[0].get('text', '') if isinstance(content[0], dict) else str(content[0])
                print(f"  Text preview: {text[:200]}")
    else:
        print(f"  No result found in results.jsonl!")

