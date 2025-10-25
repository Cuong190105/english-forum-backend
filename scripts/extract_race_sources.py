from __future__ import annotations
import argparse
import json
import random
import re
from pathlib import Path
from typing import Dict, Any, List, Tuple


def load_race_from_hf(splits: List[str] | None = None, config: str = "all") -> List[Dict[str, Any]]:
    """Load RACE (ehovy/race) from HuggingFace datasets.
    Returns a flat list of dicts with at least: {split, level, id, article} per question row.
    We'll later deduplicate by file key to keep a single article per original file.
    """
    try:
        from datasets import load_dataset  # type: ignore
    except Exception as e:
        raise RuntimeError("Missing 'datasets' package. Install with: pip install datasets") from e

    ds = load_dataset("ehovy/race", config)
    rows: List[Dict[str, Any]] = []
    # Determine which splits to include
    target_splits = list(ds.keys()) if not splits else [s for s in splits if s in ds]
    for sp in target_splits:
        for ex in ds[sp]:
            # Common fields across variants
            article = ex.get("article") or ex.get("passage") or ""
            level = ex.get("level") or ex.get("difficulty") or ""
            ex_id = ex.get("id") or ex.get("example_id") or ex.get("file") or ""
            rows.append({
                "split": sp,
                "level": str(level),
                "id": str(ex_id),
                "article": str(article),
            })
    return rows


def build_unique_articles(rows: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Deduplicate by article text; keep the first occurrence of each unique article.
    Output rows: {id, source_text, split, level}
    - id: taken from the first example's id (not guaranteed to be globally unique beyond the article).
    """
    seen: set[str] = set()
    uniq: List[Dict[str, str]] = []
    for ex in rows:
        art = (ex.get("article") or "").strip()
        if not art:
            continue
        if art in seen:
            continue
        seen.add(art)
        uniq.append({
            "id": str(ex.get("id") or ex.get("file") or ""),
            "source_text": art,
            "split": str(ex.get("split") or ""),
            "level": str(ex.get("level") or ""),
        })
    return uniq


def sample_rows(rows: List[Dict[str, str]], count: int, seed: int, balanced_by_level: bool = False) -> List[Dict[str, str]]:
    rng = random.Random(seed)
    if not balanced_by_level:
        rows2 = rows[:]
        rng.shuffle(rows2)
        return rows2[:count] if count > 0 else rows2
    # Balanced by level (middle/high) approximately
    by_level: Dict[str, List[Dict[str, str]]] = {}
    for r in rows:
        by_level.setdefault(r.get("level") or "", []).append(r)
    k = max(1, count // max(1, len(by_level))) if count > 0 else None
    out: List[Dict[str, str]] = []
    for lvl, bucket in by_level.items():
        rng.shuffle(bucket)
        if k is None:
            out.extend(bucket)
        else:
            out.extend(bucket[:k])
    # If we need to top-up to reach count, fill from remaining pool
    if count > 0 and len(out) < count:
        chosen = set((r["id"]) for r in out)
        pool = rows[:]
        rng.shuffle(pool)
        for r in pool:
            if len(out) >= count:
                break
            if r["id"] not in chosen:
                out.append(r)
                chosen.add(r["id"])
    return out


def load_excluded_texts(paths: List[Path]) -> set[str]:
    """Load a set of source_text strings to exclude from sampling.
    Accept fields in JSONL lines: corrected_text > source_text > text > article.
    """
    excluded: set[str] = set()
    for p in paths:
        if not p or not p.exists():
            continue
        with p.open('r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                text = rec.get('corrected_text') or rec.get('source_text') or rec.get('text') or rec.get('article') or ''
                text = str(text).strip()
                if text:
                    excluded.add(text)
    return excluded


def write_csv(path: Path, rows: List[Dict[str, str]]):
    import csv
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['id','source_text','split','level'])
        w.writeheader()
        for r in rows:
            w.writerow(r)


def write_jsonl(path: Path, rows: List[Dict[str, str]]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main():
    p = argparse.ArgumentParser(description='Extract unique RACE articles (one per file) as source texts.')
    p.add_argument('--from-hf', action='store_true', help='Load from HuggingFace datasets ehovy/race (requires datasets)')
    p.add_argument('--config', default='all', help='HuggingFace config for RACE (default: all)')
    p.add_argument('--splits', default='', help='Comma-separated splits to include (default: all available)')
    p.add_argument('--count', type=int, default=0, help='Optional max number of unique articles to sample (0 = all)')
    p.add_argument('--seed', type=int, default=0)
    p.add_argument('--balanced-per-level', action='store_true', help='Approx. balance between middle/high if present')
    p.add_argument('--out-csv', default='benchmark/source_texts/race_source_texts.csv')
    p.add_argument('--out-jsonl', default='benchmark/source_texts/race_source_texts.jsonl')
    p.add_argument('--exclude-jsonl', action='append', default=[], help='Path(s) to JSONL files whose texts should be excluded (can repeat or use comma-separated paths)')
    args = p.parse_args()

    if not args.from_hf:
        raise SystemExit('Please pass --from-hf to load ehovy/race from HuggingFace')

    splits = [s.strip() for s in args.splits.split(',') if s.strip()] if args.splits else None
    rows = load_race_from_hf(splits=splits, config=args.config)
    uniq = build_unique_articles(rows)
    # Exclusions
    ex_paths: List[Path] = []
    for it in (args.exclude_jsonl or []):
        for pth in str(it).split(','):
            pth = pth.strip()
            if pth:
                ex_paths.append(Path(pth))
    if ex_paths:
        excluded = load_excluded_texts(ex_paths)
        uniq = [r for r in uniq if (r.get('source_text','').strip()) not in excluded]
    chosen = sample_rows(uniq, args.count, args.seed, balanced_by_level=args.balanced_per_level)
    write_csv(Path(args.out_csv), chosen)
    write_jsonl(Path(args.out_jsonl), chosen)
    print(f"Done: {len(chosen)} unique articles written (from {len(uniq)} unique files).")


if __name__ == '__main__':
    main()
