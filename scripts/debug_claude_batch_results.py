"""Debug script to inspect Claude batch results structure."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from scripts.judge_with_claude_batch import retrieve_batch_status, retrieve_batch_results

# You need to provide a batch_id that was created
# For debugging, let's check if there's a log or we can recreate one

# For now, let's check the structure of a sample result from the docs
sample_result_structure = {
    "custom_id": "my-first-request",
    "type": "success",  # or "error"
    "output": {
        "id": "msg_xxx",
        "type": "message",
        "role": "assistant",
        "content": [
            {
                "type": "text",
                "text": '{"verdict": "correct", "why": "..."}'
            }
        ],
        "model": "claude-haiku-4-5",
        "stop_reason": "end_turn",
        "usage": {
            "input_tokens": 100,
            "output_tokens": 50
        }
    }
}

print("Expected structure based on docs:")
print(json.dumps(sample_result_structure, indent=2))

print("\n" + "="*60)
print("If you have a batch_id, provide it as argument to debug:")
print("  python scripts/debug_claude_batch_results.py <batch_id>")
print("="*60)

if len(sys.argv) > 1:
    batch_id = sys.argv[1]
    print(f"\nRetrieving batch results for {batch_id}...")
    try:
        results = retrieve_batch_results(batch_id)
        print(f"\nRetrieved {len(results)} results")
        
        if results:
            print("\nFirst result structure:")
            print(json.dumps(results[0], indent=2))
            
            print("\n\nChecking custom_ids:")
            custom_ids = [r.get('custom_id', 'MISSING') for r in results[:10]]
            print(f"  First 10 custom_ids: {custom_ids}")
            
            print("\n\nChecking result types:")
            types = [r.get('type', 'MISSING') for r in results[:10]]
            print(f"  First 10 types: {types}")
            
            print("\n\nSample successful result (if any):")
            success_results = [r for r in results if r.get('type') != 'error']
            if success_results:
                print(json.dumps(success_results[0], indent=2))
            else:
                print("  No successful results found")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

