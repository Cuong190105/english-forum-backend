from __future__ import annotations
import os
import sys
import csv
import json
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

# Ensure repo root on sys.path
def _ensure_repo_root_on_path() -> None:
    try:
        here = Path(__file__).resolve()
        repo_root = here.parent.parent  # scripts/ -> project root
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
    except Exception:
        pass

_ensure_repo_root_on_path()

from benchmark.validate import validate_items
from benchmark.score import mcq_semantics
from benchmark.report import (
    write_summary_csv, write_per_item_csv, write_jsonl,
    write_paired_overall_csv, write_winloss_csv, write_winloss_consensus_csv,
    append_per_item_rows, write_inter_judge_csv,
    compute_inter_judge_by_topic, write_inter_judge_by_topic_csv,
)
from scripts.recompute_reports import compute_group_stats, compute_inter_judge
# Reuse batch generators and prompt builder from triple module (we'll use only gemini/claude)
from benchmark.judge_triple import (
    claude_batch_generate, _build_prompt_mcq, _norm_options,
)
from benchmark.judge import _parse_json_loose
from scripts.judge_batch_runner import call_gemini_batch_api


def _safe_topic(topic: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", topic or '')


def _verdict_to_score(hw_type: str, verdict: str) -> float:
    v = (verdict or '').strip().lower()
    if hw_type == 'mcq':
        return {'correct':1.0, 'ambiguous':0.5, 'incorrect':0.0}.get(v, 0.0)
    else:
        return {'acceptable':1.0, 'unacceptable':0.0}.get(v, 0.0)


@dataclass
class SourceRec:
    topic: str
    text: str
    sha: str


def _iter_input_records(path: Path, limit: int = 0) -> List[SourceRec]:
    records: List[SourceRec] = []
    if not path.exists():
        raise FileNotFoundError(path)
    # Accept JSONL or JSON array
    txt = path.read_text(encoding='utf-8')
    first_ch = txt.strip()[:1]
    if first_ch == '[':
        data = json.loads(txt)
        it = data
    else:
        it = []
        for line in txt.splitlines():
            line = line.strip()
            if not line:
                continue
            it.append(json.loads(line))
    for rec in it:
        topic = rec.get('topic') or rec.get('section') or ''
        text = rec.get('corrected_text') or rec.get('source_text') or rec.get('text') or ''
        if not topic or not text:
            continue
        sha = hashlib.sha256(text.encode('utf-8')).hexdigest()
        records.append(SourceRec(topic=topic, text=text, sha=sha))
        if limit and len(records) >= limit:
            break
    return records


def _collect_items_for_source(config: str, hw_type: str, topic: str, sha: str, seed: int) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[int]]:
    """Load pred/gold arrays; return (pred_items, gold_items, invalid_idx_pred)."""
    st = _safe_topic(topic)
    pred_path = Path(f"benchmark/pred/{config}/{st}/{hw_type}/{sha}/seed{seed}.json")
    gold_path = Path(f"benchmark/gold/{st}/{hw_type}/{sha}/seed0.json")
    pred = json.loads(pred_path.read_text(encoding='utf-8')) if pred_path.exists() else []
    gold = json.loads(gold_path.read_text(encoding='utf-8')) if gold_path.exists() else []
    # Structural validation on pred
    _, errs_pred, _ = validate_items(pred, hw_type, expected_count=None)
    invalid_idx_pred: List[int] = []
    for e in errs_pred:
        if isinstance(e, str) and e.startswith('i') and ':' in e:
            try:
                idx_str = e[1:e.index(':')]
                ii = int(idx_str)
                invalid_idx_pred.append(ii)
            except Exception:
                pass
    return pred, gold, invalid_idx_pred


def _batch_judge_mcq(items: List[Dict[str, Any]], *, topic: str, batch_size: int = 1000, concurrency: int = 3) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    """Return two aligned lists of dicts: gemini_out[i] = {'verdict','why'}, claude_out[i] likewise.
    Supports chunked batching with logging.
    """
    # Build prompts once
    prompts: List[str] = []
    for it in items:
        q = it.get('question', {})
        stem = q.get('prompt') or it.get('stem') or ''
        opts = _norm_options(q.get('options'))
        cid = it.get('correctOptionId') or ''
        prompts.append(_build_prompt_mcq(stem, opts, cid, topic))

    N = len(prompts)
    g_all: List[str] = [''] * N
    c_all: List[str] = [''] * N
    if batch_size <= 0:
        batch_size = N or 1
    print(f"[two-judges] Submitting {N} prompts in chunks of {batch_size} with concurrency={concurrency}")

    # Build chunk descriptors
    chunks: List[Tuple[int, int]] = []
    for start in range(0, N, batch_size):
        end = min(N, start + batch_size)
        chunks.append((start, end))

    def _run_chunk(start: int, end: int) -> Tuple[int, List[str], List[str]]:
        print(f"[two-judges] Chunk {start}-{end-1} / {N}")
        sub = prompts[start:end]
        # Use robust Gemini batch via judge_batch_runner to avoid SDK signature differences
        gem_txts, _ = call_gemini_batch_api(
            prompts=sub,
            model=(os.getenv('JUDGE_MODEL') or 'gemini-2.5-pro'),
            display_name=f"two_judges_{topic[:24]}_{start}_{end}",
            poll_interval_s=5.0,
            timeout_s=60*60,
        )
        cla_txts = claude_batch_generate(sub, model=os.getenv('CLAUDE_MODEL') or 'claude-haiku-4-5')
        return start, gem_txts, cla_txts

    # Limit concurrency to sensible bounds
    workers = max(1, int(concurrency or 1))
    if workers > len(chunks):
        workers = len(chunks)
    # If only one worker and one chunk, run inline to avoid thread-related SDK quirks
    if workers == 1 and len(chunks) == 1:
        try:
            start, gem_txts, cla_txts = _run_chunk(chunks[0][0], chunks[0][1])
            for i, t in enumerate(gem_txts):
                if (start + i) < N:
                    g_all[start+i] = t
            for i, t in enumerate(cla_txts):
                if (start + i) < N:
                    c_all[start+i] = t
        except Exception as e:
            print(f"[two-judges] Chunk failed: {e}")
    else:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = [ex.submit(_run_chunk, s, e) for (s, e) in chunks]
            for fut in as_completed(futs):
                try:
                    start, gem_txts, cla_txts = fut.result()
                except Exception as e:
                    print(f"[two-judges] Chunk failed: {e}")
                    continue
                # place back
                for i, t in enumerate(gem_txts):
                    if (start + i) < N:
                        g_all[start+i] = t
                for i, t in enumerate(cla_txts):
                    if (start + i) < N:
                        c_all[start+i] = t

    # Parse
    g_out: List[Dict[str,str]] = []
    c_out: List[Dict[str,str]] = []
    n_ok_g = n_err_g = n_ok_c = n_err_c = 0
    for i in range(N):
        try:
            g = _parse_json_loose(g_all[i] or '')
            n_ok_g += 1
        except Exception:
            g = {'verdict': 'error', 'why': (g_all[i] or '')[:200]}
            n_err_g += 1
        try:
            c = _parse_json_loose(c_all[i] or '')
            n_ok_c += 1
        except Exception:
            c = {'verdict': 'error', 'why': (c_all[i] or '')[:200]}
            n_err_c += 1
        g_out.append({'verdict': str(g.get('verdict','')).lower(), 'why': g.get('why','')})
        c_out.append({'verdict': str(c.get('verdict','')).lower(), 'why': c.get('why','')})
    print(f"[two-judges] Parsed gemini ok={n_ok_g} err={n_err_g}; claude ok={n_ok_c} err={n_err_c}")
    return g_out, c_out


def main():
    import argparse
    ap = argparse.ArgumentParser(description='Two-judge batch workflow using existing gold/pred. Reads sources JSON/JSONL to locate shas.')
    ap.add_argument('--input', required=True, help='Path to JSON/JSONL with fields: topic and source_text/corrected_text/text')
    ap.add_argument('--type', dest='hw_type', default='mcq', choices=['mcq'], help='Question type (only mcq supported)')
    ap.add_argument('--configs', default='minimal,cot', help='Comma-separated configs among: minimal,cot')
    ap.add_argument('--seeds', default='0', help='Comma-separated integer seeds, e.g. 0,1')
    ap.add_argument('--limit', type=int, default=0, help='Limit number of sources to process (0 = all)')
    ap.add_argument('--run-id', default=None, help='Run id folder name under benchmark/reports (default: timestamp)')
    ap.add_argument('--resume', action='store_true', help='Resume: skip existing rows found in per_item.csv (by config/topic/type/seed/sha/idx)')
    ap.add_argument('--batch-size', type=int, default=1000, help='Chunk size for batch APIs (default 1000)')
    ap.add_argument('--dry-run', action='store_true', help='Only print what would be processed, do not call APIs or write output')
    ap.add_argument('--concurrency', type=int, default=3, help='Number of chunks (batches) to submit in parallel (default 3)')
    args = ap.parse_args()

    from datetime import datetime
    run_id = args.run_id or datetime.now().strftime('%Y%m%d_%H%M%S')
    run_dir = Path(f"benchmark/reports/{run_id}")
    run_dir.mkdir(parents=True, exist_ok=True)

    # Parse inputs
    sources = _iter_input_records(Path(args.input), limit=int(args.limit or 0))
    if not sources:
        raise SystemExit('No valid records found (need topic + source_text/corrected_text/text)')
    configs = [x.strip() for x in str(args.configs).split(',') if x.strip()]
    seeds = [int(s) for s in [x.strip() for x in str(args.seeds).split(',') if x.strip()]]

    per_item_rows: List[Dict[str, Any]] = []

    # Resume support: load existing per_item index map
    per_item_csv = run_dir / 'per_item.csv'
    existing_idx: Dict[Tuple[str,str,str,int,str], set] = {}
    if args.resume and per_item_csv.exists():
        try:
            with per_item_csv.open('r', encoding='utf-8', newline='') as f:
                reader = csv.DictReader(f, skipinitialspace=True)
                for r in reader:
                    cfg = (r.get('config','') or '').strip()
                    topic = (r.get('topic','') or '').strip()
                    hw_type = (r.get('type','') or '').strip()
                    seed = int(r.get('seed', 0)) if str(r.get('seed','')).isdigit() else 0
                    sha = (r.get('source_text_sha','') or '').strip()
                    idx = int(r.get('idx', 0)) if str(r.get('idx','')).isdigit() else 0
                    key = (cfg, topic, hw_type, seed, sha)
                    existing_idx.setdefault(key, set()).add(idx)
            print(f"[resume] Loaded existing per_item rows: {sum(len(v) for v in existing_idx.values())} indices across {len(existing_idx)} groups")
        except Exception as e:
            print(f"[resume] Failed reading existing per_item.csv: {e}")

    row_idx = 0
    for src in sources:
        st = _safe_topic(src.topic)
        for cfg in configs:
            for seed in seeds:
                pred, gold, invalid_idx_pred = _collect_items_for_source(cfg, args.hw_type, src.topic, src.sha, seed)
                if not pred or not gold:
                    print(f"[skip] Missing pred/gold for topic={src.topic} cfg={cfg} seed={seed} sha={src.sha}")
                    continue
                # Determine which indices to process (resume)
                key = (cfg, src.topic, args.hw_type, seed, src.sha)
                already = existing_idx.get(key, set())
                idx_list = [i for i in range(1, len(pred)+1) if i not in already]
                print(f"[plan] topic={src.topic} cfg={cfg} seed={seed} total={len(pred)} already={len(already)} to_do={len(idx_list)}")
                if args.dry_run:
                    continue
                if not idx_list:
                    continue
                # Build subset for judging
                pred_sub = [pred[i-1] for i in idx_list]
                try:
                    g_batch, c_batch = _batch_judge_mcq(pred_sub, topic=src.topic, batch_size=int(args.batch_size), concurrency=int(args.concurrency))
                except Exception as e:
                    print(f"[warn] Batch judging failed for topic={src.topic} cfg={cfg} seed={seed}: {e}")
                    g_batch = [{'verdict':'', 'why': ''} for _ in pred_sub]
                    c_batch = [{'verdict':'', 'why': ''} for _ in pred_sub]

                for k, i in enumerate(idx_list, start=0):
                    pi = pred[i-1]
                    gi = gold[i-1] if i-1 < len(gold) else {}
                    # Structural
                    structural_valid = 0 if (i in invalid_idx_pred) else 1
                    # Semantics
                    try:
                        ps, ans, div, item = mcq_semantics(pi, gi)
                        question_sim = round(ps, 4)
                        ans_sim = ('' if ans is None else round(ans, 4))
                        distractor_diversity = round(div, 4)
                        ans_score = ('' if ans is None else round(ans, 4))
                        item_score = round(item, 4)
                    except Exception:
                        question_sim = ''
                        ans_sim = ''
                        distractor_diversity = ''
                        ans_score = ''
                        item_score = ''
                    g = g_batch[k] if k < len(g_batch) else {'verdict':'', 'why': ''}
                    c = c_batch[k] if k < len(c_batch) else {'verdict':'', 'why': ''}
                    j1_verdict = g.get('verdict','')
                    j2_verdict = c.get('verdict','')
                    j1_score = ('' if not j1_verdict else _verdict_to_score(args.hw_type, j1_verdict))
                    j2_score = ('' if not j2_verdict else _verdict_to_score(args.hw_type, j2_verdict))
                    row_idx += 1
                    per_item_rows.append({
                        'run_id': run_id,
                        'config': cfg,
                        'topic': src.topic,
                        'type': args.hw_type,
                        'seed': seed,
                        'source_text_sha': src.sha,
                        'idx': i,
                        'qid_gold': gold[i-1]['question'].get('id','') if i-1 < len(gold) else '',
                        'qid_pred': pred[i-1]['question'].get('id','') if i-1 < len(pred) else '',
                        'structural_valid': structural_valid,
                        'question_sim': question_sim,
                        'ans_sim': ans_sim,
                        'distractor_diversity': distractor_diversity,
                        'ans_score': ans_score,
                        'item_score': item_score,
                        'judge_verdict': j1_verdict,
                        'judge_score': j1_score,
                        'judge_why': g.get('why',''),
                        'judge2_verdict': j2_verdict,
                        'judge2_score': j2_score,
                        'judge2_why': c.get('why',''),
                        'row_idx': row_idx,
                        # 3-judge extension fields left blank for compatibility
                        'judge_gemini_verdict': j1_verdict,
                        'judge_gemini_why': g.get('why',''),
                        'judge_claude_verdict': j2_verdict,
                        'judge_claude_why': c.get('why',''),
                        'judge_deepseek_verdict': '',
                        'judge_deepseek_why': '',
                    })

    # Write per_item immediately (append in resume mode if file exists)
    if args.dry_run:
        print("[dry-run] Skipping writes")
        return
    if args.resume and per_item_csv.exists():
        append_per_item_rows(per_item_csv, per_item_rows)
    else:
        write_per_item_csv(per_item_csv, per_item_rows)

    # Load full per_item to compute summary and inter-judge reliably
    full_rows: List[Dict[str, Any]] = []
    try:
        with per_item_csv.open('r', encoding='utf-8', newline='') as f:
            reader = csv.DictReader(f, skipinitialspace=True)
            if reader.fieldnames:
                reader.fieldnames = [(fn or '').strip() for fn in reader.fieldnames]
            for r in reader:
                if r is None:
                    continue
                full_rows.append({(k or '').strip(): (v.strip() if isinstance(v, str) else v) for k,v in r.items()})
    except Exception as e:
        print(f"[warn] Failed to reload per_item for summary: {e}")

    summary_rows = compute_group_stats(full_rows or per_item_rows)
    write_summary_csv(run_dir / 'summary.csv', summary_rows)

    # Build paired deltas and win/loss (minimal vs cot) using full rows
    groups: Dict[Tuple[str,str,str,int], Dict[str, Dict[str, float]]] = {}
    for r in (full_rows or per_item_rows):
        sha = str(r.get('source_text_sha','')).strip()
        topic = str(r.get('topic','')).strip()
        t = str(r.get('type','')).strip()
        seed = int(r.get('seed', 0)) if str(r.get('seed','')).isdigit() else 0
        cfg = str(r.get('config','')).strip()
        if not (sha and topic and t and cfg):
            continue
        key = (sha, topic, t, seed)
        groups.setdefault(key, {})
        if cfg not in groups[key]:
            groups[key][cfg] = {'semantic_sum':0.0, 'semantic_n':0, 'judge_sum':0.0, 'judge_n':0}
        try:
            if str(r.get('item_score','')).strip() != '':
                groups[key][cfg]['semantic_sum'] += float(r['item_score'])
                groups[key][cfg]['semantic_n'] += 1
        except Exception:
            pass
        try:
            if str(r.get('judge_score','')).strip() != '':
                groups[key][cfg]['judge_sum'] += float(r['judge_score'])
                groups[key][cfg]['judge_n'] += 1
        except Exception:
            pass

    from statistics import mean, stdev
    from math import sqrt
    deltas_sem: List[float] = []
    deltas_j: List[float] = []
    s_w = s_l = s_t = 0
    j_w = j_l = j_t = 0
    for _, cfgmap in groups.items():
        if 'minimal' in cfgmap and 'cot' in cfgmap:
            def avg(d: Dict[str,float], s: str, n: str) -> float:
                return (d.get(s,0.0) / d.get(n,1)) if d.get(n,0) > 0 else 0.0
            min_sem = avg(cfgmap['minimal'], 'semantic_sum', 'semantic_n')
            cot_sem = avg(cfgmap['cot'], 'semantic_sum', 'semantic_n')
            min_j = avg(cfgmap['minimal'], 'judge_sum', 'judge_n')
            cot_j = avg(cfgmap['cot'], 'judge_sum', 'judge_n')
            d_sem = cot_sem - min_sem
            d_j = cot_j - min_j
            deltas_sem.append(d_sem)
            deltas_j.append(d_j)
            eps = 1e-12
            if d_sem > eps:
                s_w += 1
            elif d_sem < -eps:
                s_l += 1
            else:
                s_t += 1
            if d_j > eps:
                j_w += 1
            elif d_j < -eps:
                j_l += 1
            else:
                # tie -> break by semantic
                if d_sem > 1e-6:
                    j_w += 1
                elif d_sem < -1e-6:
                    j_l += 1
                else:
                    j_t += 1

    def ci_stats(arr: List[float]) -> Dict[str, float]:
        if not arr:
            return dict(mean=0.0, std=0.0, se=0.0, low=0.0, high=0.0)
        m = mean(arr)
        sd = stdev(arr) if len(arr) > 1 else 0.0
        se = (sd / sqrt(len(arr))) if len(arr) > 1 else 0.0
        low = max(-1.0, m - 1.96 * se)
        high = min(1.0, m + 1.96 * se)
        return dict(mean=m, std=sd, se=se, low=low, high=high)

    s_stats = ci_stats(deltas_sem)
    j_stats = ci_stats(deltas_j)
    s_H = max(0.0, (s_stats['high'] - s_stats['low'])/2.0)
    j_H = max(0.0, (j_stats['high'] - j_stats['low'])/2.0)
    paired_rows = [
        {
            'run_id': run_id,
            'metric': 'semantic',
            'n_pairs': len(deltas_sem),
            'delta_mean': round(s_stats['mean'], 4),
            'delta_std': round(s_stats['std'], 4),
            'delta_se': round(s_stats['se'], 4),
            'delta_ci95_low': round(s_stats['low'], 4),
            'delta_ci95_high': round(s_stats['high'], 4),
            'delta_ci95_halfwidth_H': round(s_H, 4),
            'delta_ci_level': 0.95,
            'delta_H_target': 0.04,
            'delta_meets_H_target': 1 if s_H <= 0.04 else 0,
            'delta_significant': 1 if (s_stats['low'] > 0.0 or s_stats['high'] < 0.0) else 0,
        },
        {
            'run_id': run_id,
            'metric': 'judge',
            'n_pairs': len(deltas_j),
            'delta_mean': round(j_stats['mean'], 4),
            'delta_std': round(j_stats['std'], 4),
            'delta_se': round(j_stats['se'], 4),
            'delta_ci95_low': round(j_stats['low'], 4),
            'delta_ci95_high': round(j_stats['high'], 4),
            'delta_ci95_halfwidth_H': round(j_H, 4),
            'delta_ci_level': 0.95,
            'delta_H_target': 0.05,
            'delta_meets_H_target': 1 if j_H <= 0.05 else 0,
            'delta_significant': 1 if (j_stats['low'] > 0.0 or j_stats['high'] < 0.0) else 0,
        },
    ]
    write_paired_overall_csv(run_dir / 'paired_overall.csv', paired_rows)

    # Win/loss summary
    def _binom_p_two_sided(wins: int, losses: int) -> float:
        import math
        n = wins + losses
        if n == 0:
            return 1.0
        k = wins
        def pmf(i: int) -> float:
            return math.comb(n, i) * (0.5 ** n)
        def cdf(i: int) -> float:
            return sum(pmf(j) for j in range(0, i+1))
        c_low = cdf(k)
        c_high = 1.0 - cdf(k-1) if k > 0 else 1.0
        p = 2.0 * min(c_low, c_high)
        return min(max(p, 0.0), 1.0)

    s_n_eff = s_w + s_l
    j_n_eff = j_w + j_l
    s_rate = (s_w / s_n_eff) if s_n_eff > 0 else 0.0
    j_rate = (j_w / j_n_eff) if j_n_eff > 0 else 0.0
    s_p = _binom_p_two_sided(s_w, s_l)
    j_p = _binom_p_two_sided(j_w, j_l)
    winloss_rows = [{
        'run_id': run_id,
        'semantic_wins': s_w,
        'semantic_losses': s_l,
        'semantic_ties': s_t,
        'semantic_n_effective': s_n_eff,
        'semantic_win_rate': round(s_rate, 4),
        'semantic_binomial_p': round(s_p, 6),
        'judge_wins': j_w,
        'judge_losses': j_l,
        'judge_ties': j_t,
        'judge_n_effective': j_n_eff,
        'judge_win_rate': round(j_rate, 4),
        'judge_binomial_p': round(j_p, 6),
    }]
    write_winloss_csv(run_dir / 'winloss.csv', winloss_rows)

    # Consensus-only win/loss (primary): Both judges must agree on which config wins for a pair
    def _wilson_ci(p_hat: float, n: int, z: float = 1.96) -> Tuple[float, float]:
        if n <= 0:
            return (0.0, 0.0)
        denom = 1.0 + (z*z)/n
        center = (p_hat + (z*z)/(2.0*n)) / denom
        from math import sqrt
        half = z * sqrt(max(p_hat*(1.0 - p_hat)/n + (z*z)/(4.0*n*n), 0.0)) / denom
        low = max(0.0, center - half)
        high = min(1.0, center + half)
        return (low, high)

    # Decide per-group (sha, topic, type, seed) outcome for each judge separately using average judge scores per config
    # Then apply fusion rule: count only when both judges pick the same winner; ties/errors -> abstain
    n_pairs = 0
    cot_w = 0
    min_w = 0
    tie_or_abstain = 0

    for key, cfgmap in groups.items():  # key = (sha, topic, t, seed)
        if 'minimal' not in cfgmap or 'cot' not in cfgmap:
            continue
        n_pairs += 1
        # Judge1 means
        def avg(d: Dict[str,float], s: str, n: str) -> float:
            return (d.get(s,0.0) / d.get(n,1)) if d.get(n,0) > 0 else 0.0
        j1_min = avg(cfgmap['minimal'], 'judge_sum', 'judge_n')
        j1_cot = avg(cfgmap['cot'], 'judge_sum', 'judge_n')

        # For Judge2, recompute sums per config from full_rows using judge2_score
        j2_min_sum = 0.0; j2_min_n = 0
        j2_cot_sum = 0.0; j2_cot_n = 0
        sha, topic, t, seed = key
        for r in (full_rows or per_item_rows):
            if str(r.get('source_text_sha','')).strip() != sha: continue
            if str(r.get('topic','')).strip() != topic: continue
            if str(r.get('type','')).strip() != t: continue
            seed_r = int(r.get('seed', 0)) if str(r.get('seed','')).isdigit() else 0
            if seed_r != seed: continue
            cfg = str(r.get('config','')).strip()
            v = r.get('judge2_score','')
            if str(v).strip() == '':
                continue
            try:
                fv = float(v)
            except Exception:
                continue
            if cfg == 'minimal':
                j2_min_sum += fv; j2_min_n += 1
            elif cfg == 'cot':
                j2_cot_sum += fv; j2_cot_n += 1

        j2_min = (j2_min_sum / j2_min_n) if j2_min_n > 0 else None
        j2_cot = (j2_cot_sum / j2_cot_n) if j2_cot_n > 0 else None

        # Determine each judge's pair verdict
        def decide_pair(a: Optional[float], b: Optional[float]) -> str:
            eps = 1e-12
            if a is None or b is None:
                return 'abstain'
            d = b - a  # b = cot, a = minimal
            if d > eps:
                return 'cot_win'
            elif d < -eps:
                return 'min_win'
            else:
                return 'tie'

        j1_pair = decide_pair(j1_min, j1_cot)
        j2_pair = decide_pair(j2_min, j2_cot)

        if j1_pair == 'cot_win' and j2_pair == 'cot_win':
            cot_w += 1
        elif j1_pair == 'min_win' and j2_pair == 'min_win':
            min_w += 1
        else:
            tie_or_abstain += 1

    n_eff = cot_w + min_w
    drop_rate = ( (n_pairs - n_eff) / n_pairs ) if n_pairs > 0 else 0.0
    win_rate = (cot_w / n_eff) if n_eff > 0 else 0.0
    win_low, win_high = _wilson_ci(win_rate, n_eff)
    p_val = _binom_p_two_sided(cot_w, min_w)

    winloss_consensus_rows = [{
        'run_id': run_id,
        'n_pairs': n_pairs,
        'n_effective': n_eff,
        'drop_rate': round(drop_rate, 4),
        'cot_wins': cot_w,
        'minimal_wins': min_w,
        'ties_abstain': tie_or_abstain,
        'win_rate': round(win_rate, 4),
        'win_ci95_low': round(win_low, 4),
        'win_ci95_high': round(win_high, 4),
        'binomial_p': round(p_val, 6),
    }]
    write_winloss_consensus_csv(run_dir / 'winloss_consensus.csv', winloss_consensus_rows)

    # Inter-judge overall and by topic (two-judge metrics)
    try:
        ij_rows = compute_inter_judge(full_rows or per_item_rows)
        write_inter_judge_csv(run_dir / 'inter_judge.csv', ij_rows)
    except Exception as e:
        print(f"[warn] inter_judge overall failed: {e}")
    try:
        ij_topic = compute_inter_judge_by_topic(full_rows or per_item_rows)
        write_inter_judge_by_topic_csv(run_dir / 'inter_judge_by_topic.csv', ij_topic)
    except Exception as e:
        print(f"[warn] inter_judge_by_topic failed: {e}")

    # Also write a tiny invalid rows file for parity (only when idx invalid structurally)
    invalid_rows: List[Dict[str, Any]] = []
    for r in per_item_rows:
        if str(r.get('structural_valid','')) == '0':
            invalid_rows.append({k: r.get(k,'') for k in ['run_id','config','topic','type','seed','source_text_sha','idx']})
    write_jsonl(run_dir / 'invalid_items.jsonl', invalid_rows)

    print(json.dumps({'status':'ok','run_dir': str(run_dir), 'n_rows': len(per_item_rows)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
