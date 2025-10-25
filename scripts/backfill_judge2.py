from __future__ import annotations
import os
import sys
import csv
import json
import time
import argparse
import re
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional


# Ensure the project root (parent of this file's directory) is on sys.path
def _ensure_repo_root_on_path() -> None:
    try:
        here = Path(__file__).resolve()
        repo_root = here.parent.parent  # scripts/ -> project root
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
    except Exception:
        # Best-effort; fall back to whatever sys.path provides
        pass

_ensure_repo_root_on_path()


def load_env(dotenv_path: str | None):
    try:
        from dotenv import load_dotenv  # type: ignore
        if dotenv_path and Path(dotenv_path).exists():
            load_dotenv(dotenv_path)
        else:
            load_dotenv()
    except Exception:
        pass


def vmap_for(hw_type: str) -> Dict[str, float]:
    if hw_type == 'mcq':
        return {'correct': 1.0, 'ambiguous': 0.5, 'incorrect': 0.0}
    else:
        return {'acceptable': 1.0, 'unacceptable': 0.0}


def safe_topic_name(topic: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", topic)


def find_pred_item(pred_path: Path, qid: str) -> Dict[str, Any]:
    arr = json.loads(pred_path.read_text(encoding='utf-8'))
    for it in arr:
        if it and isinstance(it, dict) and it.get('question', {}).get('id') == qid:
            return it
    # Fallback: index by numeric suffix if any
    try:
        n = int(''.join(ch for ch in qid if ch.isdigit()))
        if 1 <= n <= len(arr):
            return arr[n-1]
    except Exception:
        pass
    raise FileNotFoundError(f"Question id {qid} not found in {pred_path}")


def judge2_call(hw_type: str, item: Dict[str, Any], topic: str, model_override: str | None = None, context: Optional[str] = None) -> Dict[str, Any]:
    # Import lazily to avoid hard dependency when not used
    from benchmark import judge as j
    if model_override:
        # Allow overriding via environment for judge2
        os.environ['JUDGE2_MODEL'] = model_override
    if hw_type == 'mcq':
        stem = item['question']['prompt']
        options = {o['id']: o['label'] for o in item['question']['options']}
        correct_id = item['correctOptionId']
        # DeepSeek native only (no OpenRouter fallback)
        return j.judge_mcq_deepseek(stem, options, correct_id, topic, context=context)
    else:
        # fill-in-the-blank
        stem = item['question']['prompt']
        answer = item.get('answer') or item.get('correctAnswer') or ''
        # DeepSeek native only (no OpenRouter fallback)
        return j.judge_fill_deepseek(stem, answer, topic, context=context)


def _load_input_map(jsonl_path: Optional[Path]) -> Dict[str, str]:
    """Map sha256(source_text) -> source_text from a labeled input JSONL.
    Accepts fields: corrected_text > source_text > text.
    """
    if not jsonl_path or not jsonl_path.exists():
        return {}
    mp: Dict[str, str] = {}
    with jsonl_path.open('r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            text = rec.get('corrected_text') or rec.get('source_text') or rec.get('text') or ''
            if not text:
                continue
            import hashlib
            sha = hashlib.sha256(text.encode('utf-8')).hexdigest()
            mp[sha] = text
    return mp


def _truncate_context(s: str, max_chars: int) -> str:
    if max_chars <= 0 or len(s) <= max_chars:
        return s
    # Keep head and tail chunks for coverage
    keep = max_chars
    head = keep // 2
    tail = keep - head
    return s[:head] + "\n...\n" + s[-tail:]


def compute_group_stats(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    from statistics import mean, stdev
    from math import sqrt

    def clamp01(x: float) -> float:
        return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x

    # group by (run_id, config, topic, type, seed)
    groups: Dict[Tuple[str, str, str, str, str], List[Dict[str, Any]]] = {}
    for r in rows:
        key = (r['run_id'], r['config'], r['topic'], r['type'], str(r['seed']))
        groups.setdefault(key, []).append(r)

    out: List[Dict[str, Any]] = []
    for (run_id, config, topic, hw_type, seed), arr in groups.items():
        n_items = len(arr)
        # structural pass percent
        try:
            n_struct_pass = sum(int(x.get('structural_valid') or 0) for x in arr)
        except Exception:
            n_struct_pass = 0
        structural_pass_pct = (100.0 * n_struct_pass / n_items) if n_items > 0 else 0.0

        # semantic = item_score
        sem_vals = [float(x['item_score']) for x in arr if str(x.get('item_score','')).strip() != '']
        sem_mean = mean(sem_vals) if sem_vals else 0.0
        sem_std = stdev(sem_vals) if len(sem_vals) > 1 else 0.0
        sem_se = (sem_std / sqrt(n_items)) if n_items > 1 else 0.0
        sem_ci_low = clamp01(sem_mean - 1.96 * sem_se)
        sem_ci_high = clamp01(sem_mean + 1.96 * sem_se)

        # judge1
        j1_vals = [float(x['judge_score']) for x in arr if str(x.get('judge_score','')).strip() != '']
        j1_mean = mean(j1_vals) if j1_vals else 0.0
        j1_std = stdev(j1_vals) if len(j1_vals) > 1 else 0.0
        j1_se = (j1_std / sqrt(n_items)) if n_items > 1 else 0.0
        j1_ci_low = clamp01(j1_mean - 1.96 * j1_se)
        j1_ci_high = clamp01(j1_mean + 1.96 * j1_se)

        # judge2 (optional)
        j2_vals = [float(x['judge2_score']) for x in arr if str(x.get('judge2_score','')).strip() != '']
        has_j2 = len(j2_vals) > 0
        if has_j2:
            j2_mean = mean(j2_vals) if j2_vals else 0.0
            j2_std = stdev(j2_vals) if len(j2_vals) > 1 else 0.0
            j2_se = (j2_std / sqrt(n_items)) if n_items > 1 else 0.0
            j2_ci_low = clamp01(j2_mean - 1.96 * j2_se)
            j2_ci_high = clamp01(j2_mean + 1.96 * j2_se)
        else:
            j2_mean = j2_std = j2_se = j2_ci_low = j2_ci_high = ''

        out.append({
            'run_id': run_id,
            'config': config,
            'topic': topic,
            'type': hw_type,
            'seed': int(seed) if str(seed).isdigit() else seed,
            'n_items': n_items,
            'structural_pass_pct': round(structural_pass_pct, 2),
            'semantic_mean': round(sem_mean, 4),
            'semantic_std': round(sem_std, 4),
            'semantic_se': round(sem_se, 4),
            'semantic_ci95_low': round(sem_ci_low, 4),
            'semantic_ci95_high': round(sem_ci_high, 4),
            'judge_mean': round(j1_mean, 4),
            'judge_std': round(j1_std, 4),
            'judge_se': round(j1_se, 4),
            'judge_ci95_low': round(j1_ci_low, 4),
            'judge_ci95_high': round(j1_ci_high, 4),
            'judge2_mean': ('' if not has_j2 else round(j2_mean, 4)),
            'judge2_std': ('' if not has_j2 else round(j2_std, 4)),
            'judge2_se': ('' if not has_j2 else round(j2_se, 4)),
            'judge2_ci95_low': ('' if not has_j2 else round(j2_ci_low, 4)),
            'judge2_ci95_high': ('' if not has_j2 else round(j2_ci_high, 4)),
        })
    return out


def compute_inter_judge(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # Compute percent agreement and Cohen's kappa for mcq and fill
    from collections import Counter
    def stats_for(pairs: List[Tuple[str, str]], classes: List[str]):
        n = len(pairs)
        if n == 0:
            return dict(n=0, pa=0.0, pa_low=0.0, pa_high=0.0, kappa=0.0, ac1=0.0)
        po = sum(1 for a,b in pairs if a == b) / n
        a_counts = Counter(a for a,_ in pairs)
        b_counts = Counter(b for _,b in pairs)
        pe = 0.0
        for c in classes:
            pa_c = a_counts.get(c,0)/n
            pb_c = b_counts.get(c,0)/n
            pe += pa_c * pb_c
        k = 0.0 if (1.0 - pe) == 0 else (po - pe) / (1.0 - pe)
        # Gwet's AC1 using pooled category proportions
        # Ae_AC1 = [sum_c p_c * (1 - p_c)] / (Q - 1), where p_c is pooled proportion and Q is number of classes
        total_ratings = 2.0 * n
        pe1 = 0.0
        if total_ratings > 0:
            for c in classes:
                p_c = (a_counts.get(c,0) + b_counts.get(c,0)) / total_ratings
                pe1 += p_c * (1.0 - p_c)
        Q = max(1, len(classes))
        denom = max(1, Q - 1)
        pe1 = pe1 / denom
        ac1 = 0.0 if (1.0 - pe1) == 0 else (po - pe1) / (1.0 - pe1)
        # 95% CI normal approx
        import math
        se = math.sqrt(max(po*(1-po)/n, 0.0))
        low = max(0.0, po - 1.96*se)
        high = min(1.0, po + 1.96*se)
        return dict(n=n, pa=po, pa_low=low, pa_high=high, kappa=k, ac1=ac1)

    out: List[Dict[str, Any]] = []
    for hw_type in ['mcq','fill']:
        pairs: List[Tuple[str,str]] = []
        for r in rows:
            if r.get('type') != hw_type:
                continue
            a = str(r.get('judge_verdict','')).lower()
            b = str(r.get('judge2_verdict','')).lower()
            if a and b and a != 'error' and b != 'error':
                pairs.append((a,b))
        if not pairs:
            continue
        classes = ['correct','ambiguous','incorrect'] if hw_type == 'mcq' else ['acceptable','unacceptable']
        st = stats_for(pairs, classes)
        out.append({
            'run_id': rows[0]['run_id'],
            'type': hw_type,
            'n': st['n'],
            'percent_agreement': round(st['pa'],4),
            'pa_ci95_low': round(st['pa_low'],4),
            'pa_ci95_high': round(st['pa_high'],4),
            'kappa': round(st['kappa'],4),
            'ac1': round(st['ac1'],4),
        })
    return out


def main():
    ap = argparse.ArgumentParser(description='Backfill judge2 (DeepSeek native) into an existing run report without regenerating items or re-judging judge1.')
    ap.add_argument('--run-id', help='Run id folder name under benchmark/reports (e.g., race5_mcq_min_cot_i5_s0_twojudge)')
    ap.add_argument('--run-dir', help='Explicit path to reports dir (overrides --run-id)')
    ap.add_argument('--only-missing', action='store_true', help='Only process rows where judge2 is empty')
    ap.add_argument('--only-errors', action='store_true', help='Only process rows where judge2_verdict == "error"')
    ap.add_argument('--overwrite', action='store_true', help='Recompute judge2 even if already present')
    ap.add_argument('--limit', type=int, default=0, help='Max number of items to process (0 = no limit)')
    ap.add_argument('--sleep', type=float, default=0.0, help='Sleep seconds between API calls to avoid rate limits')
    ap.add_argument('--retries', type=int, default=2, help='Number of retries per item on 429/5xx')
    ap.add_argument('--model', default=os.getenv('JUDGE2_MODEL') or 'deepseek-chat', help='DeepSeek model id for judge2 (e.g., deepseek-chat)')
    ap.add_argument('--dotenv', default='.env', help='Path to .env to load')
    ap.add_argument('--dry-run', action='store_true', help='Do not call API; just report how many rows would be processed')
    ap.add_argument('--verbose', action='store_true', help='Print progress and reasons for skips/errors')
    ap.add_argument('--flush-every', type=int, default=0, help='If >0, periodically write per_item.csv every N processed rows for live updates')
    ap.add_argument('--start-row', type=int, default=0, help='0-based CSV row index to start from (applied after filters)')
    ap.add_argument('--end-row', type=int, default=-1, help='0-based CSV row index to stop at inclusive (-1 = no upper bound)')
    ap.add_argument('--context-jsonl', help='Optional path to labeled input JSONL to provide source_text context to judge2')
    ap.add_argument('--max-context-chars', type=int, default=int(os.getenv('JUDGE2_MAX_CONTEXT_CHARS') or 2000), help='Max characters of context to pass to judge2 (0 = no limit)')
    args = ap.parse_args()

    load_env(args.dotenv)

    if not args.run_dir and not args.run_id:
        ap.error('Provide --run-id or --run-dir')
    run_dir = Path(args.run_dir) if args.run_dir else Path('benchmark/reports') / args.run_id  # type: ignore[arg-type]
    per_item_csv = run_dir / 'per_item.csv'
    summary_csv = run_dir / 'summary.csv'
    inter_judge_csv = run_dir / 'inter_judge.csv'
    # Set judge2 call log path for low-level tracing
    os.environ['JUDGE2_CALL_LOG'] = str(run_dir / 'judge2_api_calls.log')
    if not per_item_csv.exists():
        raise FileNotFoundError(f'per_item.csv not found at {per_item_csv}')

    # Load rows (robust to whitespace/padded headers and empty lines)
    with per_item_csv.open('r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f, skipinitialspace=True)
        # Normalize header names by trimming whitespace
        if reader.fieldnames:
            reader.fieldnames = [(fn or '').strip() for fn in reader.fieldnames]
        rows: List[Dict[str, Any]] = []
        for r in reader:
            if r is None:
                continue
            # Trim keys and string values; skip completely empty rows
            norm: Dict[str, Any] = {}
            for k, v in r.items():
                kk = (k or '').strip()
                if isinstance(v, str):
                    vv = v.strip()
                else:
                    vv = v
                norm[kk] = vv
            if not any(str(v).strip() for v in norm.values()):
                continue
            rows.append(norm)

    # Optional context map for source_text recovery
    context_map: Dict[str, str] = {}
    if args.context_jsonl:
        try:
            context_map = _load_input_map(Path(args.context_jsonl))
            if args.verbose:
                print(f"[backfill] context loaded: {len(context_map)} entries from {args.context_jsonl}")
        except Exception as e:
            if args.verbose:
                print(f"[backfill] WARN: failed to load context JSONL: {e}")

    # Determine targets
    targets_idx: List[int] = []
    for i, r in enumerate(rows):
        has_j2 = bool(str(r.get('judge2_verdict','')).strip())
        is_error = str(r.get('judge2_verdict','')).strip().lower() == 'error'
        if args.overwrite:
            targets_idx.append(i)
        elif args.only_errors and is_error:
            targets_idx.append(i)
        elif args.only_missing and not has_j2:
            targets_idx.append(i)
    # Apply row range filters
    if args.start_row or args.end_row >= 0:
        lo = max(args.start_row, 0)
        hi = (args.end_row if args.end_row >= 0 else len(rows) - 1)
        targets_idx = [i for i in targets_idx if lo <= i <= hi]
    # Apply limit after range
    if args.limit and len(targets_idx) > args.limit:
        targets_idx = targets_idx[:args.limit]
    if args.verbose:
        print(f"[backfill] targets={len(targets_idx)} sample={targets_idx[:10]}")

    if args.dry_run:
        print(json.dumps({
            'status': 'dry-run',
            'run_dir': str(run_dir),
            'total_rows': len(rows),
            'to_process': len(targets_idx),
            'model': args.model,
        }, ensure_ascii=False))
        return

    # Hard preflight: ensure DeepSeek is usable before processing items that require judge2
    if len(targets_idx) > 0:
        key = os.getenv('DEEPSEEK_API_KEY')
        if not key:
            print(json.dumps({
                'status': 'error',
                'stage': 'preflight',
                'error': 'DEEPSEEK_API_KEY not set',
                'hint': 'Set DEEPSEEK_API_KEY in this shell or provide a .env and pass --dotenv',
            }, ensure_ascii=False))
            sys.exit(2)
        try:
            from openai import OpenAI  # type: ignore
            base = os.getenv('DEEPSEEK_BASE_URL') or 'https://api.deepseek.com'
            _ = OpenAI(base_url=base, api_key=key)
            if args.verbose:
                print(f"[backfill] preflight ok base={base}")
        except Exception as e:
            print(json.dumps({
                'status': 'error',
                'stage': 'preflight',
                'error': f'openai client init failed: {e}',
                'hint': 'Ensure openai package is installed and API key is valid',
            }, ensure_ascii=False))
            sys.exit(3)

    # Process
    # Diagnostics counters
    processed = 0
    c_pred_missing = 0
    c_lookup_fail = 0
    c_api_calls = 0
    c_api_success = 0
    c_api_errors = 0
    c_api_rate_retries = 0

    # Early sanity check for import and API key (optional)
    try:
        from benchmark import judge as _j_check  # noqa: F401
    except Exception as e:
        if args.verbose:
            print(f"[backfill] FATAL: cannot import benchmark.judge -> {e}")
        # Continue anyway; per-item loop will record the error per row
    if args.verbose and not os.getenv('DEEPSEEK_API_KEY'):
        print("[backfill] WARN: DEEPSEEK_API_KEY is not set; judge2 calls will fail.")
    for idx in targets_idx:
        r = rows[idx]
        # Safe accessors with trimming
        def _get(name: str) -> str:
            val = r.get(name, '')
            return str(val).strip()

        hw_type = _get('type')
        if not hw_type:
            r['judge2_verdict'] = 'error'
            r['judge2_score'] = ''
            r['judge2_why'] = 'missing required column: type'
            if args.verbose:
                print(f"[backfill] SKIP missing 'type' idx={idx}")
            processed += 1
            continue

        topic = _get('topic')
        if not topic:
            r['judge2_verdict'] = 'error'
            r['judge2_score'] = ''
            r['judge2_why'] = 'missing required column: topic'
            if args.verbose:
                print(f"[backfill] SKIP missing 'topic' idx={idx}")
            processed += 1
            continue

        config = _get('config')
        if not config:
            r['judge2_verdict'] = 'error'
            r['judge2_score'] = ''
            r['judge2_why'] = 'missing required column: config'
            if args.verbose:
                print(f"[backfill] SKIP missing 'config' idx={idx}")
            processed += 1
            continue

        seed_str = _get('seed')
        seed = int(seed_str) if seed_str.isdigit() else 0

        source_text_sha = _get('source_text_sha')
        if not source_text_sha:
            r['judge2_verdict'] = 'error'
            r['judge2_score'] = ''
            r['judge2_why'] = 'missing required column: source_text_sha'
            if args.verbose:
                print(f"[backfill] SKIP missing 'source_text_sha' idx={idx}")
            processed += 1
            continue

        qid_pred = _get('qid_pred')
        if not qid_pred:
            r['judge2_verdict'] = 'error'
            r['judge2_score'] = ''
            r['judge2_why'] = 'missing required column: qid_pred'
            if args.verbose:
                print(f"[backfill] SKIP missing 'qid_pred' idx={idx}")
            processed += 1
            continue
        pred_path = Path(f"benchmark/pred/{config}/{safe_topic_name(topic)}/{hw_type}/{source_text_sha}/seed{seed}.json")
        if not pred_path.exists():
            # Skip silently but keep note in why
            r['judge2_verdict'] = 'error'
            r['judge2_score'] = ''
            r['judge2_why'] = f'pred not found: {pred_path}'
            c_pred_missing += 1
            if args.verbose:
                print(f"[backfill] SKIP pred-missing idx={idx} path={pred_path}")
            processed += 1
            continue
        try:
            item = find_pred_item(pred_path, qid_pred)
        except Exception as e:
            r['judge2_verdict'] = 'error'
            r['judge2_score'] = ''
            r['judge2_why'] = f'pred lookup failed: {e}'
            c_lookup_fail += 1
            if args.verbose:
                print(f"[backfill] SKIP pred-lookup-failed idx={idx} why={e}")
            processed += 1
            continue

        # Call judge2 with retries on 429/5xx
        attempt = 0
        last_err = None
        success = False
        while attempt <= args.retries:
            try:
                if args.verbose:
                    print(f"[backfill] CALL judge2 idx={idx} hw_type={hw_type} topic={topic} attempt={attempt}")
                c_api_calls += 1
                context_text = None
                if context_map:
                    raw = context_map.get(source_text_sha)
                    if raw:
                        context_text = _truncate_context(raw, args.max_context_chars)
                out = judge2_call(hw_type, item, topic, model_override=args.model, context=context_text)
                verdict = str(out.get('verdict','')).lower()
                why = out.get('why','')
                score_map = vmap_for(hw_type)
                score = score_map.get(verdict, 0.0)
                r['judge2_verdict'] = verdict
                r['judge2_score'] = score
                r['judge2_why'] = why
                c_api_success += 1
                success = True
                break
            except Exception as e:
                last_err = str(e)
                # Heuristic: if 429 or rate limit, backoff and retry
                if any(code in str(e).lower() for code in ['429', 'rate limit', 'temporarily rate-limited']):
                    c_api_rate_retries += 1
                    if args.verbose:
                        print(f"[backfill] RETRY rate-limit idx={idx} attempt={attempt} err={e}")
                    time.sleep(max(args.sleep, 1.5) * (attempt + 1))
                    attempt += 1
                    continue
                else:
                    c_api_errors += 1
                    if args.verbose:
                        print(f"[backfill] ERROR non-retry idx={idx} err={e}")
                    break
        if not success:
            # mark error when attempts exhausted or non-retry error
            r['judge2_verdict'] = 'error'
            r['judge2_score'] = ''
            r['judge2_why'] = last_err or 'unknown error'

        processed += 1
        # Periodic flush for live updates
        if args.flush_every and (processed % args.flush_every == 0):
            try:
                from benchmark.report import write_per_item_csv as _flush_writer
                _flush_writer(per_item_csv, rows)
                if args.verbose:
                    print(f"[backfill] FLUSH per_item.csv after {processed} processed rows")
            except Exception as _e_flush:
                if args.verbose:
                    print(f"[backfill] FLUSH failed: {_e_flush}")
        if args.sleep:
            time.sleep(args.sleep)

    # Write back per_item.csv with updated judge2 columns
    try:
        from benchmark.report import write_per_item_csv
        write_per_item_csv(per_item_csv, rows)
    except Exception:
        # Fallback to plain csv writer if import path differs
        keys = [
            'run_id','config','topic','type','seed','source_text_sha','idx','qid_gold','qid_pred','structural_valid',
            'question_sim','ans_sim','distractor_diversity','ans_score','item_score',
            'judge_verdict','judge_score','judge_why',
            'judge2_verdict','judge2_score','judge2_why'
        ]
        with per_item_csv.open('w', encoding='utf-8', newline='') as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k, '') for k in keys})

    # Recompute and write summary.csv (including judge2_* aggregates) and inter-judge CSVs
    try:
        from benchmark.report import (
            write_summary_csv,
            write_inter_judge_csv,
            compute_inter_judge_by_topic,
            write_inter_judge_by_topic_csv,
        )
        summary_rows = compute_group_stats(rows)
        write_summary_csv(summary_csv, summary_rows)
        ij_rows = compute_inter_judge(rows)
        if ij_rows:
            write_inter_judge_csv(inter_judge_csv, ij_rows)
        # By-topic inter-judge
        ij_topic_rows = compute_inter_judge_by_topic(rows)
        inter_by_topic_csv = run_dir / 'inter_judge_by_topic.csv'
        if ij_topic_rows:
            write_inter_judge_by_topic_csv(inter_by_topic_csv, ij_topic_rows)
        else:
            # Create empty with header for consistency
            import csv as _csv
            with inter_by_topic_csv.open('w', encoding='utf-8', newline='') as f:
                w = _csv.DictWriter(f, fieldnames=['run_id','type','topic','n','percent_agreement','pa_ci95_low','pa_ci95_high','kappa','ac1'])
                w.writeheader()
    except Exception:
        pass

    print(json.dumps({
        'status': 'ok',
        'run_dir': str(run_dir),
        'processed': processed,
        'total_rows': len(rows),
        'model': args.model,
        'summary_updated': summary_csv.exists(),
        'inter_judge': inter_judge_csv.exists(),
        'diag': {
            'pred_missing': c_pred_missing,
            'pred_lookup_failed': c_lookup_fail,
            'api_calls': c_api_calls,
            'api_success': c_api_success,
            'api_errors': c_api_errors,
            'api_rate_retries': c_api_rate_retries,
        }
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()
