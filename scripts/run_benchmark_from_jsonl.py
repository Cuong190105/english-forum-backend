from __future__ import annotations
import json
import sys
from pathlib import Path
from typing import List, Dict

# Ensure project root is on sys.path when running as a script
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

def parse_list_arg(s: str) -> List[str]:
    return [x.strip() for x in s.split(',') if x.strip()]


def main():
    import argparse
    ap = argparse.ArgumentParser(description='Run benchmark from a labeled JSONL (must contain topic and context text).')
    ap.add_argument('--input', required=True, help='Path to labeled JSONL (e.g., output from label_topics_for_sources.py)')
    ap.add_argument('--type', dest='hw_type', default='mcq', choices=['mcq','fill'], help='Question type to generate')
    ap.add_argument('--configs', default='minimal,cot', help='Comma-separated configs among: minimal,cot')
    ap.add_argument('--seeds', default='0', help='Comma-separated integer seeds, e.g. 0,1,2')
    ap.add_argument('--limit', type=int, default=0, help='Limit number of contexts (0 means all)')
    ap.add_argument('--run-id', default=None, help='Optional run id; default is timestamp')
    ap.add_argument('--items', type=int, default=10, help='Number of items to generate per source (default: 10)')
    ap.add_argument('--resume', action='store_true', help='Resume: reuse existing pred files if present to avoid regenerating')
    args = ap.parse_args()

    from benchmark.run_benchmark import run

    in_path = Path(args.input)
    topics: List[Dict[str,str]] = []

    with in_path.open('r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            topic = rec.get('topic')
            # Prefer corrected_text else source_text
            text = rec.get('corrected_text') or rec.get('source_text') or rec.get('text') or ''
            if not topic or not text:
                continue
            topics.append({'topic': topic, 'type': args.hw_type, 'post_text': text})
            if args.limit and len(topics) >= args.limit:
                break

    if not topics:
        raise SystemExit('No valid records found with topic and text')

    configs = parse_list_arg(args.configs)
    seeds = [int(s) for s in parse_list_arg(args.seeds)]

    run(topics, configs, seeds, run_id=args.run_id, num_items=max(1, int(args.items)), resume=bool(args.resume))


if __name__ == '__main__':
    main()
