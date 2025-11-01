from __future__ import annotations
from typing import List, Dict, Any, Tuple, Optional
from .embed import embed_texts, cosine
import os
import re
import unicodedata

# Scoring configuration
# Enable using answer similarity for MCQ via env (default OFF as requested)
# Set MCQ_USE_ANS_SIM=1 to enable.
MCQ_USE_ANS_SIM = (os.getenv('MCQ_USE_ANS_SIM', '0').lower() in {'1','true','yes','y'})

# Weights for item score when MCQ_USE_ANS_SIM is False
# Default: item_score = 0.75 * prompt_sim + 0.25 * distractor_diversity
MCQ_W_PROMPT_NOANS = float(os.getenv('MCQ_W_PROMPT_NOANS', '0.75'))
MCQ_W_DIV_NOANS = float(os.getenv('MCQ_W_DIV_NOANS', '0.25'))

# Weights for item score when MCQ_USE_ANS_SIM=True
# Defaults chosen to emphasize stem and answer correctness while keeping some diversity signal.
# You can override via env: MCQ_W_PROMPT, MCQ_W_ANS, MCQ_W_DIV (they will be renormalized if needed).
MCQ_W_PROMPT = float(os.getenv('MCQ_W_PROMPT', '0.50'))
MCQ_W_ANS = float(os.getenv('MCQ_W_ANS', '0.30'))
MCQ_W_DIV = float(os.getenv('MCQ_W_DIV', '0.20'))


def mcq_semantics(pred_item: Dict[str, Any], gold_item: Dict[str, Any]) -> Tuple[float, Optional[float], float, float]:
    stem_pred = pred_item['question']['prompt']
    stem_gold = gold_item['question']['prompt']
    cid_pred = pred_item['correctOptionId']
    # Distractor diversity (pred): mean pairwise cosine among 3 distractors
    distractors = [o['label'] for o in pred_item['question']['options'] if o['id'] != cid_pred]

    def _normalize_answer(s: str) -> str:
        if s is None:
            return ''
        s2 = str(s).strip()
        # Unicode normalize
        s2 = unicodedata.normalize('NFKD', s2)
        # Replace smart quotes
        s2 = s2.replace('“', '"').replace('”', '"').replace("’", "'")
        # Strip surrounding punctuation and brackets
        s2 = s2.strip(' \"\'`.,;:()[]{}')
        # Collapse whitespace
        s2 = re.sub(r'\s+', ' ', s2)
        return s2.lower()

    if MCQ_USE_ANS_SIM:
        cid_gold = gold_item['correctOptionId']
        label_pred = next(o['label'] for o in pred_item['question']['options'] if o['id'] == cid_pred)
        label_gold = next(o['label'] for o in gold_item['question']['options'] if o['id'] == cid_gold)
        # normalize labels and distractors for embedding/exact match stability
        label_pred_n = _normalize_answer(label_pred)
        label_gold_n = _normalize_answer(label_gold)
        distractors_n = [_normalize_answer(d) for d in distractors]
        vecs = embed_texts([stem_pred, stem_gold, label_pred_n, label_gold_n] + distractors_n)
        v_sp, v_sg, v_lp, v_lg, *v_d = vecs
        prompt_sim = cosine(v_sp, v_sg)
        ans_sim: Optional[float] = cosine(v_lp, v_lg)
        pairs = [(0,1),(0,2),(1,2)]
        cos_vals = [cosine(v_d[i], v_d[j]) for i,j in pairs]
        diversity = 1.0 - (sum(cos_vals)/len(cos_vals))
        item_score = MCQ_W_PROMPT*prompt_sim + MCQ_W_ANS*ans_sim + MCQ_W_DIV*diversity
        return prompt_sim, ans_sim, diversity, item_score
    else:
        # normalize distractors for more stable diversity embedding
        distractors_n = [_normalize_answer(d) for d in distractors]
        vecs = embed_texts([stem_pred, stem_gold] + distractors_n)
        v_sp, v_sg, *v_d = vecs
        prompt_sim = cosine(v_sp, v_sg)
        ans_sim = None
        pairs = [(0,1),(0,2),(1,2)] if len(v_d) == 3 else []
        cos_vals = [cosine(v_d[i], v_d[j]) for i,j in pairs] if pairs else [0.0]
        diversity = 1.0 - (sum(cos_vals)/len(cos_vals))
        item_score = MCQ_W_PROMPT_NOANS*prompt_sim + MCQ_W_DIV_NOANS*diversity
        return prompt_sim, ans_sim, diversity, item_score


def fill_semantics(pred_item: Dict[str, Any], gold_item: Dict[str, Any]) -> Tuple[float, float, float]:
    stem_pred = pred_item['question']['prompt']
    stem_gold = gold_item['question']['prompt']
    ans_pred = pred_item['answer']
    ans_gold = gold_item['answer']

    def _normalize_answer(s: str) -> str:
        if s is None:
            return ''
        s2 = str(s).strip()
        s2 = unicodedata.normalize('NFKD', s2)
        s2 = s2.replace('“', '"').replace('”', '"').replace("’", "'")
        s2 = s2.strip(' \"\'`.,;:()[]{}')
        s2 = re.sub(r'\s+', ' ', s2)
        return s2.lower()

    # Normalize answers before exact compare and embedding to reduce superficial mismatches
    ans_pred_n = _normalize_answer(ans_pred)
    ans_gold_n = _normalize_answer(ans_gold)

    vecs = embed_texts([stem_pred, stem_gold, ans_pred_n, ans_gold_n])
    v_sp, v_sg, v_ap, v_ag = vecs
    prompt_sim = cosine(v_sp, v_sg)
    exact = 1.0 if ans_pred_n == ans_gold_n else 0.0
    ans_sim = max(exact, cosine(v_ap, v_ag))
    item_score = 0.50*prompt_sim + 0.50*ans_sim
    return prompt_sim, ans_sim, item_score
