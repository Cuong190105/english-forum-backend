from __future__ import annotations
import os
import time
import json
from typing import Optional

# Ensure project root is on sys.path when running as a script
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utilities.ai_generator_LLM_Clone import generate_with_llm


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Latency probe for a single CoT generation call.")
    ap.add_argument('--topic', default='Passive Voice', help='Locked topic to test')
    ap.add_argument('--text', default='Students are taught grammar in many schools.', help='Context/source text')
    ap.add_argument('--type', default='mcq', choices=['mcq','fill'])
    ap.add_argument('--items', type=int, default=1)
    ap.add_argument('--model', default=os.getenv('PRED_MODEL') or os.getenv('GEMINI_MODEL') or 'gemini-2.5-flash')
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--temperature', type=float, default=0.0)
    args = ap.parse_args()

    t0 = time.perf_counter()
    try:
        items = generate_with_llm(
            post_text=args.text,
            hw_type=args.type,
            num_items=max(1, int(args.items)),
            mode='cot',
            temperature=args.temperature,
            seed=args.seed,
            locked_topic=args.topic,
            model=args.model,
        )
        dt = time.perf_counter() - t0
        print(json.dumps({
            'ok': True,
            'elapsed_sec': round(dt, 3),
            'model': args.model,
            'topic': args.topic,
            'type': args.type,
            'items_returned': len(items),
            'first_prompt': (items[0]['question']['prompt'] if items else None)
        }, ensure_ascii=False))
    except Exception as e:
        dt = time.perf_counter() - t0
        print(json.dumps({
            'ok': False,
            'elapsed_sec': round(dt, 3),
            'error': str(e)
        }, ensure_ascii=False))


if __name__ == '__main__':
    main()
