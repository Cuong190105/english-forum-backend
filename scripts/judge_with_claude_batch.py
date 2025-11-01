from __future__ import annotations
import os
import sys
import json
import csv
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
import re

try:
    import anthropic
except ImportError:
    raise ImportError("anthropic package not installed. Install with: pip install anthropic")

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# Judge system prompts from benchmark/judge.py
MCQ_SYS = (
    'Trả JSON: { "verdict": "correct|ambiguous|incorrect", "why": "<vi-vn>" }\n'
    'Vai trò: Giám khảo EFL (nghiêm ngặt vừa phải). Chỉ sử dụng stem và options; KHÔNG dùng kiến thức ngoài.\n'
    'Quy trình ra quyết định (ưu tiên tính chặt chẽ cho AMBIGUOUS):\n'
    '1) Trích xuất ràng buộc từ stem (ngữ pháp, nghĩa, dấu hiệu loại trừ).\n'
    '2) Đánh giá từng option theo ràng buộc: phân loại "phù hợp rõ ràng" vs "có thể chấp nhận" vs "loại".\n'
    '3) Nếu đúng 1 option "phù hợp rõ ràng" và các option khác bị "loại" → verdict=correct.\n'
    '4) Nếu 0 option "phù hợp rõ ràng" HOẶC có ≥2 option ở mức "có thể chấp nhận" nhưng thiếu bằng chứng để loại trừ → verdict=ambiguous.\n'
    '5) Nếu đáp án gán-đúng bị bác bỏ theo stem hoặc có option khác đúng/ tốt ngang làm mất tính duy nhất → verdict=incorrect.\n'
    'Khi nào nên AMBIGUOUS (các tình huống thường gặp):\n'
    '- Stem thiếu thông tin quyết định (phải dựa kiến thức ngoài).\n'
    '- Nhiều option đồng nghĩa/paraphrase thỏa ràng buộc như nhau, không có tín hiệu tách bạch.\n'
    '- Tham chiếu/khung thời gian/tiêu điểm ngữ nghĩa không đủ rõ trong stem.\n'
    '- Lỗi hình thức MCQ (trùng/thiếu option, mô tả chồng lấn) khiến không thể loại trừ.\n'
    'Xuất kết quả:\n'
    '- Chỉ {verdict, why}. why 1–2 câu, nêu ràng buộc trong stem và option liên quan (nhắc ID option nếu cần).\n'
    '- Không đoán: nếu chưa thể loại trừ hoàn toàn → chọn ambiguous và giải thích vì sao.'
)

FILL_SYS = (
    'Trả JSON: { "verdict": "acceptable|unacceptable", "why": "<vi-vn>" }\n'
    'Vai trò: Giám khảo EFL (nghiêm ngặt vừa phải). Chỉ sử dụng stem và answer; KHÔNG dùng kiến thức ngoài.\n'
    'Tiêu chí:\n'
    '- acceptable: Đáp án khớp ngữ pháp và ý nghĩa mục tiêu theo stem (chấp nhận biến thể nhỏ như viết hoa/chấm câu; ghi rõ nếu chấp nhận).\n'
    '- unacceptable: Sai ngữ pháp/ý hoặc không đáp ứng ràng buộc cần thiết (thì, hòa hợp chủ-vị, cấu trúc).\n'
    'Đầu ra: Chỉ {verdict, why}; why ngắn gọn 1–2 câu, bám sát stem/answer.'
)


def _parse_json_loose(text: str) -> Dict[str, Any]:
    """Try to parse a JSON object from a possibly noisy LLM output."""
    try:
        return json.loads(text)
    except Exception:
        pass
    # Find the first '{' and last '}' and attempt
    if '{' in text and '}' in text:
        start = text.find('{')
        end = text.rfind('}')
        if end > start:
            candidate = text[start:end+1]
            try:
                return json.loads(candidate)
            except Exception:
                # Try to remove code fences/backticks
                candidate = re.sub(r"^```[a-zA-Z]*", "", candidate).strip('`\n ')
                try:
                    return json.loads(candidate)
                except Exception:
                    pass
    # As a last resort, map common label words to a verdict
    low = text.lower()
    if any(w in low for w in ['correct']):
        return {"verdict": "correct", "why": text}
    if any(w in low for w in ['ambiguous','unclear','both could']):
        return {"verdict": "ambiguous", "why": text}
    if any(w in low for w in ['incorrect','wrong','not correct']):
        return {"verdict": "incorrect", "why": text}
    if any(w in low for w in ['acceptable']):
        return {"verdict": "acceptable", "why": text}
    if any(w in low for w in ['unacceptable']):
        return {"verdict": "unacceptable", "why": text}
    # Fallback: raise so caller may retry
    raise ValueError("Could not parse JSON from model output")


def _get_client() -> anthropic.Anthropic:
    """Get or create Anthropic client."""
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        raise RuntimeError('ANTHROPIC_API_KEY not set')
    return anthropic.Anthropic(api_key=api_key)


def create_claude_batch(requests: List[Dict[str, Any]]) -> str:
    """Create a Claude message batch and return the batch ID using REST API."""
    # Batch API is only available via REST endpoint (not in SDK yet)
    import httpx
    
    api_key = os.getenv('ANTHROPIC_API_KEY')
    url = "https://api.anthropic.com/v1/messages/batches"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }
    
    payload = {"requests": requests}
    
    with httpx.Client(timeout=60.0) as http_client:
        resp = http_client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data['id']


def retrieve_batch_status(batch_id: str) -> Dict[str, Any]:
    """Retrieve the status of a Claude message batch using REST API."""
    import httpx
    
    api_key = os.getenv('ANTHROPIC_API_KEY')
    url = f"https://api.anthropic.com/v1/messages/batches/{batch_id}"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01"
    }
    
    with httpx.Client(timeout=60.0) as client:
        resp = client.get(url, headers=headers)
        resp.raise_for_status()
        return resp.json()


def retrieve_batch_results(batch_id: str) -> List[Dict[str, Any]]:
    """Retrieve the results of a completed Claude message batch using REST API."""
    import httpx
    
    api_key = os.getenv('ANTHROPIC_API_KEY')
    status = retrieve_batch_status(batch_id)
    results_url = status.get('results_url')
    if not results_url:
        raise RuntimeError(f"Batch {batch_id} not completed yet. Status: {status.get('processing_status')}")
    
    # Download the .jsonl file
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01"
    }
    
    with httpx.Client(timeout=120.0) as client:
        resp = client.get(results_url, headers=headers)
        resp.raise_for_status()
        
        # Parse JSONL
        results = []
        for line in resp.text.strip().split('\n'):
            if line.strip():
                results.append(json.loads(line))
        return results


def load_per_item_data(run_id: str) -> List[Dict[str, Any]]:
    """Load per_item.csv and return rows with pred data loaded."""
    run_dir = Path(f"benchmark/reports/{run_id}")
    per_item_csv = run_dir / 'per_item.csv'
    
    if not per_item_csv.exists():
        raise FileNotFoundError(f"per_item.csv not found: {per_item_csv}")
    
    rows = []
    with per_item_csv.open('r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)
    
    # Load pred JSON files
    pred_base = Path("benchmark/pred")
    for row in rows:
        config = row.get('config', '').strip()
        topic = row.get('topic', '').strip()
        hw_type = row.get('type', '').strip()
        seed = row.get('seed', '').strip()
        source_text_sha = row.get('source_text_sha', '').strip()
        idx = int(row.get('idx', '0') or '0')
        
        if not all([config, topic, hw_type, seed, source_text_sha]):
            continue
        
        # Sanitize topic for filesystem
        safe_topic = re.sub(r"[^A-Za-z0-9._-]+", "_", topic)
        pred_path = pred_base / config / safe_topic / hw_type / source_text_sha / f"seed{seed}.json"
        
        if pred_path.exists():
            pred_data = json.loads(pred_path.read_text(encoding='utf-8'))
            row['pred_item'] = pred_data[idx - 1] if idx > 0 and idx <= len(pred_data) else None
        else:
            row['pred_item'] = None
    
    return rows


def build_mcq_request(
    stem: str,
    options: Dict[str, str],
    correct_id: str,
    topic: str,
    context: Optional[str] = None,
    custom_id: str = ""
) -> Dict[str, Any]:
    """Build a Claude batch request for MCQ judging."""
    user_content = json.dumps({
        'stem': stem,
        'options': options,
        'correctOptionId': correct_id,
        'topic': topic,
        **({'context': context} if context else {}),
    }, ensure_ascii=False)
    
    messages = [
        {"role": "user", "content": f"{MCQ_SYS}\n{user_content}"}
    ]
    
    return {
        "custom_id": custom_id,
        "params": {
            "model": "claude-haiku-4-5",
            "max_tokens": 1024,
            "temperature": 0.0,
            "response_format": {
                "type": "json_object"
            },
            "messages": messages
        }
    }


def build_fill_request(
    prompt: str,
    answer: str,
    topic: str,
    context: Optional[str] = None,
    custom_id: str = ""
) -> Dict[str, Any]:
    """Build a Claude batch request for Fill judging."""
    user_content = json.dumps({
        'prompt': prompt,
        'answer': answer,
        'topic': topic,
        **({'context': context} if context else {}),
    }, ensure_ascii=False)
    
    messages = [
        {"role": "user", "content": f"{FILL_SYS}\n{user_content}"}
    ]
    
    return {
        "custom_id": custom_id,
        "params": {
            "model": "claude-haiku-4-5",
            "max_tokens": 1024,
            "temperature": 0.0,
            "response_format": {
                "type": "json_object"
            },
            "messages": messages
        }
    }


def judge_with_claude_batch(run_id: str, max_requests_per_batch: int = 10000):
    """Judge all items from run_id using Claude batch API."""
    print(f"Loading data from run {run_id}...")
    rows = load_per_item_data(run_id)
    print(f"Loaded {len(rows)} rows")
    
    # Build batch requests
    requests = []
    row_map = {}  # custom_id -> row index
    
    use_context = os.getenv('JUDGE_USE_CONTEXT', '0').lower() in {'1', 'true', 'yes', 'y'}
    
    for i, row in enumerate(rows):
        pred_item = row.get('pred_item')
        if not pred_item:
            print(f"Warning: Row {i} has no pred_item, skipping")
            continue
        
        hw_type = row.get('type', '').strip()
        topic = row.get('topic', '').strip()
        source_text_sha = row.get('source_text_sha', '').strip()
        idx = row.get('idx', '').strip()
        
        custom_id = f"{run_id}_{i}"
        row_map[custom_id] = i
        
        if use_context:
            # Load source text if needed
            # For now, skip context
            context = None
        else:
            context = None
        
        if hw_type == 'mcq':
            stem = pred_item.get('question', {}).get('prompt', '')
            options = {o['id']: o['label'] for o in pred_item.get('question', {}).get('options', [])}
            correct_id = pred_item.get('correctOptionId', '')
            
            if stem and options and correct_id:
                req = build_mcq_request(stem, options, correct_id, topic, context, custom_id)
                requests.append(req)
        elif hw_type == 'fill':
            prompt = pred_item.get('question', {}).get('prompt', '')
            answer = pred_item.get('answer', '')
            
            if prompt and answer:
                req = build_fill_request(prompt, answer, topic, context, custom_id)
                requests.append(req)
    
    print(f"Built {len(requests)} batch requests")
    
    if not requests:
        print("No requests to process")
        return
    
    # Split into batches if needed
    batches = []
    for i in range(0, len(requests), max_requests_per_batch):
        batch_requests = requests[i:i+max_requests_per_batch]
        batches.append(batch_requests)
    
    print(f"Split into {len(batches)} batch(es)")
    
    # Create batches and wait for completion
    all_results = []
    for batch_idx, batch_requests in enumerate(batches):
        print(f"\nProcessing batch {batch_idx + 1}/{len(batches)} ({len(batch_requests)} requests)...")
        
        print("Creating batch...")
        batch_id = create_claude_batch(batch_requests)
        print(f"Created batch: {batch_id}")
        
        # Poll for completion
        print("Waiting for batch completion...")
        max_wait = 24 * 60 * 60  # 24 hours
        start_time = time.time()
        poll_interval = 30  # 30 seconds
        
        while True:
            status = retrieve_batch_status(batch_id)
            proc_status = status.get('processing_status')
            request_counts = status.get('request_counts', {})
            
            elapsed = time.time() - start_time
            print(f"  Status: {proc_status}, "
                  f"Succeeded: {request_counts.get('succeeded', 0)}, "
                  f"Processing: {request_counts.get('processing', 0)}, "
                  f"Errored: {request_counts.get('errored', 0)}, "
                  f"Elapsed: {elapsed:.1f}s")
            
            if proc_status == 'ended':
                break
            
            if elapsed > max_wait:
                raise TimeoutError(f"Batch {batch_id} timed out after {max_wait}s")
            
            time.sleep(poll_interval)
        
        # Retrieve results
        print("Retrieving results...")
        batch_results = retrieve_batch_results(batch_id)
        print(f"Retrieved {len(batch_results)} results")
        all_results.extend(batch_results)
    
    # Parse results and update rows
    print(f"\nParsing {len(all_results)} results...")
    
    results_map = {}
    missing_custom_ids = []
    for result_item in all_results:
        custom_id = result_item.get('custom_id', '')
        if not custom_id:
            missing_custom_ids.append(str(result_item)[:200])
            continue
        
        # Structure: {"custom_id": "...", "result": {"type": "succeeded", "message": {...}}}
        result = result_item.get('result', {})
        
        if not result:
            results_map[custom_id] = {
                'verdict': 'error',
                'why': 'No result field in response'
            }
            continue
        
        # Check if this is an error response
        result_type = result.get('type', '')
        if result_type == 'errored' or result_type == 'error':
            error = result.get('error', {})
            results_map[custom_id] = {
                'verdict': 'error',
                'why': json.dumps(error)
            }
            continue
        
        if result_type != 'succeeded':
            results_map[custom_id] = {
                'verdict': 'error',
                'why': f"Result type not succeeded: {result_type}"
            }
            continue
        
        # Get message from result.result.message
        message = result.get('message', {})
        if not message:
            results_map[custom_id] = {
                'verdict': 'error',
                'why': 'No message field in result'
            }
            continue
        
        # Get content from message.content[0].text
        content_list = message.get('content', [])
        if not content_list or len(content_list) == 0:
            results_map[custom_id] = {
                'verdict': 'error',
                'why': 'No content in message'
            }
            continue
        
        # Get text from first content block
        first_content = content_list[0]
        if isinstance(first_content, dict):
            text = first_content.get('text', '')
        elif isinstance(first_content, str):
            text = first_content
        else:
            text = str(first_content)
        
        if not text:
            results_map[custom_id] = {
                'verdict': 'error',
                'why': 'No text found in content'
            }
            continue
        
        # Parse JSON from text (may have code fences)
        try:
            parsed = _parse_json_loose(text)
            results_map[custom_id] = parsed
        except Exception as e:
            results_map[custom_id] = {
                'verdict': 'error',
                'why': f"Parse error: {str(e)}. Text: {text[:200]}"
            }
    
    if missing_custom_ids:
        print(f"Warning: {len(missing_custom_ids)} results missing custom_id")
        if len(missing_custom_ids) <= 5:
            for m in missing_custom_ids:
                print(f"  {m}")
    
    print(f"Results map has {len(results_map)} entries")
    print(f"Sample custom_ids in map: {list(results_map.keys())[:5]}")
    
    # Update rows with Claude judge results
    updated_rows = []
    missing_results = []
    for i, row in enumerate(rows):
        custom_id = f"{run_id}_{i}"
        result = results_map.get(custom_id, {})
        
        if not result:
            missing_results.append(i)
        
        verdict = result.get('verdict', 'error')
        why = result.get('why', 'No response')
        
        # Score mapping
        if row.get('type', '').strip() == 'mcq':
            vmap = {'correct': 1.0, 'ambiguous': 0.5, 'incorrect': 0.0}
        else:
            vmap = {'acceptable': 1.0, 'unacceptable': 0.0}
        
        score = vmap.get(verdict.lower(), 0.0)
        
        new_row = row.copy()
        new_row['claude_judge_verdict'] = verdict
        new_row['claude_judge_score'] = round(score, 4)
        new_row['claude_judge_why'] = why
        updated_rows.append(new_row)
    
    if missing_results:
        print(f"\nWarning: {len(missing_results)} rows had no matching results in batch")
        if len(missing_results) <= 10:
            print(f"  Missing row indices: {missing_results}")
        else:
            print(f"  Missing row indices (first 10): {missing_results[:10]}")
    
    # Save updated per_item.csv
    output_run_id = f"{run_id}_claude"
    output_dir = Path(f"benchmark/reports/{output_run_id}")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    output_csv = output_dir / 'per_item_claude.csv'
    print(f"\nSaving results to {output_csv}...")
    
    # Write CSV with Claude judge columns
    fieldnames = [
        'run_id', 'config', 'topic', 'type', 'seed', 'source_text_sha', 'idx',
        'qid_gold', 'qid_pred', 'structural_valid',
        'question_sim', 'ans_sim', 'distractor_diversity', 'ans_score', 'item_score',
        'judge_verdict', 'judge_score', 'judge_why',
        'judge2_verdict', 'judge2_score', 'judge2_why',
        'claude_judge_verdict', 'claude_judge_score', 'claude_judge_why'
    ]
    
    with output_csv.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        for row in updated_rows:
            writer.writerow(row)
    
    print(f"Saved {len(updated_rows)} rows to {output_csv}")
    print(f"Output run_id: {output_run_id}")
    
    return output_run_id, updated_rows


if __name__ == '__main__':
    run_id = sys.argv[1] if len(sys.argv) > 1 else '20251029_161124'
    judge_with_claude_batch(run_id)

