from __future__ import annotations
import os
import re
import random
from typing import List, Dict, Any, Optional

import json

from dotenv import load_dotenv
load_dotenv()

try:
    import httpx
except Exception:
    httpx = None

# Google GenAI SDK (AI Studio)
try:
    from google import genai
    try:
        from google.genai import types
    except Exception:
        types = None
except Exception:
    genai = None
    types = None

# Optional spaCy integration: used if installed and model is available.
try:
    import spacy
    try:
        _spacy_nlp = spacy.load("en_core_web_sm")
    except Exception:
        _spacy_nlp = None
except Exception:
    spacy = None
    _spacy_nlp = None

# optional lemminflect for robust inflection
try:
    from lemminflect import getInflection
except Exception:
    getInflection = None

# Optional lemminflect for reliable inflections
try:
    from lemminflect import getInflection
except Exception:
    getInflection = None

# small bilingual stopword set
STOPWORDS = {
    # English
    'the', 'is', 'in', 'and', 'to', 'of', 'a', 'an', 'for', 'on', 'with', 'that',
    'this', 'it', 'as', 'are', 'be', 'by', 'from', 'or', 'at', 'which', 'was',
    # Vietnamese common function words (small list)
    'và', 'là', 'của', 'cho', 'với', 'có', 'những', 'một', 'trong', 'các', 'đã', 'đang',
    'như', 'khi', 'này', 'ấy', 'tôi', 'anh', 'chị', 'em', 'ông', 'bà', 'nếu', 'nhưng',
    # Meta/UI words to avoid turning into targets
    'question', 'questions', 'example', 'examples', 'option', 'options', 'label', 'prompt', 'hint',
    'correct', 'incorrect', 'choose', 'select', 'pick', 'sounds', 'sound', 'best', 'id', 'use', 'uses', 'used', 'using'
}

# generation modes (env flags)
_GEN_MODE = os.getenv('AI_GENERATOR_MODE', 'hybrid').lower()  # 'llm' | 'local' | 'hybrid'
_LOCAL_USE_LLM_SENTENCE = os.getenv('LOCAL_USE_LLM_SENTENCE', '0') == '1'


def extract_keywords(text: str, top_k: int = 5) -> List[str]:
    """Unicode-aware keyword extraction for mixed English/Vietnamese text."""
    if not text:
        return []
    words = re.findall(r"\b[^\W\d_]+(?:['’][^\W\d_]+)*\b", text.lower(), flags=re.UNICODE)
    freq: Dict[str, int] = {}
    for w in words:
        if w in STOPWORDS or len(w) < 2:
            continue
        freq[w] = freq.get(w, 0) + 1
    items = sorted(freq.items(), key=lambda x: (-x[1], -len(x[0])))
    candidates = [w for w, _ in items]
    # Heuristic: drop meta-ish words and pure question terms even if not in STOPWORDS
    ban_substrings = [
        'question', 'example', 'option', 'prompt', 'label', 'hint', 'choose', 'select',
        'correct', 'incorrect', 'best'
    ]
    cleaned: List[str] = []
    for w in candidates:
        if any(b in w for b in ban_substrings):
            continue
        cleaned.append(w)
        if len(cleaned) >= top_k:
            break
    return cleaned


def _get_spacy_examples(text: str, targets: List[str]) -> Dict[str, List[str]]:
    """If spaCy is available and a model is loaded, return example sentences
    from the text that contain each target. Returns mapping target -> [sentences]."""
    examples: Dict[str, List[str]] = {}
    if _spacy_nlp is None or not text:
        return examples
    try:
        doc = _spacy_nlp(text)
    except Exception:
        return examples
    sents = [sent.text.strip() for sent in doc.sents]
    lowered = [s.lower() for s in sents]
    for t in targets:
        t0 = t.lower()
        matches = []
        for s, ls in zip(sents, lowered):
            if t0 in ls:
                matches.append(s)
        if matches:
            examples[t] = matches
    return examples


def _simple_conjugate_3rd_person(verb: str) -> str:
    """Very small heuristic to create 3rd-person singular verb forms.
    Not comprehensive, but good enough for simple verbs (add 's' or 'es')."""
    if verb.endswith('y') and len(verb) > 2 and verb[-2] not in 'aeiou':
        return verb[:-1] + 'ies'
    if verb.endswith(('s', 'sh', 'ch', 'x', 'z')):
        return verb + 'es'
    return verb + 's'


def _generate_distractors_spacy(correct: str, target: str, max_distractors: int = 3) -> List[str]:
    """Use spaCy (and lemminflect when available) to produce plausible distractors
    by transforming the correct sentence: tense/inflection changes, preposition swaps,
    negation insertion/removal, or small word-order tweaks."""
    distractors: List[str] = []
    if _spacy_nlp is None:
        return distractors
    try:
        doc = _spacy_nlp(correct)
    except Exception:
        return distractors

    # find main verb tokens
    verbs = [t for t in doc if t.pos_ == 'VERB']
    # find prepositions
    preps = [t for t in doc if t.pos_ == 'ADP']

    # Helper: replace token text at token.idx/ token.idx+len with new_text
    def replace_token(tok, new_text):
        s = correct
        start = tok.idx
        end = tok.idx + len(tok.text)
        return s[:start] + new_text + s[end:]

    # 1) verb inflection changes using lemminflect if available
    if verbs:
        v = verbs[0]
        lemma = v.lemma_
        # try past simple (VBD)
        past = None
        third = None
        if getInflection:
            try:
                forms = getInflection(lemma, tag='VBD')
                if forms:
                    past = forms[0]
                forms2 = getInflection(lemma, tag='VBZ')
                if forms2:
                    third = forms2[0]
            except Exception:
                past = None
                third = None
        # fallback simple heuristics
        if past is None:
            if lemma.endswith('e'):
                past = lemma + 'd'
            else:
                past = lemma + 'ed'
        if third is None:
            third = _simple_conjugate_3rd_person(lemma)

        # create variations
        distractors.append(replace_token(v, past))
        distractors.append(replace_token(v, third))

    # 2) preposition swaps
    if preps:
        common = ['in', 'on', 'at', 'for', 'with', 'to', 'by']
        for p in preps:
            for cand in common:
                if cand != p.text:
                    distractors.append(replace_token(p, cand))
                    if len(distractors) >= max_distractors:
                        break
            if len(distractors) >= max_distractors:
                break

    # 3) negation toggle (insert or remove 'not' after auxiliaries)
    auxs = [t for t in doc if t.tag_ in ('AUX', 'MD') or t.dep_ == 'aux']
    if auxs:
        a = auxs[0]
        # if 'not' following? naive check
        rest = correct[a.idx + len(a.text):].lstrip()
        if rest.startswith('not'):
            # remove not
            new = correct.replace(' not', '', 1)
        else:
            # insert not after auxiliary
            new = correct[:a.idx + len(a.text)] + ' not' + correct[a.idx + len(a.text):]
        distractors.append(new)

    # 4) small paraphrase: replace target with target+'ing' or lemma
    if target:
        if target in correct:
            if not target.endswith('ing'):
                distractors.append(correct.replace(target, target + 'ing'))
            # replace with lemma if target is multiword -> keep same

    # Ensure uniqueness and reasonable length
    unique: List[str] = []
    for d in distractors:
        if d and d != correct and d not in unique:
            unique.append(d)
        if len(unique) >= max_distractors:
            break

    # If still not enough, add simple heuristic variants
    while len(unique) < max_distractors:
        unique.append(correct + '.')

    return unique[:max_distractors]


def local_generate(post_text: str, hw_type: str, num_items: int = 5, topic: Optional[str] = None, targets: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Local fallback generator producing strict JSON for 'mcq' and 'fill'."""
    keywords = extract_keywords(post_text, top_k=max(5, num_items))
    # prefer explicit targets provided by topic detector
    if targets:
        # keep only tokens/phrases that are in the extracted keywords or include spaces
        expanded = []
        for t in targets:
            tt = t.lower().strip()
            if ' ' in tt or tt in keywords:
                expanded.append(tt)
        if expanded:
            keywords = expanded
    items: List[Dict[str, Any]] = []
    # Heuristics-based generation: create more varied and less template-locked questions.
    # We'll produce MCQs by creating a correct sentence and then generating distractors
    # using common error patterns: wrong tense, wrong plurality/number, wrong preposition,
    # or subtle paraphrase that changes meaning. For fill-in-the-blank we'll produce
    # sentences and blank out either the keyword or a related collocate.
    for i in range(num_items):
        kw = keywords[i % len(keywords)] if keywords else f"item{i+1}"
        qid = f"q{i+1}"

        def make_correct_sentence(k: str) -> str:
            # If enabled, try LLM to compose a fresh sentence frame
            if _LOCAL_USE_LLM_SENTENCE:
                llm_sent = llm_generate_sentence(k, post_text)
                if llm_sent:
                    return llm_sent
            # First try to use example sentences from the post (if spaCy can extract them)
            if _spacy_nlp is not None:
                ex = _get_spacy_examples(post_text, [k]).get(k)
                if ex:
                    return random.choice(ex)

            # If the target looks like a multi-word phrase or a grammar term, use phrase-style templates
            if ' ' in k or len(k) > 12 or not re.match(r"^[a-zA-Z]+$", k):
                # Compose a fresh sentence each time instead of fixed templates
                subjects = ["Learners", "Many students", "Teachers", "Writers", "Speakers"]
                verbs = ["debate", "practice", "apply", "misuse", "struggle with", "rely on"]
                contexts = [
                    "in real conversations",
                    "during exams",
                    "when writing emails",
                    "in academic essays",
                    "in everyday speech",
                ]
                return f"{random.choice(subjects)} {random.choice(verbs)} {k} {random.choice(contexts)}."

            # Otherwise assume single-word target (likely verb or noun). Create varied frames.
            third_person_subjects = ["She", "He", "My friend", "The student"]
            other_subjects = ["I", "We", "They", "Students"]
            subj = random.choice(third_person_subjects + other_subjects)

            # If subject is third person singular, conjugate verb heuristically
            if subj in third_person_subjects and re.match(r"^[a-zA-Z]+$", k):
                verb_form = _simple_conjugate_3rd_person(k)
                frames = [
                    f"{subj} {verb_form} every weekend.",
                    f"{subj} often {verb_form} in the evening.",
                    f"Why does {subj.lower()} {verb_form}?",
                ]
                return random.choice(frames)

            # generic frames
            adverbs = ["often", "sometimes", "rarely", "usually", "hardly ever"]
            times = ["on weekends", "after school", "in the evening", "before breakfast", "at noon"]
            patterns = [
                f"{subj} {k} {random.choice(times)}.",
                f"{subj} {random.choice(adverbs)} {k} at home.",
                f"{subj} decided to {k} yesterday.",
                f"{subj} prefers to {k} with friends.",
            ]
            return random.choice(patterns)

        def make_distractors(correct: str, k: str) -> List[str]:
            # Prefer spaCy-based transformations when available
            distractors: List[str] = []
            if _spacy_nlp is not None:
                try:
                    distractors = _generate_distractors_spacy(correct, k, max_distractors=3)
                except Exception:
                    distractors = []

            # If spaCy couldn't generate enough, fall back to lightweight heuristics
            if not distractors or len(distractors) < 3:
                hd: List[str] = []
                # 1) wrong verb form (remove or add 's' / change tense)
                if re.search(r"\b\w+s\b", correct):
                    hd.append(re.sub(r"(\w+)s\b", r"\1", correct))
                else:
                    hd.append(correct + 's')

                # 2) wrong preposition insertion/removal
                hd.append(correct.replace(' in ', ' on ') if ' in ' in correct else correct.replace(' on ', ' in '))

                # 3) paraphrase that subtly changes structure
                hd.append(correct.replace(k, k + 'ing') if not k.endswith('ing') else correct.replace(k, k.rstrip('ing')))

                # 4) nonsensical but plausible learner error
                hd.append(f"{k} are liked by me.")

                # merge unique distractors preserving spaCy ones first
                unique: List[str] = []
                for d in (distractors + hd):
                    if d and d != correct and d not in unique:
                        unique.append(d)
                    if len(unique) >= 3:
                        break

                # Pad with simple variants if not enough
                while len(unique) < 3:
                    unique.append(f"I like {k}.")

                return unique[:3]

            return distractors[:3]

        if hw_type == 'mcq':
            correct = make_correct_sentence(kw)
            # prefer spaCy-based distractors when possible
            distractors = []
            if _spacy_nlp is not None:
                try:
                    distractors = _generate_distractors_spacy(correct, kw, max_distractors=3)
                except Exception:
                    distractors = []
            if not distractors:
                distractors = make_distractors(correct, kw)
            choices = [correct] + distractors
            random.shuffle(choices)
            options = [{'id': f"{qid}-opt{j+1}", 'label': c} for j, c in enumerate(choices)]
            correct_id = next(opt['id'] for opt in options if opt['label'] == correct)
            # Prompt is descriptive but not a fixed template
            prompt_variants = [
                "Choose the most natural sentence.",
                "Which option sounds most correct?",
                "Pick the best sentence for clear English.",
                "Select the sentence that fits best in context.",
                "Which sentence would you use when speaking to a friend?",
            ]
            items.append({
                'type': 'mcq',
                'question': {
                    'id': qid,
                    'prompt': random.choice(prompt_variants),
                    'options': options,
                    'correctOptionId': correct_id,
                    'hint': None,
                }
            })
        else:
            # Fill-in-the-blank: blank either the keyword or a collocate (simple heuristic)
            sentence = make_correct_sentence(kw)
            # Slightly vary prompt framing by appending short contexts randomly
            if random.random() < 0.4:
                tails = [
                    " Use one word only.",
                    " Keep the verb form correct.",
                    " Choose a natural collocation.",
                    " Mind the preposition.",
                ]
                sentence = sentence.rstrip('.!?') + '.' + random.choice(tails)
            # choose blank target: either the keyword or a nearby common word
            if random.random() < 0.7:
                blanked = sentence.replace(kw, '_____', 1)
                answer = kw
            else:
                # try to blank a common short word (e.g., 'in', 'on', 'every') if present
                m = re.search(r"\b(in|on|every|the|a|an)\b", sentence)
                if m:
                    target = m.group(0)
                    blanked = sentence.replace(target, '_____', 1)
                    answer = target
                else:
                    blanked = sentence.replace(kw, '_____', 1)
                    answer = kw

            items.append({
                'type': 'fill',
                'question': {
                    'id': qid,
                    'prompt': blanked,
                    'answer': answer,
                    'hint': None,
                }
            })
    return items


def topic_detector(post_text: str) -> Dict[str, Any]:
    """Detect likely topic and candidate target phrases in the post.

    Returns a dict: { 'topic': str, 'targets': [str, ...] }
    """
    text = (post_text or '').lower()
    # grammar/topic keywords
    grammar_keys = [
        'present perfect', 'past simple', 'past continuous', 'present continuous', 'past perfect',
        'future', 'gerund', 'infinitive', 'passive', 'inversion', 'conditional', 'preposition',
        'modal', 'reported speech', 'tag question', 'comparative', 'superlative', 'relative clause',
        'tense', 'agreement'
    ]
    topic = ''
    for k in grammar_keys:
        if k in text:
            topic = k
            break

    # extract quoted examples first (they often contain target phrases)
    quoted = re.findall(r'"([^"]+)"|\'([^\']+)\'', post_text)
    quotes = []
    for q in quoted:
        # q is a tuple because of alternation; pick non-empty
        if isinstance(q, tuple):
            s = q[0] or q[1]
        else:
            s = q
        if s:
            quotes.append(s.strip())

    # collocation detection: n-grams (1..3) excluding stopwords
    words = re.findall(r"\b[^\W\d_]+(?:['’][^\W\d_]+)*\b", text, flags=re.UNICODE)
    candidates: Dict[str, int] = {}
    for n in (3, 2, 1):
        for i in range(len(words) - n + 1):
            ng = ' '.join(words[i:i+n])
            if any(w in STOPWORDS for w in ng.split()):
                continue
            candidates[ng] = candidates.get(ng, 0) + 1

    # sort candidates by frequency and length
    sorted_cands = sorted(candidates.items(), key=lambda x: (-x[1], -len(x[0])))
    # Filter out meta-phrases that include banned substrings
    ban_phr = ('question', 'example', 'option', 'prompt', 'label', 'hint')
    collocations = [c for c, _ in sorted_cands if not any(b in c for b in ban_phr)][:5]

    # build targets: prefer quoted examples, then collocations
    targets: List[str] = []
    for q in quotes:
        if q and q not in targets:
            targets.append(q)
    for c in collocations:
        if c and c not in targets:
            targets.append(c)

    # fallback: extract top single-word keywords
    if not targets:
        kws = extract_keywords(post_text, top_k=5)
        targets = kws

    return {'topic': topic or 'general', 'targets': targets}


def _strip_code_fences(s: str) -> str:
    if not s:
        return s
    s2 = s.strip()
    # Remove triple backtick fences if present
    if s2.startswith("```"):
        s2 = re.sub(r"^```[a-zA-Z0-9_-]*\n", "", s2)
        if s2.endswith("```"):
            s2 = s2[:-3]
    return s2.strip()


def llm_generate_sentence(keyword: str, post_text: str, model: str = 'models/gemini-2.5-flash') -> Optional[str]:
    """Ask LLM to compose a single natural sentence using the keyword in context.
    Returns a plain sentence (no quotes/backticks), or None on failure."""
    user_prompt = (
        "Write ONE natural English sentence that uses the target naturally.\n"
        "Constraints:\n"
        "- Do not return explanations or markdown.\n"
        "- Do not wrap in quotes or backticks.\n"
        "- Keep it between 6 and 20 words if possible.\n\n"
        f"Context (optional):\n{post_text[:600]}\n\n"
        f"Target: {keyword}\n"
    )
    out = call_google_generative(user_prompt, model=model)
    if not out:
        return None
    s = _strip_code_fences(out).strip()
    s = s.splitlines()[0].strip()
    if s and s[-1] not in '.!?':
        s += '.'
    if 'Write ONE natural English sentence' in s:
        return None
    return s


def call_google_generative(prompt: str, model: str = 'models/gemini-2.5-flash') -> Optional[str]:
    """Call Google Generative API (basic adapter). Returns raw text or None."""
    key = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
    debug = os.getenv('DEBUG_AI', '') == '1'
    if not key or httpx is None:
        if debug:
            print('[ai_generator] GOOGLE_API_KEY missing or httpx not available; skipping Google call')
        return None
    # Prefer the official Python client if available
    if genai is not None:
        try:
            # New google-genai SDK provides Client()
            if hasattr(genai, 'Client'):
                if debug:
                    print('[ai_generator] Using google.genai Client (new SDK)')
                client = genai.Client(api_key=key)
                try:
                    resp = client.models.generate_content(model=model, contents=prompt)
                    # Try to extract common text locations
                    if hasattr(resp, 'candidates') and resp.candidates:
                        cand0 = resp.candidates[0]
                        content = getattr(cand0, 'content', None) or (cand0.get('content') if isinstance(cand0, dict) else None)
                        if content:
                            parts = getattr(content, 'parts', None) or (content.get('parts') if isinstance(content, dict) else None)
                            if parts:
                                part0 = parts[0]
                                text = getattr(part0, 'text', None) or (part0.get('text') if isinstance(part0, dict) else None)
                                if text:
                                    return text
                    if hasattr(resp, 'text') and resp.text:
                        return resp.text
                except Exception as e:
                    if debug:
                        print('[ai_generator] google.genai Client call failed:', repr(e))
                    
        except Exception as e:
            if debug:
                print('[ai_generator] google.genai module error:', repr(e))
    # Fallback: use HTTP endpoint via httpx
    if debug:
        print('[ai_generator] Falling back to HTTP v1beta generateContent')
    url = f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}'
    data = {
        'contents': [
            { 'role': 'user', 'parts': [ { 'text': prompt } ] }
        ],
        'generationConfig': { 'temperature': 0.3, 'maxOutputTokens': 512 }
    }
    try:
        resp = httpx.post(url, json=data, timeout=20.0)
        resp.raise_for_status()
        j = resp.json()
        # Try Gemini REST response shape
        if isinstance(j, dict) and 'candidates' in j and j['candidates']:
            cand0 = j['candidates'][0]
            content = cand0.get('content')
            if content and 'parts' in content and content['parts']:
                part0 = content['parts'][0]
                if 'text' in part0:
                    return part0['text']
        return None
    except Exception:
        if debug:
            import traceback as _tb
            print('[ai_generator] httpx Google call failed:')
            _tb.print_exc()
        return None


def generate_with_llm(post_text: str, hw_type: str, num_items: int = 5) -> Optional[List[Dict[str, Any]]]:
    """Use Google Generative API to request a strict JSON array of items.

    Returns parsed list on success, or None on any failure.
    """
    # Strict JSON schema instruction (MCQ/FILL tailored)
    if hw_type == 'mcq':
        schema_instruction = (
            "Return ONLY a JSON array of objects (no commentary). "
            "Each object must have: 'type' = 'mcq' and a 'question' object. "
            "question.id MUST be 'practice-{number}' starting at 1 and incrementing by 1. "
            "question.prompt should read well on a phone cue card (~80–160 characters). Not necessarily short; be clear and contextual. "
            "question.options is an array of EXACTLY 4 options, each with fields {id,label}. "
            "Option ids MUST be 'a', 'b', 'c', 'd' (lowercase). "
            "question.correctOptionId MUST be one of 'a'|'b'|'c'|'d'. "
            "question.hint may be null. "
            "Do NOT include code fences or explanations."
        )
    else:
        schema_instruction = (
            "Return ONLY a JSON array of objects (no commentary). "
            "Each object must have: 'type' = 'fill' and a 'question' object. "
            "question.id MUST be 'practice-{number}' starting at 1 and incrementing by 1. "
            "question.prompt should be a cue card (~80–160 characters) containing a FIXED blank represented by '_____'. "
            "Do NOT vary the number of underscores to match the answer length. Always use exactly five underscores '_____'. "
            "question.options is an array of EXACTLY 4 options, each with fields {id,label}. "
            "Option ids MUST be 'a', 'b', 'c', 'd' (lowercase). "
            "question.correctOptionId MUST be one of 'a'|'b'|'c'|'d'. "
            "question.hint may be null. "
            "Do NOT include code fences or explanations."
        )

    # topic-aware prompt
    td = topic_detector(post_text)
    topic = td.get('topic')
    # few-shot example tailored for MCQ/FILL with a/b/c/d
    if hw_type == 'mcq':
        few_shot = (
            "Example (mcq): [ {\"type\": \"mcq\", \"question\": {\"id\": \"practice-1\", \"prompt\": \"Which sentence uses the present perfect naturally?\", \"options\": ["
            "{\"id\": \"a\", \"label\": \"I have lived here since 2010.\"},"
            "{\"id\": \"b\", \"label\": \"I live here since 2010.\"},"
            "{\"id\": \"c\", \"label\": \"I am live here since 2010.\"},"
            "{\"id\": \"d\", \"label\": \"I was live here since 2010.\"} ],"
            "\"correctOptionId\": \"a\", \"hint\": null } } ]\n"
        )
    else:
        few_shot = (
            "Example (fill): [ {\"type\": \"fill\", \"question\": {\"id\": \"practice-1\", "
            "\"prompt\": \"Complete the sentence with one word: Had regulators required _____ earlier, some harms might have been avoided.\", "
            "\"options\": [ {\"id\": \"a\", \"label\": \"transparency\"}, {\"id\": \"b\", \"label\": \"transparent\"}, {\"id\": \"c\", \"label\": \"transparently\"}, {\"id\": \"d\", \"label\": \"transparencying\"} ], "
            "\"correctOptionId\": \"a\", \"hint\": null } } ]\n"
        )

    # Build user prompt emphasizing creativity and non-template outputs
    user_prompt = (
        f"Post text:\n{post_text}\n\nTopic (detected): {topic}\n\n"
        f"Generate {num_items} {hw_type} items. Vary phrasing and difficulty. Strictly follow the schema.\n\n"
        f"{schema_instruction}\n\n{few_shot}"
    )
    debug = os.getenv('DEBUG_AI', '') == '1'
    if debug:
        print('[ai_generator] LLM user prompt:')
        print(user_prompt[:1000])
    out = call_google_generative(user_prompt)
    if not out:
        if debug:
            print('[ai_generator] LLM returned no output (None)')
        return None
    if debug:
        print('[ai_generator] Raw LLM output:')
        print(out[:2000])
    try:
        cleaned = _strip_code_fences(out)
        # Some models may prepend/explain; try to extract first JSON array
        if not cleaned.lstrip().startswith('['):
            m = re.search(r"\[.*\]", cleaned, flags=re.DOTALL)
            if m:
                cleaned = m.group(0)
        parsed = json.loads(cleaned)
        if isinstance(parsed, list):
            return parsed
        if debug:
            print('[ai_generator] Parsed JSON is not a list; type:', type(parsed))
    except Exception:
        if debug:
            import traceback as _tb
            print('[ai_generator] Failed to parse LLM output as JSON; raw output printed above')
            _tb.print_exc()
        # fallthrough to None
    return None


def generate_homework(post_text: str, hw_type: str, num_items: int = 5) -> List[Dict[str, Any]]:
    hw_type = hw_type.lower()
    if hw_type not in {'mcq', 'fill'}:
        hw_type = 'mcq'
    # detect topic and targets, pass them to local fallback
    td = topic_detector(post_text)
    if _GEN_MODE == 'llm':
        items = generate_with_llm(post_text, hw_type, num_items)
        if items:
            return items
        return local_generate(post_text, hw_type, num_items, topic=td.get('topic'), targets=td.get('targets'))
    if _GEN_MODE == 'local':
        return local_generate(post_text, hw_type, num_items, topic=td.get('topic'), targets=td.get('targets'))
    # hybrid default: try LLM then fallback
    items = generate_with_llm(post_text, hw_type, num_items)
    if items:
        return items
    return local_generate(post_text, hw_type, num_items, topic=td.get('topic'), targets=td.get('targets'))
