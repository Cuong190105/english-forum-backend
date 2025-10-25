# AI Generation Testing Plan

## Overview
This document outlines the testing strategy for the AI generation endpoints in the English Forum backend.

## Current Issues to Address

### 1. Import Mismatch
- **File**: [`routers/ai.py`](routers/ai.py)
- **Problem**: Line 9 imports `generate_exercises_from_context` but the actual function is named `generate_exercises_from_context`

### 2. Function Name Inconsistencies
- Multiple spelling variations throughout the codebase

## Test Scenarios

### Scenario 1: Topic Classification Testing

#### Test Case 1.1: Present Simple Classification
```json
{
  "context_text": "I usually wake up at 6 AM every morning. Then I brush my teeth and have breakfast."

#### Expected Output:
```json
{
  "topic": "Present Simple",
  "items": [...]
}
```

### Scenario 2: MCQ Generation Testing

#### Test Case 2.1: Basic MCQ Generation
- **Endpoint**: `/ai/generate-from-text`
- **Input**:
```json
{
  "context_text": "Every day, I go to school by bus.",
  "type": "mcq",
  "num_items": 3,
  "mode": "cot"
```

#### Expected Schema:
```json
{
  "topic": "Present Simple",
  "items": [
    {
      "type": "mcq",
      "question": {
        "id": "item_001",
        "prompt": "She _____ to school every day.",
  "options": [
    {"id": "a", "label": "goes"},
    {"id": "b", "label": "go"},
    {"id": "c", "label": "is going"},
    {"id": "d", "label": "went"}
  ],
  "correctOptionId": "b",
  "hint": "Dùng 'go' cho chủ ngữ 'she' với thì hiện tại đơn."
}
```

### Scenario 3: Fill-in-the-Blank Testing

#### Test Case 3.1: Basic Fill Generation
- **Input**:
```json
{
  "context_text": "Yesterday, I visited my grandmother.",
  "type": "fill",
  "num_items": 2
```

## Testing Procedure

### Step 1: Environment Setup
1. Verify API keys are configured in `.env`
2. Ensure database is running
3. Start FastAPI server

### Step 2: Manual API Testing

#### Test Script Template:
```python
import requests
import json

BASE_URL = "http://localhost:8000"

# Test 1: Generate from text (MCQ)
def test_generate_from_text_mcq():
    payload = {
        "context_text": "I have lived in Hanoi for five years.",
  "type": "mcq",
  "num_items": 2,
  "mode": "cot"
}

response = requests.post(f"{BASE_URL}/ai/generate-from-text", json=payload)
print(f"Status: {response.status_code}")
print(f"Response: {response.json()}")
```

### Step 3: Validation Checklist

- [ ] Response status code is 200
- [ ] Response matches expected schema
- [ ] Generated items are grammatically correct
- **Topic-specific rules** should be enforced
- **Vietnamese hints** should be concise and helpful

## Expected Test Results

### Success Criteria:
1. Topic classification accuracy > 80%
2. Generated items are unambiguous
3. Error handling works for invalid inputs

## Error Cases to Test

1. **Empty context text**
2. **Invalid type parameter**
3. **Number of items out of range**
4. **Missing required fields**

## Implementation Priority

### High Priority (Fix Before Testing):
1. Import statement fixes
2. Function name standardization

### Medium Priority:
1. Database connection completion
2. Configuration validation

## Recommendations for Testing

### 1. Create Test Data
- Sample posts in database
- Various context text scenarios

### 2. Automated Test Suite
- Unit tests for `classify_topic` function
- Integration tests for full workflow

### 3. Monitoring & Logging
- Add debug logging for AI generation process
- Monitor API response times
- Track generation success rates