from __future__ import annotations
import argparse
import json
import random
from pathlib import Path
from typing import List, Dict, Any, Tuple


def read_json_or_jsonl(path: Path) -> List[Dict[str, Any]]:
    text = path.read_text(encoding='utf-8').strip()
    if not text:
        return []
    if text.startswith('['):
        return json.loads(text)
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def load_jfleg_from_hf(splits: List[str]) -> List[Dict[str, Any]]:
    try:
        from datasets import load_dataset  # type: ignore
    except Exception as e:
        raise RuntimeError("Missing 'datasets' package. Install with: pip install datasets") from e

    ds = load_dataset('jhu-clsp/jfleg')
    items: List[Dict[str, Any]] = []
    for sp in splits:
        if sp not in ds:
            continue
        for ex in ds[sp]:
            # ex has fields: sentence, corrections (list)
            items.append({'split': sp, 'sentence': ex.get('sentence',''), 'corrections': ex.get('corrections') or [], 'id': ex.get('id')})
    return items


def choose_corrected_text(it: Dict[str, Any], *, rng: random.Random) -> str:
    corrs = it.get('corrections') or []
    if corrs:
        return rng.choice(corrs)
    # fallback to raw sentence or already-prepared source_text
    return it.get('sentence') or it.get('source_text') or ''


def _dedupe_pool(pool: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen = set()
    uniq: List[Dict[str,str]] = []
    for r in pool:
        key = r['source_text'].strip()
        if key and key not in seen:
            seen.add(key)
            uniq.append(r)
    return uniq


def to_rows(items: List[Dict[str, Any]], count: int, seed: int) -> List[Dict[str, str]]:
    rng = random.Random(seed)
    pool: List[Dict[str, str]] = []
    for it in items:
        src = choose_corrected_text(it, rng=rng)
        if not src:
            continue
        sid = str(it.get('id') or '')
        pool.append({'id': sid, 'source_text': src, 'split': str(it.get('split') or '')})

    # Deduplicate by source_text
    uniq = _dedupe_pool(pool)

    if len(uniq) < count:
        # Not enough unique rows; cap to available
        return uniq

    rng.shuffle(uniq)
    return uniq[:count]


def to_rows_balanced(items: List[Dict[str, Any]], count: int, seed: int, splits: List[str]) -> List[Dict[str, str]]:
    """Sample approximately count/len(splits) per split (dev/test) then merge and
    deduplicate across the union; if not enough unique, cap to available."""
    rng = random.Random(seed)
    # Bucket items by split
    by_split: Dict[str, List[Dict[str, Any]]] = {sp: [] for sp in splits}
    for it in items:
        sp = str(it.get('split') or '')
        if sp in by_split:
            by_split[sp].append(it)

    per = max(1, count // max(1, len(splits)))
    pools: List[Dict[str, str]] = []
    for sp in splits:
        bucket = by_split.get(sp, [])
        local_pool: List[Dict[str, str]] = []
        for it in bucket:
            src = choose_corrected_text(it, rng=rng)
            if not src:
                continue
            sid = str(it.get('id') or '')
            local_pool.append({'id': sid, 'source_text': src, 'split': sp})
        local_uniq = _dedupe_pool(local_pool)
        rng.shuffle(local_uniq)
        pools.extend(local_uniq[:per])

    # Merge and dedupe globally, then, if fewer than count, try to top up from remaining items
    merged = _dedupe_pool(pools)
    if len(merged) >= count:
        rng.shuffle(merged)
        return merged[:count]

    # Top-up from all items
    all_pool: List[Dict[str, str]] = []
    for it in items:
        src = choose_corrected_text(it, rng=rng)
        if not src:
            continue
        all_pool.append({'id': str(it.get('id') or ''), 'source_text': src, 'split': str(it.get('split') or '')})
    all_uniq = _dedupe_pool(all_pool)
    rng.shuffle(all_uniq)
    # Keep current merged then append new uniques until reaching count
    chosen_keys = {r['source_text'] for r in merged}
    for r in all_uniq:
        if len(merged) >= count:
            break
        if r['source_text'] not in chosen_keys:
            merged.append(r)
            chosen_keys.add(r['source_text'])
    return merged


def write_csv(path: Path, rows: List[Dict[str, str]]):
    import csv
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['id','source_text','split'])
        w.writeheader()
        for r in rows:
            w.writerow(r)


def write_jsonl(path: Path, rows: List[Dict[str, str]]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def write_xlsx(path: Path, rows: List[Dict[str, str]]):
    try:
        import xlsxwriter  # type: ignore
    except Exception:
        # silently skip if not installed
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = xlsxwriter.Workbook(str(path))
    ws = wb.add_worksheet('source_texts')
    header_fmt = wb.add_format({'bold': True})
    wrap_fmt = wb.add_format({'text_wrap': True, 'valign': 'top'})
    cols = ['id','source_text','split']
    for c, name in enumerate(cols):
        ws.write(0, c, name, header_fmt)
    for r, row in enumerate(rows, start=1):
        ws.write(r, 0, row.get('id',''))
        ws.write(r, 1, row.get('source_text',''), wrap_fmt)
        ws.write(r, 2, row.get('split',''))
    ws.freeze_panes(1,0)
    ws.set_column(0, 0, 10)
    ws.set_column(1, 1, 100)
    ws.set_column(2, 2, 10)
    wb.close()


def main():
    p = argparse.ArgumentParser(description='Extract N corrected JFLEG source texts for reuse as generation contexts.')
    p.add_argument('--count', type=int, default=1000)
    p.add_argument('--seed', type=int, default=0)
    p.add_argument('--splits', default='dev,test', help='Comma-separated splits to include from HF (e.g., dev,test)')
    p.add_argument('--from-hf', action='store_true', help='Load from HuggingFace datasets (requires datasets package)')
    p.add_argument('--input', help='Optional local JSON/JSONL file with fields {sentence, corrections[], id, split}')
    p.add_argument('--out-csv', default='benchmark/source_texts/jfleg_1000_source_texts.csv')
    p.add_argument('--out-jsonl', default='benchmark/source_texts/jfleg_1000_source_texts.jsonl')
    p.add_argument('--out-xlsx', default='benchmark/source_texts/jfleg_1000_source_texts.xlsx')
    p.add_argument('--balanced-per-split', action='store_true', help='Pick approximately count/len(splits) from each split (e.g., dev/test).')
    args = p.parse_args()

    rows_list: List[Dict[str, Any]] = []
    if args.from_hf:
        splits = [s.strip() for s in args.splits.split(',') if s.strip()]
        # Normalize common aliases
        alias = {'validation': 'dev', 'val': 'dev'}
        splits = [alias.get(s, s) for s in splits]
        rows_list = load_jfleg_from_hf(splits)
    elif args.input:
        rows_list = read_json_or_jsonl(Path(args.input))
    else:
        raise RuntimeError('Provide --from-hf to pull JFLEG or --input to read a local file.')

    # Balanced per split if requested (e.g., ~500 from dev and ~500 from test when count=1000)
    if args.balanced_per_split and args.from_hf:
        rows = to_rows_balanced(rows_list, args.count, args.seed, splits)
    else:
        rows = to_rows(rows_list, args.count, args.seed)
    write_csv(Path(args.out_csv), rows)
    if args.out_jsonl:
        write_jsonl(Path(args.out_jsonl), rows)
    if args.out_xlsx:
        write_xlsx(Path(args.out_xlsx), rows)
    print(f"Done: {len(rows)} rows written.")


if __name__ == '__main__':
    main()
