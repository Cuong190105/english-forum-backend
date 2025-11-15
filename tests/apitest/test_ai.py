import json
from typing import Any, Dict, Optional
from unittest.mock import patch
import pytest
from google.genai.types import HttpResponse
from google.genai._api_client import BaseApiClient

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
    print("Fake request")
    if request_dict['contents'][0]['parts'][0]['text'].startswith("You are an expert English grammar examiner"):
        return HttpResponse(headers={}, body=body1)
    else:
        return HttpResponse(headers={}, body=body3)
    
def fake_generate_exercises_from_context(
    context_text: str,
    hw_type: str,
    num_items: int = 1,
    *,
    mode: str = 'cot',
    temperature: Optional[float] = None,
    seed: Optional[int] = 0,
) -> Dict[str, Any]:
    print("Triggered")
    if context_text == "Happy birthday":
        raise Exception("Simulated LLM generation error")
    return {"topic": "OK", "items": []}

@pytest.mark.usefixtures("setup_database", "seed_data")
class TestAi:
    
    @pytest.mark.asyncio
    async def test_get(self, async_client):
        data = {
            'context_text': 'My brother usually _____ his homework after dinner.',
            'type': 'mcq',
            'num_items': 1,
            'mode': 'cot',
        }
        with patch.object(BaseApiClient, "request", side_effect=fake_request):
            # Unauthorized
            res = await async_client.post("/ai/generate-from-text")
            assert res.status_code == 401

            # No data
            res = await async_client.post("/ai/generate-from-text", headers={"Authorization": "Bearer 1"})
            assert res.status_code == 422

            # Normal
            res = await async_client.post("/ai/generate-from-text", headers={"Authorization": "Bearer 1"}, json=data,)
            assert res.status_code == 200
            
            # Fault data
            data["context_text"] = "   "
            res = await async_client.post("/ai/generate-from-text", headers={"Authorization": "Bearer 1"}, json=data,)
            assert res.status_code == 400

            