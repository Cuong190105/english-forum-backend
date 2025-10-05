import sys
import json
from pathlib import Path

project_root = str(Path(__file__).resolve().parents[1])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

print('sys.path (first 5):', sys.path[:5])

from utilities import ai_generator as g
from database.database import SessionLocal
from database import models

# Try to load a real post from DB (post_id = 1). If not present, fall back to hard-coded samples.
db = SessionLocal()
post = db.query(models.Post).filter(models.Post.post_id == 1).first()
if post:
    print(f"Loaded post id=1 from DB; using its content as first sample (title='{post.title}')")
    samples = [post.content]
else:
    print('No post with id=1 found in DB; using built-in samples')
    samples = []

if not samples:
    samples.extend([
        # grammar: present perfect vs past simple
        "Question: When do we use present perfect vs past simple? Example: I have lived here since 2010.",
        # grammar: gerund vs infinitive
        "Is it 'I enjoy swimming' or 'I enjoy to swim'? Please explain with examples.",
        # preposition collocation / multiword target
        "How do we use prepositions with 'interested' or 'good at'? e.g. 'good at programming' or 'interested in music'.",
        # vocabulary/collocation
        "How to use the phrase 'make a decision' versus 'take a decision' in British/American English?"
    ])
db.close()
print('='*40)
for idx, text in enumerate(samples, 1):
    print('='*40)
    print(f'SAMPLE {idx}:')
    # Truncate long content for display
    if isinstance(text, str) and len(text) > 400:
        print(text[:400] + '...')
    else:
        print(text)

    print('\nMCQs:')
    try:
        mcq_items = g.generate_homework(text, 'mcq', num_items=3)
        print(json.dumps(mcq_items, ensure_ascii=False, indent=2))
    except Exception:
        import traceback
        traceback.print_exc()

    # Optionally generate fills (commented out by default)
    # try:
    #     fill_items = g.generate_homework(text, 'fill', num_items=2)
    #     print('\nFills:')
    #     print(json.dumps(fill_items, ensure_ascii=False, indent=2))
    # except Exception:
    #     traceback.print_exc()

    print('\n')