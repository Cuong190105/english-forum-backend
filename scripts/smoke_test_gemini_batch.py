from __future__ import annotations
import os
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure project root on path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Reuse the batch call from judge_batch_runner
from scripts.judge_batch_runner import call_gemini_batch_api

def main():
    import argparse
    ap = argparse.ArgumentParser(description='Smoke test Gemini Batch API with 2-3 prompts')
    # Default to a batch-friendly model name in the documented 'models/...' form
    ap.add_argument('--model', default=os.getenv('JUDGE_MODEL') or 'models/gemini-2.5-flash')
    ap.add_argument('--count', type=int, default=3, help='Number of prompts (2-3 recommended)')
    ap.add_argument('--no-response-schema', dest='use_response_schema', action='store_false')
    ap.set_defaults(use_response_schema=True)
    args = ap.parse_args()

    # Simple prompts that should return structured JSON when response_schema is provided
    base_prompts = [
        "You are a JSON-only bot. Return a JSON object with keys: verdict (string), why (string). Set verdict='correct' and explain briefly in why.",
        "Return strictly JSON with keys verdict and why. verdict should be 'acceptable' and include a one-sentence reason.",
        "Only output JSON: {verdict: 'ambiguous', why: '<short reason>'}. No extra text.",
    ]
    prompts: List[str] = base_prompts[: max(1, min(3, args.count))]

    response_schema: Optional[Dict[str, Any]] = None
    if args.use_response_schema:
        response_schema = {
            'type': 'object',
            'properties': {
                'verdict': {'type': 'string'},
                'why': {'type': 'string'}
            },
            'required': ['verdict']
        }

    texts, meta = call_gemini_batch_api(
        prompts=prompts,
        model=args.model,
        display_name='smoke_test_gemini_batch',
        response_schema=response_schema,
        poll_interval_s=5.0,
        timeout_s=60 * 10,
    )

    print("=== Gemini Batch Smoke Test Results ===")
    if meta:
        print(json.dumps(meta, ensure_ascii=False))
    for i, (p, t) in enumerate(zip(prompts, texts)):
        print(f"\n--- Item {i} ---")
        print("Prompt:")
        print(p)
        print("Response:")
        print(t)

if __name__ == '__main__':
    main()
