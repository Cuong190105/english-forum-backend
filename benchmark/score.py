from __future__ import annotations
from typing import List, Dict, Any, Tuple, Optional
from .embed import embed_texts, cosine

# Scoring configuration
# If False, MCQ will NOT use ans_sim in item score; weights are renormalized.
MCQ_USE_ANS_SIM = False
# Weights for item score when MCQ_USE_ANS_SIM is False
# Requested: item_score = 0.70 * prompt_sim + 0.30 * distractor_diversity
MCQ_W_PROMPT_NOANS = 0.70
MCQ_W_DIV_NOANS = 0.30
# Weights when ans_sim is used (legacy)
MCQ_W_PROMPT = 0.40
MCQ_W_ANS = 0.40
MCQ_W_DIV = 0.20


def mcq_semantics(pred_item: Dict[str, Any], gold_item: Dict[str, Any]) -> Tuple[float, Optional[float], float, float]:
    stem_pred = pred_item['question']['prompt']
    stem_gold = gold_item['question']['prompt']
    cid_pred = pred_item['correctOptionId']
    # Distractor diversity (pred): mean pairwise cosine among 3 distractors
    distractors = [o['label'] for o in pred_item['question']['options'] if o['id'] != cid_pred]

    if MCQ_USE_ANS_SIM:
        cid_gold = gold_item['correctOptionId']
        label_pred = next(o['label'] for o in pred_item['question']['options'] if o['id'] == cid_pred)
        label_gold = next(o['label'] for o in gold_item['question']['options'] if o['id'] == cid_gold)
        vecs = embed_texts([stem_pred, stem_gold, label_pred, label_gold] + distractors)
        v_sp, v_sg, v_lp, v_lg, *v_d = vecs
        prompt_sim = cosine(v_sp, v_sg)
        ans_sim: Optional[float] = cosine(v_lp, v_lg)
        pairs = [(0,1),(0,2),(1,2)]
        cos_vals = [cosine(v_d[i], v_d[j]) for i,j in pairs]
        diversity = 1.0 - (sum(cos_vals)/len(cos_vals))
        item_score = MCQ_W_PROMPT*prompt_sim + MCQ_W_ANS*ans_sim + MCQ_W_DIV*diversity
        return prompt_sim, ans_sim, diversity, item_score
    else:
        vecs = embed_texts([stem_pred, stem_gold] + distractors)
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

    vecs = embed_texts([stem_pred, stem_gold, ans_pred, ans_gold])
    v_sp, v_sg, v_ap, v_ag = vecs
    prompt_sim = cosine(v_sp, v_sg)
    exact = 1.0 if ans_pred.strip().lower() == ans_gold.strip().lower() else 0.0
    ans_sim = max(exact, cosine(v_ap, v_ag))
    item_score = 0.50*prompt_sim + 0.50*ans_sim
    return prompt_sim, ans_sim, item_score
