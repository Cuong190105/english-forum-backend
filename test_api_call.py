"""Test API call to compare with AI Studio results."""
import os
import json

# Enable debug
os.environ['DEBUG_AI'] = '1'

from utilities.ai_generator_LLM_Clone import generate_with_llm

# Same source text
source_text = """A recent study of ancient and modern elephants has come up with the unexpected conclusion that the African elephant is divided into two distinct  species.
The discovery was made by researchers at York and Harvard Universities when they were examining the genetic relationship between the ancient woolly mammoth and mastodon to modern elephants -- the Asian elephant, African forest elephant, and African savanna elephant.
Once they obtained DNA sequences  from two fossils , mammoths,and mastodons the team compared them with DNA from modern elephants. They found to their amazement that modern forest and savanna elephants are as distinct from each other as Asian elephants and mammoths.
The scientists used detailed genetic analysis to prove that the African savanna elephant and the African forest elephant have been distinct species for several million years. The divergence of the two species took place around the time of the divergence of Asian elephants and woolly mammoths. This result amazed all the scientists. There has long been debate in the scientific community that the two might be separate species, but this is the most convincing scientific evidence so far that they are indeed different species.
Previously, many naturalists believed that African savanna elephants and African forest elephants were two populations of the same species, despite the elephants' significant size differences. The savanna elephant has an average shoulder height of 3.5 metres while the forest elephant has an average shoulder height of 2.5 metres. The savanna elephant weighs between six and seven tons, roughly double the weight of the forest elephant. But the fact that they look so different does not necessarily mean they are different species. However the proof lay in the analysis of the DNA.
Alfred Roca, assistant professor in the Department of Animal Sciences at the University of Illinois, said, "We now have to treat the forest and savanna elephants as two different units for conservation purposes. Since 1950,all African elephants have been conserved as one species. Now that we know the forest and savanna elephants are two very distinctive animals, the forest elephant should become a bigger priority  for conservation purposes.\""""

print("=" * 70)
print("Testing API call with same params as AI Studio")
print("=" * 70)
print(f"\nSource text length: {len(source_text)} chars")
print(f"Topic: Past Simple")
print(f"Mode: minimal")
print(f"Num items: 1")
print(f"Temperature: 0.0")
print(f"Seed: 0")
print("\nCalling API...\n")

try:
    items = generate_with_llm(
        post_text=source_text,
        hw_type='mcq',
        num_items=1,
        mode='minimal',
        temperature=0.0,
        seed=0,
        locked_topic='Past Simple',
        model='gemini-2.5-flash',
    )
    
    print("\n" + "=" * 70)
    print("RESULT FROM API:")
    print("=" * 70)
    print(json.dumps(items, indent=2, ensure_ascii=False))
    
    if items:
        first_item = items[0]
        prompt = first_item.get('question', {}).get('prompt', '')
        print("\n" + "=" * 70)
        print("COMPARISON:")
        print("=" * 70)
        print(f"\nAI Studio result: 'The discovery _____ by researchers...' ✅")
        print(f"API call result:  '{prompt[:60]}...'")
        
        if '_____' in prompt or '____' in prompt:
            print("\n✅ API call generated grammar test with blank!")
        else:
            print("\n❌ API call generated comprehension question (no blank)")
            print("\n🔍 This confirms the issue is NOT with schema,")
            print("   but something else in the API call chain.")
        
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()

