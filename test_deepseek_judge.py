"""Test DeepSeek judge functionality."""
import os
from benchmark.judge import judge_mcq_deepseek, judge_fill_deepseek

# Check environment
print("=" * 70)
print("DeepSeek Judge Test")
print("=" * 70)

deepseek_key = os.getenv('DEEPSEEK_API_KEY')
if not deepseek_key:
    print("❌ DEEPSEEK_API_KEY not set in environment")
    print("\nTo use DeepSeek judge:")
    print("  1. Set DEEPSEEK_API_KEY in .env file")
    print("  2. Optionally set JUDGE2_MODEL (default: deepseek-reasoner)")
    print("  3. Set JUDGES=gemini,deepseek to enable both judges")
    exit(1)

print(f"✅ DEEPSEEK_API_KEY: {'*' * 10}{deepseek_key[-4:]}")
print(f"✅ JUDGE2_MODEL: {os.getenv('JUDGE2_MODEL') or 'deepseek-reasoner (default)'}")
print(f"✅ JUDGES config: {os.getenv('JUDGES') or 'gemini,deepseek (default)'}")

# Test MCQ
print("\n" + "=" * 70)
print("Testing MCQ Judge")
print("=" * 70)

stem = "The discovery _____ by researchers at York University."
options = {
    "a": "was made",
    "b": "has made",
    "c": "is made",
    "d": "made"
}
correct_id = "a"
topic = "Past Simple"

print(f"\nStem: {stem}")
print(f"Options: {options}")
print(f"Correct: {correct_id}")
print(f"Topic: {topic}")
print("\nCalling DeepSeek judge...")

try:
    result = judge_mcq_deepseek(stem, options, correct_id, topic, context=None)
    print("\n✅ Result:")
    print(f"  Verdict: {result.get('verdict')}")
    print(f"  Reason: {result.get('why', '')[:200]}")
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()

# Test FILL
print("\n" + "=" * 70)
print("Testing FILL Judge")
print("=" * 70)

prompt = "The discovery _____ by researchers in 2007."
answer = "was made"
topic = "Past Simple"

print(f"\nPrompt: {prompt}")
print(f"Answer: {answer}")
print(f"Topic: {topic}")
print("\nCalling DeepSeek judge...")

try:
    result = judge_fill_deepseek(prompt, answer, topic, context=None)
    print("\n✅ Result:")
    print(f"  Verdict: {result.get('verdict')}")
    print(f"  Reason: {result.get('why', '')[:200]}")
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 70)
print("Test Complete")
print("=" * 70)

