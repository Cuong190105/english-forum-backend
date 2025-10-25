from __future__ import annotations
import json
import random
from pathlib import Path
from typing import List, Dict, Any, Tuple, DefaultDict
from collections import defaultdict


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open('r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                # skip bad line
                pass
    return rows


essential_keys = ["id", "source_text", "split", "level", "topic", "topic_category"]


def main():
    import argparse
    ap = argparse.ArgumentParser(description='Merge two labeled JSONL files and sample a balanced set by topic.')
    ap.add_argument('--inputs', required=True, nargs='+', help='Input labeled JSONL paths (2 or more)')
    ap.add_argument('--out-jsonl', required=True, help='Output JSONL path')
    ap.add_argument('--count', type=int, default=50, help='Approximate number of samples to output (default: 50)')
    ap.add_argument('--by', choices=['topic','topic_category'], default='topic', help='Balance key (default: topic)')
    ap.add_argument('--seed', type=int, default=0, help='Random seed for sampling')
    args = ap.parse_args()

    random.seed(args.seed)

    # Load and dedupe by id (fallback to source_text hash if missing id)
    all_rows: Dict[str, Dict[str, Any]] = {}
    for ip in args.inputs:
        p = Path(ip)
        if not p.exists():
            continue
        for r in load_jsonl(p):
            rid = str(r.get('id') or '').strip()
            if not rid:
                # fallback: hash of source_text
                st = r.get('corrected_text') or r.get('source_text') or r.get('text') or ''
                rid = str(abs(hash(st)))
                r['id'] = rid
            if rid not in all_rows:
                all_rows[rid] = r

    rows = list(all_rows.values())
    if not rows:
        raise SystemExit('No rows loaded from inputs')

    key = args.by
    groups: DefaultDict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        k = str(r.get(key) or '').strip()
        if not k:
            # drop items without the balancing key
            continue
        groups[k].append(r)

    K = len(groups)
    N = max(1, int(args.count))
    if K == 0:
        raise SystemExit('No groups found by the selected key')

    # target per group
    base = N // K
    rem = N % K

    # Shuffle each group for randomness
    for lst in groups.values():
        random.shuffle(lst)

    selected: List[Dict[str, Any]] = []
    # First pass: take base from each topic
    for k, lst in groups.items():
        take = min(base, len(lst))
        selected.extend(lst[:take])
        groups[k] = lst[take:]

    # Remaining quota
    need = N - len(selected)
    if need > 0:
        # Build a list of (k, remaining_count) sorted by remaining descending to pull from larger groups first
        pool: List[Tuple[str, int]] = sorted(((k, len(lst)) for k, lst in groups.items()), key=lambda x: x[1], reverse=True)
        idx = 0
        while need > 0 and pool and any(cnt > 0 for _, cnt in pool):
            k, cnt = pool[idx % len(pool)]
            if cnt > 0:
                selected.append(groups[k].pop())
                need -= 1
                # update cnt in pool
                pool[idx % len(pool)] = (k, cnt - 1)
            idx += 1

    # If total available < N, we will just output everything selected + leftover until exhausted
    if len(selected) < N:
        for k, lst in groups.items():
            for r in lst:
                if len(selected) >= N:
                    break
                selected.append(r)
            if len(selected) >= N:
                break

    # Keep only essential keys, preserve others if present
    out = []
    for r in selected:
        o = {k: r.get(k) for k in essential_keys}
        # Preserve corrected_text if exists, else source_text
        if 'corrected_text' in r:
            o['corrected_text'] = r['corrected_text']
        elif 'source_text' in r:
            o['source_text'] = r['source_text']
        else:
            o['text'] = r.get('text','')
        out.append(o)

    out_path = Path(args.out_jsonl)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open('w', encoding='utf-8') as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')

    # Print brief summary
    counts: Dict[str, int] = defaultdict(int)
    for r in out:
        counts[str(r.get(key))] += 1
    print(f'Done: wrote {len(out)} rows to {out_path} (balanced by {key} across {len(counts)} groups)')
    for k, v in sorted(counts.items(), key=lambda x: (-x[1], x[0])):
        print(f'  {k}: {v}')


if __name__ == '__main__':
    main()
