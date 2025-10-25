from __future__ import annotations
import os
from typing import List
import math

try:
    from google import genai
except Exception:
    genai = None

# Load .env so GOOGLE_API_KEY/GEMINI_API_KEY is available if defined there
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass


def _client():
    key = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
    if not key:
        raise RuntimeError('GOOGLE_API_KEY or GEMINI_API_KEY not set')
    if genai is None:
        raise RuntimeError('google-genai not installed')
    # Cache client per process
    global _EMB_CLIENT, _EMB_KEY
    try:
        _EMB_CLIENT
    except NameError:
        _EMB_CLIENT = None  # type: ignore[assignment]
        _EMB_KEY = None  # type: ignore[assignment]
    if _EMB_CLIENT is None or _EMB_KEY != key:
        _EMB_CLIENT = genai.Client(api_key=key)  # type: ignore[assignment]
        _EMB_KEY = key  # type: ignore[assignment]
    return _EMB_CLIENT  # type: ignore[return-value]


def embed_texts(texts: List[str], model: str = 'text-embedding-004') -> List[List[float]]:
    c = _client()

    def to_list(x):
        try:
            return list(x)
        except Exception:
            return None

    def extract_vec_from_obj(obj):
        # Try attribute-based shapes
        emb = getattr(obj, 'embedding', None)
        embs = getattr(obj, 'embeddings', None)
        if emb is not None:
            vals = getattr(emb, 'values', None)
            if vals is not None:
                return list(vals)
            # Sometimes embedding is already a list
            if isinstance(emb, (list, tuple)):
                return list(emb)
            # Dict-like
            if isinstance(emb, dict) and 'values' in emb:
                return list(emb['values'])
        if embs is not None:
            # embs could be list of vectors or a single vector
            if isinstance(embs, (list, tuple)):
                # If it's a list of numbers (single vector)
                if embs and isinstance(embs[0], (float, int)):
                    return list(embs)
                # If it's a list of objects each with .values
                if embs and hasattr(embs[0], 'values'):
                    return [list(x.values) for x in embs]  # type: ignore
                # If it's a list of dicts with 'values'
                if embs and isinstance(embs[0], dict) and 'values' in embs[0]:
                    return [list(x['values']) for x in embs]  # type: ignore
            # If has .values attribute directly
            vals = getattr(embs, 'values', None)
            if vals is not None:
                return list(vals)
        # Dict-like top-level
        if isinstance(obj, dict):
            if 'embedding' in obj:
                e = obj['embedding']
                if isinstance(e, dict) and 'values' in e:
                    return list(e['values'])
                if isinstance(e, (list, tuple)):
                    return list(e)
            if 'embeddings' in obj:
                e = obj['embeddings']
                if isinstance(e, (list, tuple)):
                    if e and isinstance(e[0], (float, int)):
                        return list(e)
                    if e and isinstance(e[0], dict) and 'values' in e[0]:
                        return [list(x['values']) for x in e]
        return None

    # First, try batch call
    out = c.models.embed_content(model=model, contents=texts)

    vecs: List[List[float]] = []
    parsed = False
    if isinstance(out, list):
        # Many SDKs return a list of per-input objects
        for o in out:
            v = extract_vec_from_obj(o)
            if v is None:
                continue
            if v and isinstance(v[0], list):
                # If a list of vectors somehow per output, extend
                vecs.extend(v)  # type: ignore[arg-type]
            else:
                vecs.append(v)  # type: ignore[arg-type]
        parsed = len(vecs) == len(texts)
    else:
        v = extract_vec_from_obj(out)
        if v is not None:
            if v and isinstance(v[0], list):
                vecs = v  # type: ignore[assignment]
            else:
                vecs = [v]  # type: ignore[list-item]
            parsed = len(vecs) in (1, len(texts))

    if not parsed or len(vecs) != len(texts):
        # Fallback: serial calls per text (reliable shape across SDKs)
        vecs = []
        for t in texts:
            single = c.models.embed_content(model=model, contents=t)
            v = extract_vec_from_obj(single)
            if v is None:
                raise RuntimeError('Unknown embed_content output shape')
            if v and isinstance(v[0], list):
                # If single returns a list of vectors, pick the first
                vecs.append(list(v[0]))  # type: ignore[index]
            else:
                vecs.append(list(v))  # type: ignore[arg-type]

    return vecs


def cosine(a: List[float], b: List[float]) -> float:
    dot = sum(x*y for x, y in zip(a, b))
    na = math.sqrt(sum(x*x for x in a))
    nb = math.sqrt(sum(y*y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)
