import json
import random
from typing import Any, Optional
from unittest.mock import patch
import pytest
from utilities import ai
from google.genai.types import HttpResponse
from google.genai._api_client import BaseApiClient
from pydantic import BaseModel

class SampleModel(BaseModel):
    wrong_field: str
    another_field: int

body1 = json.dumps({
  "candidates": [
    {
      "content": {
        "parts": [
          {
            "text": "{\n  \"category\": \"tenses_aspects\",\n  \"topic\": \"Present Simple (id: present_simple)\"\n}"
          }
        ],
        "role": "model"
      },
      "finishReason": "STOP",
      "index": 0
    }
  ],
  "usageMetadata": {
    "promptTokenCount": 1659,
    "candidatesTokenCount": 24,
    "totalTokenCount": 1769,
    "promptTokensDetails": [
      {
        "modality": "TEXT",
        "tokenCount": 1659
      }
    ],
    "thoughtsTokenCount": 86
  },
  "modelVersion": "gemini-2.5-flash",
  "responseId": "V3wYaZ_lMIKF1e8PhuCysQg"
}, indent=2)
body2 = json.dumps({
  "candidates": [
    {
      "content": {
        "parts": [
          {
            "text": "```JSON\n{\n  \"category\": \"tenses_aspects\",\n  \"topic\": \"Present Simple (id: present_simple)\"\n}\n```"
          }
        ],
        "role": "model"
      },
      "finishReason": "STOP",
      "index": 0
    }
  ],
  "usageMetadata": {
    "promptTokenCount": 1659,
    "candidatesTokenCount": 24,
    "totalTokenCount": 1769,
    "promptTokensDetails": [
      {
        "modality": "TEXT",
        "tokenCount": 1659
      }
    ],
    "thoughtsTokenCount": 86
  },
  "modelVersion": "gemini-2.5-flash",
  "responseId": "V3wYaZ_lMIKF1e8PhuCysQg"
}, indent=2)
body3 = json.dumps({
  "candidates": [
    {
      "content": {
        "parts": [
          {
            "text": "[\n  {\n    \"type\": \"mcq\",\n    \"question\": {\n      \"id\": \"ps_mcq_001\",\n      \"prompt\": \"My brother usually _____ his homework after dinner.\",\n      \"options\": [\n        {\n          \"id\": \"a\",\n          \"label\": \"do\"\n        },\n        {\n          \"id\": \"b\",\n          \"label\": \"does\"\n        },\n        {\n          \"id\": \"c\",\n          \"label\": \"doing\"\n        },\n        {\n          \"id\": \"d\",\n          \"label\": \"did\"\n        }\n      ]\n    },\n    \"correctOptionId\": \"b\",\n    \"hint\": \"Dùng 'does' vì chủ ngữ 'My brother' là ngôi thứ ba số ít và 'usually' là dấu hiệu của thì Hiện tại đơn. Lỗi phổ biến là quên thêm 'es' hoặc dùng sai thì.\"\n  }\n]"
          }
        ],
        "role": "model"
      },
      "finishReason": "STOP",
      "index": 0
    }
  ],
  "usageMetadata": {
    "promptTokenCount": 855,
    "candidatesTokenCount": 216,
    "totalTokenCount": 1679,
    "cachedContentTokenCount": 568,
    "promptTokensDetails": [
      {
        "modality": "TEXT",
        "tokenCount": 855
      }
    ],
    "cacheTokensDetails": [
      {
        "modality": "TEXT",
        "tokenCount": 568
      }
    ],
    "thoughtsTokenCount": 608
  },
  "modelVersion": "gemini-2.5-flash",
  "responseId": "9o4YacDwJti0vr0PzqfuoQw"
}, indent=2)

def fake_request(method, path, request_dict, options = None):
    if request_dict['contents'][0]['parts'][0]['text'].startswith("You are an expert English grammar examiner"):
        ans = [
            HttpResponse(headers={}, body=body1),
            HttpResponse(headers={}, body=body2),
        ]
        return ans[random.randint(0, 1)]
    else:
        return HttpResponse(headers={}, body=body3)
    
def fake_call_genai_error(prompt: str,
    *,
    model: str | None = None,
    response_mime_type: Optional[str] = 'application/json',
    response_schema: Any | None = None,
    # Determinism controls (optional)
    temperature: Optional[float] = None,
    seed: Optional[int] = None):
    if response_schema != None:
        raise AttributeError("Simulated SDK AttributeError")
    else:
        return '[{"type": "mcq", "question": {"id": "ps_mcq_001", "prompt": "My brother usually _____ his homework after dinner.", "options": [{"id": "a", "label": "do"}, {"id": "b", "label": "does"}, {"id": "c", "label": "doing"}, {"id": "d", "label": "did"}]}, "correctOptionId": "b", "hint": "Dùng \'does\' vì chủ ngữ \'My brother\' là ngôi thứ ba số ít và \'usually\' là dấu hiệu của thì Hiện tại đơn. Lỗi phổ biến là quên thêm \'es\' hoặc dùng sai thì."}]'

@pytest.mark.usefixtures("setup_database", "seed_data")
class TestAi:

    def test_load_all_topic_displays(self):
        # Normal case
        res = (ai.load_all_topic_displays())
        assert type(res) == list
        assert type(res[0]) == str

        # Cached case
        assert ai.load_all_topic_displays() is not None

    def test_load_topic_map(self):
        # Normal case
        res = ai.load_topics_map()
        assert type(res) == dict
        assert len(list(res.keys())) > 0
        assert type(res[list(res.keys())[0]]) == list

        # Cached case
        assert ai.load_topics_map() is not None


    def test_build_label_prompt(self):
        prompt = ai._build_label_prompt("test", ai.load_topics_map())
        assert type(prompt) == str
    
    def test_classify_topics(self):
        with patch.object(BaseApiClient, "request", side_effect=fake_request):
            # 7 times to cover both mocked responses (2/128 chance to hit only one type of response)
            assert ai.classify_topic("What is Present Simple?") == "Present Simple"
            assert ai.classify_topic("What is Present Simple?") == "Present Simple"
            assert ai.classify_topic("What is Present Simple?") == "Present Simple"
            assert ai.classify_topic("What is Present Simple?") == "Present Simple"
            assert ai.classify_topic("What is Present Simple?") == "Present Simple"
            assert ai.classify_topic("What is Present Simple?") == "Present Simple"
            assert ai.classify_topic("What is Present Simple?") == "Present Simple"

    def test_build_locked_prompt_cot(self):
        prompt1 = ai.build_locked_prompt_cot("mcq", "Present Simple", "What is Present Simple?", 5)
        prompt2 = ai.build_locked_prompt_cot("mcq", "Simple", "What is Present Simple?", 5)

        assert "time markers;" not in prompt1
        assert "time markers;" in prompt2

    def test_build_locked_prompt(self):
        prompt1 = ai.build_locked_prompt("mcq", "Present Simple", "What is Present Simple?", 5, "minimal")
        prompt2 = ai.build_locked_prompt("mcq", "Simple", "What is Present Simple?", 5, "cot")

        assert "MINIMAL" in prompt1
        assert "time markers;" in prompt2
    
    def test_strip_code_fences(self):
        s1 = '```Something\n```'
        s2 = '```as```'
        s3 = '  abc   '
        s4 = ''
        s5 = 'asdfasdf'

        assert ai._strip_code_fences(s1) == ''
        assert ai._strip_code_fences(s2) == '```as'
        assert ai._strip_code_fences(s3) == 'abc'
        assert ai._strip_code_fences(s4) == ''
        assert ai._strip_code_fences(s5) == 'asdfasdf'

    def test_generate_exercises(self):
        with patch.object(BaseApiClient, "request", side_effect=fake_request):
            res = ai.generate_exercises_from_context(
                context_text="What is Present Simple?",
                hw_type="mcq",
            )

            assert (type(res) == dict)
            assert "items" in res
            assert res['topic'] == "Present Simple"

    def test_pick_schema(self):
        assert type(ai._pick_schema_and_hint('mcq')) == tuple
        assert type(ai._pick_schema_and_hint('fill')) == tuple
        assert type(ai._pick_schema_and_hint('random')) == tuple


    def test_generate_with_llm(self):
        with patch.object(BaseApiClient, "request", side_effect=fake_request):
            # full_prompt not None
            res1 = ai.generate_with_llm(
                post_text="What is Present Simple?",
                hw_type="mcq",
                full_prompt="You are an stupid.",
            )
            assert type(res1) == list
            
            # full_prompt None, no locked_topic
            with pytest.raises(ValueError):
                res2 = ai.generate_with_llm(
                    post_text="What is Present Simple?",
                    hw_type="mcq",
                )
            
            # full_prompt None, with minimal
            res2 = ai.generate_with_llm(
                post_text="What is Present Simple?",
                hw_type="mcq",
                locked_topic="Present Simple",
                mode="minimal"
            )
            assert type(res2) == list
            
            # full_prompt None, with cot
            res3 = ai.generate_with_llm(
                post_text="What is Present Simple?",
                hw_type="mcq",
                locked_topic="Present Simple",
            )
            assert type(res3) == list

            # trigger validation error
            with pytest.raises(ai.ValidationError):
                ai.generate_with_llm(
                    post_text="What is Present Simple?",
                    hw_type="mcq",
                    locked_topic="Simple",
                    full_prompt="You are an expert English grammar examiner"
                )
            
            # trigger SDK AttributeError
            with patch.object(ai, "_call_genai", fake_call_genai_error):
                res4 = ai.generate_with_llm(
                    post_text="What is Present Simple?",
                    hw_type="mcq",
                    locked_topic="Present Simple",
                )
                assert type(res4) == list