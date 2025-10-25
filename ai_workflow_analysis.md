# AI Workflow Analysis & Testing Plan

## Current Architecture Issues Identified

### Critical Issues:

1. **Import Mismatch**: [`routers/ai.py:9`](routers/ai.py:9) imports `generate_exercises_from_context` but the utility file has `generate_exercises_from_context` (spelling inconsistency)
2. **Function Name Typo**: [`utilities/ai_generator_LLM_Clone.py:738`](utilities/ai_generator_LLM_Clone.py:738)
3. **Database Connection**: Incomplete configuration in [`database/database.py`](database/database.py) and [`configs/config_db.py`](configs/config_db.py)

## Current Workflow Analysis

### Endpoint 1: `/ai/generate`
- **Purpose**: Generate exercises from existing post content
- **Workflow**:
  1. Receive `post_id`, `type`, `num_items`
  2. Query database for post content
  3. Call `llm_generate_homework` function
  4. Return generated items

### Endpoint 2: `/ai/generate-from-text` 
- **Purpose**: Generate exercises from raw context text
- **Workflow**:
  1. Receive `context_text`, `type`, `num_items`, `mode`
  2. Call `generate_exercises_from_context` function
  3. Return topic and items

## Required Fixes

### Phase 1: Critical Code Fixes
1. Fix import statement in [`routers/ai.py`](routers/ai.py)
3. Fix database connection configuration
4. Verify all function names match

### Phase 2: Testing Strategy

#### Test Cases for Topic Classification:

1. **Simple Present Tense Context**:
   - Input: "I usually go to school by bus every day."
  - Expected: "Present Simple"

2. **Past Tense Context**:
   - Input: "Yesterday, I visited my grandmother in the countryside."
  - Expected: "Past Simple"

3. **Conditional Context**:
   - Input: "If I had more time, I would learn another language."
  - Expected: "Second Conditional"

#### Test Cases for Generation:

1. **MCQ Generation**:
   - Type: "mcq"
   - Context: "She has lived in Hanoi for five years now."
  - Expected: "Present Perfect"

## Testing Methodology

### Manual API Testing Steps:

1. **Start Server**: Run the FastAPI application
2. **Test Endpoint 1**: Generate from post ID
3. **Test Endpoint 2**: Generate from text context
4. **Validate Schema**: Ensure output matches expected JSON schema
5. **Error Handling**: Test with invalid inputs

### Automated Testing (Future):

1. Unit tests for classification function
2. Integration tests for full workflow
3. Performance tests for API response times

## Recommendations

1. **Immediate**: Fix import mismatches and function names
2. **Short-term**: Complete database configuration
3. **Long-term**: Add comprehensive test suite

## Next Steps

1. Switch to Code mode to implement fixes
2. Create test scripts
3. Execute testing plan
4. Document results and improvements