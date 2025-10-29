from __future__ import annotations
import json
import argparse
from pathlib import Path
from typing import List, Dict, Any
from collections import defaultdict, Counter


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    """Read JSONL file and return list of records."""
    rows: List[Dict[str, Any]] = []
    with path.open('r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                rows.append(rec)
            except Exception as e:
                print(f"Warning: failed to parse line: {e}")
                continue
    return rows


def write_jsonl(path: Path, rows: List[Dict[str, Any]]):
    """Write records to JSONL file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')


def balance_by_topic(rows: List[Dict[str, Any]], per_topic: int = 5, target_topics: int = 20) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Balance dataset by topic.
    
    Args:
        rows: Input records with 'topic' field
        per_topic: Number of source texts per topic (default: 5)
        target_topics: Target number of topics (default: 20)
    
    Returns:
        Tuple of (selected_rows, stats)
    """
    # Group by topic
    by_topic: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        topic = r.get('topic') or r.get('topic_display') or ''
        if not topic:
            print(f"Warning: skipping row without topic: {r.get('id', 'unknown')}")
            continue
        by_topic[topic].append(r)
    
    # Count available topics
    topic_counts = Counter({t: len(items) for t, items in by_topic.items()})
    
    print(f"\n=== Topic Statistics ===")
    print(f"Total unique topics: {len(by_topic)}")
    print(f"Total source texts: {len(rows)}")
    print(f"\nTop 30 topics by count:")
    for topic, count in topic_counts.most_common(30):
        print(f"  {topic}: {count} texts")
    
    # Find topics with at least per_topic texts
    eligible_topics = {t: items for t, items in by_topic.items() if len(items) >= per_topic}
    
    print(f"\n=== Selection Criteria ===")
    print(f"Required texts per topic: {per_topic}")
    print(f"Target number of topics: {target_topics}")
    print(f"Eligible topics (>= {per_topic} texts): {len(eligible_topics)}")
    
    if len(eligible_topics) < target_topics:
        print(f"\n⚠️  WARNING: Only {len(eligible_topics)} topics have >= {per_topic} texts")
        print(f"   Requested {target_topics} topics but can only provide {len(eligible_topics)}")
        print(f"\n   Options:")
        print(f"   1. Reduce --per-topic (current: {per_topic})")
        print(f"   2. Reduce --target-topics (current: {target_topics})")
        print(f"   3. Add more labeled data")
        
        # Show shortfall details
        shortfall = target_topics - len(eligible_topics)
        print(f"\n   Shortfall: {shortfall} topics")
        
        # Show topics that are close (have per_topic-1 or per_topic-2 texts)
        near_miss = {t: len(items) for t, items in by_topic.items() 
                     if per_topic - 2 <= len(items) < per_topic}
        if near_miss:
            print(f"\n   Topics close to threshold:")
            for t, c in sorted(near_miss.items(), key=lambda x: -x[1]):
                print(f"     {t}: {c} texts (need {per_topic - c} more)")
    
    # Select top N eligible topics by count (prioritize topics with more data)
    selected_topics = sorted(eligible_topics.keys(), 
                            key=lambda t: len(eligible_topics[t]), 
                            reverse=True)[:target_topics]
    
    # Sample per_topic texts from each selected topic
    selected_rows: List[Dict[str, Any]] = []
    final_counts: Dict[str, int] = {}
    
    for topic in selected_topics:
        items = eligible_topics[topic][:per_topic]  # Take first per_topic items
        selected_rows.extend(items)
        final_counts[topic] = len(items)
    
    # Stats
    stats = {
        'total_input_texts': len(rows),
        'unique_input_topics': len(by_topic),
        'eligible_topics': len(eligible_topics),
        'selected_topics': len(selected_topics),
        'per_topic': per_topic,
        'total_output_texts': len(selected_rows),
        'topics': final_counts,
    }
    
    print(f"\n=== Final Selection ===")
    print(f"Selected topics: {len(selected_topics)}")
    print(f"Total texts: {len(selected_rows)} ({len(selected_topics)} × {per_topic})")
    print(f"\nSelected topics:")
    for topic in sorted(selected_topics):
        print(f"  {topic}: {final_counts[topic]} texts")
    
    return selected_rows, stats


def main():
    ap = argparse.ArgumentParser(
        description='Balance JSONL dataset by topic: select N topics with M texts each.'
    )
    ap.add_argument('--input', nargs='+', required=True, 
                    help='Input JSONL file(s) to combine (e.g., file1.jsonl file2.jsonl)')
    ap.add_argument('--output', required=True, 
                    help='Output JSONL path for balanced dataset')
    ap.add_argument('--per-topic', type=int, default=5, 
                    help='Number of source texts per topic (default: 5)')
    ap.add_argument('--target-topics', type=int, default=20, 
                    help='Target number of topics (default: 20)')
    ap.add_argument('--stats-json', default='', 
                    help='Optional: save stats to JSON file')
    args = ap.parse_args()
    
    # Load all input files
    all_rows: List[Dict[str, Any]] = []
    for inp in args.input:
        path = Path(inp)
        if not path.exists():
            print(f"Warning: {path} not found, skipping")
            continue
        rows = read_jsonl(path)
        print(f"Loaded {len(rows)} rows from {path}")
        all_rows.extend(rows)
    
    if not all_rows:
        raise SystemExit("No data loaded. Check input paths.")
    
    print(f"\nTotal combined rows: {len(all_rows)}")
    
    # Balance
    selected, stats = balance_by_topic(
        all_rows, 
        per_topic=args.per_topic, 
        target_topics=args.target_topics
    )
    
    # Write output
    out_path = Path(args.output)
    write_jsonl(out_path, selected)
    print(f"\n✓ Wrote {len(selected)} balanced rows to: {out_path}")
    
    # Write stats
    if args.stats_json:
        stats_path = Path(args.stats_json)
        stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f"✓ Stats saved to: {stats_path}")


if __name__ == '__main__':
    main()

