"""Check judge scores and explain delta calculation."""
import csv
from pathlib import Path
from statistics import mean

run_dir = Path("benchmark/reports/20251029_161124")
per_item_csv = run_dir / 'per_item.csv'

rows = []
with per_item_csv.open('r', encoding='utf-8', newline='') as f:
    reader = csv.DictReader(f)
    for r in reader:
        rows.append(r)

# Group by (source_text_sha, topic, type, seed, config)
groups = {}
for row in rows:
    sha = row.get('source_text_sha', '').strip()
    topic = row.get('topic', '').strip()
    hw_type = row.get('type', '').strip()
    seed = row.get('seed', '').strip()
    config = row.get('config', '').strip()
    
    if not all([sha, topic, hw_type, seed, config]):
        continue
    
    if config not in {'minimal', 'cot'}:
        continue
    
    key = (sha, topic, hw_type, seed, config)
    if key not in groups:
        groups[key] = []
    
    js = row.get('judge_score', '').strip()
    if js:
        try:
            groups[key].append(float(js))
        except:
            pass

# Show example calculation
print("Example delta calculation:")
print("="*60)

example_shown = False
pair_groups = {}

for key, scores in list(groups.items())[:10]:
    sha, topic, hw_type, seed, config = key
    pair_key = (sha, topic, hw_type, seed)
    
    if pair_key not in pair_groups:
        pair_groups[pair_key] = {'minimal': [], 'cot': []}
    
    if config == 'minimal':
        pair_groups[pair_key]['minimal'].extend(scores)
    elif config == 'cot':
        pair_groups[pair_key]['cot'].extend(scores)

for pair_key, config_map in list(pair_groups.items())[:2]:
    if 'minimal' in config_map and 'cot' in config_map and config_map['minimal'] and config_map['cot']:
        min_mean = mean(config_map['minimal'])
        cot_mean = mean(config_map['cot'])
        delta = cot_mean - min_mean
        
        print(f"\nPair: topic={pair_key[1][:15]}..., type={pair_key[2]}, seed={pair_key[3]}")
        print(f"  Minimal: {len(config_map['minimal'])} items")
        print(f"    Scores: {[round(s, 2) for s in config_map['minimal'][:5]]}...")
        print(f"    Mean = {round(min_mean, 4)}")
        print(f"  CoT: {len(config_map['cot'])} items")
        print(f"    Scores: {[round(s, 2) for s in config_map['cot'][:5]]}...")
        print(f"    Mean = {round(cot_mean, 4)}")
        print(f"  Delta = mean(cot) - mean(minimal) = {round(cot_mean, 4)} - {round(min_mean, 4)} = {round(delta, 4)}")
        print(f"\n  NOTE: NOT tong diem, ma la TRUNG BINH cua tat ca items trong cung pair")

# Calculate overall delta
all_pairs = {}
for key, scores in groups.items():
    sha, topic, hw_type, seed, config = key
    pair_key = (sha, topic, hw_type, seed)
    
    if pair_key not in all_pairs:
        all_pairs[pair_key] = {'minimal': [], 'cot': []}
    
    if config == 'minimal':
        all_pairs[pair_key]['minimal'].extend(scores)
    elif config == 'cot':
        all_pairs[pair_key]['cot'].extend(scores)

deltas = []
for pair_key, config_map in all_pairs.items():
    if 'minimal' in config_map and 'cot' in config_map and config_map['minimal'] and config_map['cot']:
        min_mean = mean(config_map['minimal'])
        cot_mean = mean(config_map['cot'])
        deltas.append(cot_mean - min_mean)

print(f"\n" + "="*60)
print(f"Overall delta calculation:")
print(f"="*60)
print(f"Total pairs: {len(deltas)}")
print(f"Delta mean = {round(mean(deltas), 4)}")
print(f"\nExplanation:")
print(f"1. For each pair (source_text_sha, topic, type, seed):")
print(f"   - Calculate mean of all judge_scores in minimal config")
print(f"   - Calculate mean of all judge_scores in cot config")
print(f"   - Delta_pair = mean(cot) - mean(minimal)")
print(f"2. Then calculate mean of all 60 deltas_pair")
print(f"3. Result is delta_mean in paired_overall.csv")
print(f"\nNOT sum of scores, but MEAN of scores for each config in each pair")

