from __future__ import annotations
import os
import json
from pathlib import Path
from typing import Literal

from utilities.ai_generator_LLM_Clone import generate_with_llm


def generate_gold(topic: str, hw_type: Literal['mcq','fill'], post_text: str, out_path: Path, num_items: int = 1):
    # Deterministic config
    items = generate_with_llm(
        post_text,
        hw_type,
        num_items,
        mode='minimal',
        temperature=0.0,
        seed=0,
        model=os.getenv('GOLD_MODEL') or 'gemini-2.5-pro',
        # Enforce the locked topic if provided by caller
        locked_topic=topic,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding='utf-8')
    return items


if __name__ == '__main__':
    # Example quick run placeholder
    topic = os.getenv('TOPIC') or 'Passive Voice'
    hw_type = os.getenv('TYPE') or 'mcq'
    post_text = 'Students are taught grammar in many schools.'
    out = Path(f"benchmark/gold/{topic}/{hw_type}/seed0.json")
    generate_gold(topic, 'mcq' if hw_type=='mcq' else 'fill', post_text, out)
    print(f"Gold written: {out}")
