from __future__ import annotations
import os
import json
from pathlib import Path
from typing import List, Dict, Any, Tuple

# Use the same SDK assumptions as the generator utility
try:
    from google import genai
    from google.genai.types import GenerateContentConfig
except Exception:
    genai = None
    GenerateContentConfig = None
# Load .env if present so GOOGLE_API_KEY/GEMINI_API_KEY can be read
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass


def load_topics_map(topics_json_path: Path) -> Dict[str, List[Dict[str, str]]]:
    """Load topics as a dict: category -> list of {id, display} objects.
    Backward compatible with old schema where each category was a list of strings.
    In that case, convert to objects with id derived from safe normalization and display as original string.
    """
    raw = json.loads(topics_json_path.read_text(encoding='utf-8'))
    norm: Dict[str, List[Dict[str, str]]] = {}
    for cat, subs in raw.items():
        norm_list: List[Dict[str, str]] = []
        if subs and isinstance(subs, list):
            for s in subs:
                if isinstance(s, dict):
                    # Expect keys id/display
                    sid = str(s.get('id') or '').strip()
                    disp = str(s.get('display') or '').strip()
                    if not disp and sid:
                        disp = sid.replace('_', ' ')
                    if disp:
                        norm_list.append({'id': sid or disp, 'display': disp})
                else:
                    # Old string entry
                    disp = str(s).strip()
                    sid = disp.lower().replace(' ', '_').replace('/', '_').replace('…', '').replace('—', '-')
                    norm_list.append({'id': sid, 'display': disp})
        norm[cat] = norm_list
    return norm


def build_label_prompt(context_text: str, topics_map: Dict[str, List[Dict[str, str]]]) -> str:
    # Flatten categories to a list of "Category :: display (id)" lines for selection clarity
    lines: List[str] = []
    for cat, subs in topics_map.items():
        for s in subs:
            disp = s.get('display', '')
            sid = s.get('id', '')
            if sid and sid != disp:
                lines.append(f"- {cat} :: {disp} (id: {sid})")
            else:
                lines.append(f"- {cat} :: {disp}")
    topics_block = "\n".join(lines)
    prompt = (
        "You are an expert English grammar examiner.\n"
        "Task: Choose exactly ONE most relevant grammar topic from the list for writing exam questions based on the given context.\n"
        "Output JSON only with keys: {\"category\": string, \"topic\": string}. No extra text.\n\n"
        "AVAILABLE TOPICS (category :: subtopic)\n"
        f"{topics_block}\n\n"
        "CONTEXT:\n"
        f"{context_text}\n\n"
        "Rules:\n"
        "- Pick the single best-fitting subtopic; if multiple are plausible, pick the most specific.\n"
    "- Ensure the choice strictly matches the grammar focus and is specific.\n"
    )
    return prompt


def label_one(client, model: str, text: str, topics_map: Dict[str, List[Dict[str, str]]]):
    prompt = build_label_prompt(text, topics_map)
    cfg = GenerateContentConfig(response_mime_type='application/json')
    resp = client.models.generate_content(model=model, contents=prompt, config=cfg)
    if getattr(resp, 'text', None):
        raw = resp.text
    elif getattr(resp, 'parsed', None) is not None:
        # Some SDKs parse into a dict-like already
        try:
            if hasattr(resp.parsed, 'model_dump'):
                return resp.parsed.model_dump()
            elif hasattr(resp.parsed, 'dict'):
                return resp.parsed.dict()
            else:
                return resp.parsed
        except Exception:
            raw = json.dumps(resp.parsed, ensure_ascii=False)
    else:
        raw = '{}'
    try:
        data = json.loads(raw)
        # Normalize keys
        category = str(data.get('category', '')).strip()
        topic_raw = str(data.get('topic', '')).strip()

        def find_match(cat: str, needle: str) -> Tuple[bool, str]:
            """Return (found, display) by matching needle against display or id within cat."""
            subs = topics_map.get(cat, [])
            for obj in subs:
                disp = obj.get('display', '')
                sid = obj.get('id', '')
                if needle == disp or needle == sid:
                    return True, disp or sid
            return False, ''

        valid = False
        display_choice = ''
        if category in topics_map:
            valid, display_choice = find_match(category, topic_raw)

        # If not valid, try to find topic anywhere by display or id
        if not valid and topic_raw:
            for cat, subs in topics_map.items():
                for obj in subs:
                    disp = obj.get('display', '')
                    sid = obj.get('id', '')
                    if topic_raw == disp or topic_raw == sid:
                        category = cat
                        display_choice = disp or sid
                        valid = True
                        break
                if valid:
                    break

        if not valid:
            # Fallback: first category's first item (deterministic)
            first_cat = next(iter(topics_map.keys()))
            first_item = topics_map[first_cat][0]
            category = first_cat
            display_choice = first_item.get('display', first_item.get('id', ''))

        return {"category": category, "topic": display_choice}
    except Exception:
        first_cat = next(iter(topics_map.keys()))
        first_item = topics_map[first_cat][0]
        return {"category": first_cat, "topic": first_item.get('display', first_item.get('id', ''))}


def main():
    import argparse
    ap = argparse.ArgumentParser(description='Label each source text with a locked grammar topic using Gemini.')
    ap.add_argument('--input', required=True, help='Path to source JSONL (e.g., benchmark/source_texts/jfleg_1000_source_texts.jsonl)')
    ap.add_argument('--output', required=True, help='Path to output JSONL with added topic fields')
    ap.add_argument('--topics', default='benchmark/topics_locked.json', help='Path to topics JSON map')
    ap.add_argument('--model', default='gemini-2.5-flash-lite')
    ap.add_argument('--limit', type=int, default=0, help='If >0, label only the first N rows')
    args = ap.parse_args()

    key = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
    if not key:
        raise RuntimeError('GOOGLE_API_KEY or GEMINI_API_KEY is not set in environment')
    if genai is None or GenerateContentConfig is None:
        raise RuntimeError('google-genai not installed. Install it or update requirements.txt')

    client = genai.Client(api_key=key)
    topics_map = load_topics_map(Path(args.topics))

    in_path = Path(args.input)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    n = 0
    with in_path.open('r', encoding='utf-8') as fin, out_path.open('w', encoding='utf-8') as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            text = rec.get('corrected_text') or rec.get('source_text') or rec.get('text') or ''
            label = label_one(client, args.model, text, topics_map)
            rec['topic'] = label.get('topic')
            rec['topic_category'] = label.get('category')
            fout.write(json.dumps(rec, ensure_ascii=False) + '\n')
            n += 1
            if args.limit and n >= args.limit:
                break
    print(f'Done: {n} rows labeled -> {out_path}')


if __name__ == '__main__':
    main()
