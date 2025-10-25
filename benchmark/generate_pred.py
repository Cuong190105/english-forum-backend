from __future__ import annotations
import os
import json
from pathlib import Path
from typing import Literal, Dict, Any

from utilities.ai_generator_LLM_Clone import generate_with_llm


def _has_english(text: str) -> bool:
    import re
    return bool(re.search(r"[A-Za-z]", text or ""))


"""Generate predictions for minimal/cot configs with locked topic.

This module uses batch-friendly prompt invocation and validates the final JSON
via the shared Pydantic schema in utilities.ai_generator_LLM_Clone.
"""


def generate_pred(config: str, topic: str, hw_type: Literal['mcq','fill'], post_text: str, seed: int, out_path: Path, num_items: int = 1) -> Dict[str, Any]:
    cfg = config.lower().strip()
    # Only two configs: minimal and cot. Both use topic lock per plan.
    if cfg == 'minimal':
        mode = 'minimal'
    elif cfg == 'cot':
        mode = 'cot'
    else:
        mode = 'minimal'

    effective_text = post_text if _has_english(post_text) else post_text
    # locked topic to enforce topic-specific item creation
    items = generate_with_llm(
        effective_text,
        hw_type,
        num_items,
        mode=mode,
        temperature=0.0,
        seed=seed,
        model=os.getenv('PRED_MODEL') or 'gemini-2.5-flash',
        locked_topic=topic,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding='utf-8')
    return {'config': config, 'topic': topic, 'type': hw_type, 'seed': seed, 'n': len(items)}


if __name__ == '__main__':
    topic = os.getenv('TOPIC') or 'Passive Voice'
    hw_type = os.getenv('TYPE') or 'mcq'
    post_text = 'Students are taught grammar in many schools.'
    seed = int(os.getenv('SEED') or 0)
    config = os.getenv('CONFIG') or 'minimal'
    out = Path(f"benchmark/pred/{config}/{topic}/{hw_type}/seed{seed}.json")
    meta = generate_pred(config, topic, 'mcq' if hw_type=='mcq' else 'fill', post_text, seed, out)
    print(json.dumps(meta, ensure_ascii=False))
