from __future__ import annotations
import os
import csv
import json
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Tuple

import sys
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmark.judge_triple import judge_triple_batch_mcq, judge_triple_batch_fill
from benchmark.report import append_per_item_rows


def sanitize_topic(topic: str) -> str:
    import re
    return re.sub(r"[^A-Za-z0-9._-]+", "_", topic)


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode('utf-8')).hexdigest()


def load_existing_rows(out_csv: Path) -> List[Dict[str, Any]]:
    if not out_csv.exists():
        return []
    with out_csv.open('r', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def append_rows(out_csv: Path, rows: List[Dict[str, Any]]) -> None:
    # Reuse the centralized writer to guarantee the full legacy schema is present
    append_per_item_rows(out_csv, rows)


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    with path.open('r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser(description='Triple-judge from a labeled JSONL using pre-existing pred (and gold) files. Logs progress and supports resume.')
    ap.add_argument('--input', required=True, help='Path to labeled JSONL (e.g., data/race_final_balanced_20x5.jsonl)')
    ap.add_argument('--type', dest='hw_type', required=True, choices=['mcq','fill'], help='Question type to judge')
    ap.add_argument('--configs', default='minimal,cot', help='Comma-separated configs to judge, e.g. minimal,cot')
    ap.add_argument('--seeds', default='0', help='Comma-separated integer seeds, e.g. 0,1')
    ap.add_argument('--run-id', required=True, help='Run id for output folder naming, e.g. 20251029_161124_triple')
    ap.add_argument('--resume', action='store_true', help='Resume: skip groups already fully written')
    args = ap.parse_args()

    in_path = Path(args.input)
    hw_type = args.hw_type
    configs = [s.strip() for s in args.configs.split(',') if s.strip()]
    seeds = [int(s.strip()) for s in args.seeds.split(',') if s.strip()]

    # Output CSV aggregated
    out_dir = Path(f"benchmark/reports/{args.run_id}")
    out_csv = out_dir / 'per_item.csv'
    existing = load_existing_rows(out_csv) if args.resume else []

    # Build a set of completed groups for resume
    done_groups: Dict[Tuple[str,str,str,int,str], int] = {}
    if existing:
        from collections import Counter
        cnt = Counter()
        for r in existing:
            key = (
                str(r.get('config','')),
                str(r.get('topic','')),
                str(r.get('type','')),
                int(r.get('seed') or 0),
                str(r.get('source_text_sha','')),
            )
            cnt[key] += 1
        done_groups = dict(cnt)

    recs = load_jsonl(in_path)
    print(f"[Triple] Loaded {len(recs)} records from {in_path}")

    for rec_idx, rec in enumerate(recs):
        topic = rec.get('topic') or ''
        text = rec.get('source_text') or rec.get('text') or ''
        if not topic or not text:
            continue
        sha = sha256_text(text)
        topic_san = sanitize_topic(topic)

        for config in configs:
            for seed in seeds:
                # pred path
                pred_path = Path(f"benchmark/pred/{config}/{topic_san}/{hw_type}/{sha}/seed{seed}.json")
                if not pred_path.exists():
                    print(f"[Triple] SKIP missing pred: {pred_path}")
                    continue

                items = json.loads(pred_path.read_text(encoding='utf-8'))
                if not isinstance(items, list) or not items:
                    print(f"[Triple] SKIP empty pred: {pred_path}")
                    continue

                key = (config, topic, hw_type, seed, sha)
                if args.resume and done_groups.get(key, 0) >= len(items):
                    print(f"[Triple] RESUME skip group (done): config={config} topic={topic} seed={seed} n={len(items)}")
                    continue

                print(f"[Triple] Group start: rec={rec_idx+1}/{len(recs)} config={config} topic={topic} type={hw_type} seed={seed} sha={sha}")
                # Judge in batch
                if hw_type == 'mcq':
                    results = judge_triple_batch_mcq(items, topic=topic)
                else:
                    results = judge_triple_batch_fill(items, topic=topic)

                # Prepare rows and append
                rows: List[Dict[str, Any]] = []
                for i, it in enumerate(items):
                    q = it.get('question', {})
                    rr = {
                        # Core identity
                        'run_id': args.run_id,
                        'config': config,
                        'topic': topic,
                        'type': hw_type,
                        'seed': seed,
                        'source_text_sha': sha,
                        'idx': i+1,
                        # IDs (gold may be unknown here)
                        'qid_gold': '',
                        'qid_pred': q.get('id') or f"{i+1}",
                        # Structural/semantic metrics not available in this judge-only pass
                        'structural_valid': '',
                        'question_sim': '',
                        'ans_sim': '',
                        'distractor_diversity': '',
                        'ans_score': '',
                        'item_score': '',
                        # Legacy two-judge fields (left empty in triple-judge flow)
                        'judge_verdict': '',
                        'judge_score': '',
                        'judge_why': '',
                        'judge2_verdict': '',
                        'judge2_score': '',
                        'judge2_why': '',
                        # Extended 3-judge fields
                        'row_idx': '',
                        'judge_gemini_verdict': results[i].get('gemini_verdict',''),
                        'judge_gemini_why': results[i].get('gemini_why',''),
                        'judge_claude_verdict': results[i].get('claude_verdict',''),
                        'judge_claude_why': results[i].get('claude_why',''),
                        'judge_deepseek_verdict': results[i].get('deepseek_verdict',''),
                        'judge_deepseek_why': results[i].get('deepseek_why',''),
                    }
                    rows.append(rr)

                append_rows(out_csv, rows)
                print(f"[Triple] Group done: wrote {len(rows)} rows -> {out_csv}")

    print(f"[Triple] Completed. Output: {out_csv}")


if __name__ == '__main__':
    main()
