# AI Generation Test Procedures

## Overview
This document provides step-by-step procedures for testing the AI generation endpoints.

## Pre-requisites

### Environment Setup:
1. Database running on localhost:3306
2. FastAPI server running on localhost:8000
3. Valid API keys configured in `.env`

## Test Procedure 1: Topic Classification

### Step 1: Prepare Test Cases

**Test Case 1.1: Present Simple
```json
{
  "context_text": "I usually drink coffee in the morning before going to work."
}

### Step 2: Execute Classification Tests

#### Manual API Call:
```bash
curl -X POST "http://localhost:8000/ai/generate-from-text" \
  -H "Content-Type: application/json" \
  -d '{
    "context_text": "She works in an office from 9 AM to 5 PM, Monday through Friday."
}

#### Expected Response:
```json
{
  "topic": "Present Simple",
  "items": [...]
}
```

### Step 3: Validate Results

**Validation Criteria:**
1. Topic matches expected grammar concept
2. Response schema is correct
3. No errors in processing

## Test Procedure 2: MCQ Generation

### Step 1: Prepare Test Input
```json
{
  "context_text": "I have been studying English for three years.",
  "type": "mcq",
  "num_items": 2,
  "mode": "cot"
}

### Step 2: Execute MCQ Test

**Sample Request:**
```python
import requests

url = "http://localhost:8000/ai/generate-from-text"
headers = {"Content-Type": "application/json"}
data = {
    "context_text": "Yesterday, I went to the market and bought some fruits.",
  "type": "mcq",
  "num_items": 2,
  "mode": "cot"
}

response = requests.post(url, json=data, headers=headers)
```

**Expected Response Schema:**
```json
{
  "topic": "string",
  "items": [
    {
      "type": "mcq",
      "question": {
        "id": "string",
        "prompt": "string",
        "options": [
          {"id": "a", "label": "string"},
          {"id": "b", "label": "string"},
          {"id": "c", "label": "string"},
          {"id": "d", "label": "string"}
      ],
      "correctOptionId": "string",
      "hint": "string"
    }
  ]
}
```

## Test Procedure 3: Fill-in-the-Blank Generation

### Step 1: Prepare Test Input
```json
{
  "context_text": "If I had more money, I would travel around the world.",
  "type": "fill",
  "num_items": 1
}
```

### Step 2: Execute Fill Test

**Validation Points:**
1. Exactly one "_____" in each prompt
2. Clear answer format
3. Vietnamese hints are helpful

## Specific Test Cases

### Case A: Business English Context
```json
{
  "context_text": "Our company plans to launch a new product next quarter.",
  "type": "fill",
  "num_items": 1
}
```

## Error Testing

### Test Case 4.1: Empty Context Text
```json
{
  "context_text": "",
  "type": "mcq",
  "num_items": 1
}
```

## Expected Success Metrics

### Topic Classification:
- Accuracy: >80%
- Response time: <5 seconds

### Exercise Generation:
- Schema validation: 100%
- Grammatical correctness: >90%

### Error Handling:
- Appropriate status codes for invalid inputs
- Clear error messages in response

## Troubleshooting Guide

### Common Issues:

1. **Import Errors**: Function name mismatches between files
2. **API Key Issues**: Verify `.env` configuration
3. **Database Connection**: Ensure MySQL is running
4. **Response Schema**: Verify against Pydantic models

### Debug Steps:

1. Check server logs for errors
2. Verify API key validity
3. Test with minimal context first

## Next Steps

After completing manual testing:

1. **Automate Tests**: Create pytest scripts
2. **Performance Monitoring**: Track response times
3. **Quality Assurance**: Manual review of generated content