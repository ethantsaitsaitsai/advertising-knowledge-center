# Clarification Loop Resolution Summary

## Problem Statement

When users submit ambiguous queries (e.g., "悠遊卡 投遞的格式、成效"), the system entered an infinite loop between Supervisor and CampaignAgent:

```
Supervisor (iteration 1):
  "使用者想查詢悠遊卡相關的活動，但沒有明確指定是哪個活動。
   請根據使用者提供的資訊，進一步詢問使用者想查詢的具體活動名稱。"
  ↓
CampaignAgent:
  ❌ Executes SQL query (returns campaign_data, not clarification message)
  ↓
Supervisor (iteration 2):
  "使用者想查詢與「悠遊卡」相關的活動，但意圖不明確。
   [repeated instruction]"
  ↓
CampaignAgent:
  ❌ Executes SQL query again
  ↓
[Loop continues indefinitely]
```

**Root Cause**: CampaignAgent Router was checking only instruction text keywords for clarification detection, but not the `is_ambiguous` flag from IntentAnalyzer. When Supervisor sent clarification instructions but didn't include specific keywords, the Router would fall through and execute SQL instead of returning a clarification message.

---

## Solution Overview

Implemented a **3-layer clarification detection system** with redundancy:

```
Layer 1 (Keyword Detection)
  ↓
Layer 2 (Strong Indicators)
  ↓
Layer 3 (is_ambiguous Flag) ← CRITICAL, most reliable
  ↓
Router Decision: Clarification? → Return message (no SQL)
```

---

## Implementation Details

### 1. Added `is_ambiguous` Field to CampaignTask

**File**: `schemas/agent_tasks.py`

```python
class CampaignTask(BaseModel):
    ...
    is_ambiguous: Optional[bool] = Field(
        False,
        description="Whether the user intent is ambiguous and requires clarification (from IntentAnalyzer)."
    )
```

**Purpose**: Allow CampaignAgent Router to directly check if the user's intent is ambiguous without relying solely on instruction text parsing.

**Propagation Path**:
```
IntentAnalyzer
  (finds multiple search results)
  ↓
Sets: user_intent.is_ambiguous = True
  ↓
Supervisor (planner_node, line 68)
  (includes is_ambiguous in payload context)
  ↓
Supervisor (validator_node, lines 107-110)
  (passes to decision_payload)
  ↓
CampaignNode
  (receives in CampaignTask)
  ↓
CampaignRouter
  (checks flag and detects clarification)
```

---

### 2. Enhanced Router Clarification Detection

**File**: `nodes/campaign_subgraph/router.py` (lines 64-82)

```python
# LAYER 1: Original keyword detection
is_clarification_request = False

if task.instruction_text:
    instruction_lower = task.instruction_text.lower()

    # LAYER 1: Original keywords
    if any(keyword in instruction_lower
           for keyword in ["澄清", "clarify", "clarification", "選擇", "choose", "哪一個", "which one"]):
        is_clarification_request = True

    # LAYER 2: Strong clarification indicators (used by Supervisor)
    elif any(keyword in instruction_lower
             for keyword in ["詢問", "ask", "問", "list", "列出", "options", "哪一個", "which", "具體"]):
        is_clarification_request = True

# LAYER 3: CRITICAL - Check is_ambiguous flag (most reliable)
if hasattr(task, 'is_ambiguous') and task.is_ambiguous:
    print("DEBUG [CampaignRouter] is_ambiguous=True in task -> treating as clarification request")
    is_clarification_request = True
```

**Why 3 Layers?**
- **Layer 1 & 2**: Catch explicit clarification requests from instruction text
- **Layer 3**: Acts as safety net, catches ambiguous intent even if instruction text doesn't include specific keywords
- **Redundancy**: If any layer detects clarification, Router will handle it correctly

---

### 3. Propagate `is_ambiguous` Through Validator

**File**: `nodes/supervisor_subgraph/validator.py` (lines 107-110)

```python
# 【CRITICAL】Pass is_ambiguous flag from user_intent to task
# CampaignAgent Router needs to know if this is a clarification step
if user_intent:
    decision_payload["is_ambiguous"] = user_intent.is_ambiguous
```

**Why**: Ensures the flag flows through the entire chain:
```
IntentAnalyzer.is_ambiguous
  → (via state) →
Supervisor.user_intent.is_ambiguous
  → (via validator) →
CampaignTask.is_ambiguous
  → (via router) →
Router Detection
```

---

### 4. Add Debug Logging

**File**: `nodes/campaign_node_wrapper.py` (line 42)

```python
print(f"DEBUG [CampaignNode] is_ambiguous: {task.is_ambiguous}")
```

**Purpose**: Visibility into flag propagation for debugging

---

## Corrected Flow (After Fix)

```
User Input: "悠遊卡 投遞的格式、成效"
  ↓
[1] IntentAnalyzer
  ├─ search_ambiguous_term("悠遊卡")
  ├─ Returns: 10 results
  ├─ Detects: Multiple results (Case C)
  ├─ Sets: is_ambiguous = True
  └─ Message: "您好！根據您提到的「悠遊卡」，我在資料庫中找到了幾個相關項目..."
  ↓
[2] Supervisor (Planning)
  ├─ Sees: user_intent.is_ambiguous = True
  ├─ Decision: Route to CampaignAgent for clarification
  ├─ Creates: CampaignTask with is_ambiguous = True
  └─ Instruction: "使用者想查詢悠遊卡相關的活動，但意圖不明確。請詢問使用者..."
  ↓
[3] CampaignAgent Router ← THE FIX APPLIES HERE
  ├─ Receives: task.is_ambiguous = True
  ├─ Layer 3 Detection: hasattr(task, 'is_ambiguous') and task.is_ambiguous
  ├─ Result: is_clarification_request = True ✅
  ├─ Decision: Don't execute SQL, return clarification
  └─ Return: {"next_action": "finish", "final_response": task.instruction_text}
  ↓
[4] ResponseSynthesizer
  ├─ Receives: CampaignAgent message (clarification)
  ├─ Detects: Contains "澄清"/"clarify"/keywords
  ├─ Sets: clarification_pending = True
  └─ Shows: Clarification message to user (ONCE)
  ↓
[5] User Responds: "我要查詢品牌部分的悠遊卡"
  ↓
[6] Supervisor (iteration 2)
  ├─ Detects: clarification_pending = True AND new HumanMessage
  ├─ Routes to: IntentAnalyzer for re-analysis (not CampaignAgent again)
  └─ Clears: clarification_pending = False
  ↓
[7] IntentAnalyzer (re-run)
  ├─ Parses: "品牌部分的悠遊卡"
  ├─ Searches: confirms single result or clear entity
  ├─ Sets: is_ambiguous = False ✅
  └─ Creates: New UserIntent with resolved entity
  ↓
[8] Supervisor (iteration 3)
  ├─ Sees: user_intent.is_ambiguous = False
  ├─ Decision: Normal SQL execution
  └─ Routes to: CampaignAgent with is_ambiguous = False
  ↓
[9] CampaignAgent Router (SQL execution)
  ├─ Receives: task.is_ambiguous = False
  ├─ Layer 3: is_ambiguous=False → NOT a clarification
  ├─ Proceeds: generate_sql → execute_sql
  └─ Returns: Data ✅
  ↓
[10] Final Output: Query results for "品牌部分的悠遊卡" ✅

NO INFINITE LOOP ✅
CLARIFICATION SHOWN ONCE ✅
```

---

## Key Fixes at Each Layer

| Component | Issue | Fix | Location |
|-----------|-------|-----|----------|
| **IntentAnalyzer** | Not setting is_ambiguous correctly | Guidance in prompt (Case A/B/C logic) | prompts/intent_analyzer_prompt.py:70-99 |
| **Supervisor** | Not propagating is_ambiguous | Pass flag through payload | nodes/supervisor_subgraph/validator.py:107-110 |
| **CampaignTask** | No is_ambiguous field | Added field | schemas/agent_tasks.py:36-39 |
| **CampaignRouter** | Only checking keywords | Added Layer 3 (flag check) | nodes/campaign_subgraph/router.py:79-82 |
| **CampaignNode** | No visibility | Debug logging | nodes/campaign_node_wrapper.py:42 |

---

## Verification Checklist

Run this test to verify the fix works:

### Test Case 1: Ambiguous Query Detection

```bash
Input: "悠遊卡 成效"  (ambiguous - multiple results expected)

Expected Output:
  您好！根據您提到的「悠遊卡」，我在資料庫中找到了幾個相關項目：
  * [Option 1]
  * [Option 2]
  * ...
  請問您是想查詢哪一個呢？

Expected Debug Logs:
  ✅ DEBUG [IntentAnalyzer] Final Structured Intent: UserIntent(...is_ambiguous=True...)
  ✅ DEBUG [CampaignNode] is_ambiguous: True
  ✅ DEBUG [CampaignRouter] is_ambiguous=True in task -> treating as clarification request
  ✅ DEBUG [CampaignRouter] Logic: Clarification request detected -> FINISH

NOT Expected (if seen, it's a bug):
  ❌ DEBUG [CampaignExecutor] Executing: SELECT ...
```

### Test Case 2: Clarification Response & Data Retrieval

```bash
Input (User): "品牌部分的悠遊卡"  (clarification response)

Expected Flow:
  1. IntentAnalyzer re-runs (because clarification_pending=True + new HumanMessage)
  2. Resolves entity to single match (is_ambiguous=False)
  3. Supervisor routes to CampaignAgent with is_ambiguous=False
  4. CampaignRouter checks: is_ambiguous=False → NOT clarification
  5. Executes SQL and returns data

Expected Debug Logs:
  ✅ DEBUG [IntentAnalyzer] Clarification response detected
  ✅ DEBUG [SupervisorWrapper] Clarification response detected. Routing to IntentAnalyzer...
  ✅ DEBUG [CampaignRouter] Logic: Data found -> FINISH

Expected Output:
  [Query results for 品牌部分的悠遊卡]
```

### Test Case 3: No Infinite Loop

```
CRITICAL: No repeated Supervisor-CampaignAgent cycles
✅ Clarification shown ONCE
✅ User response processed once
✅ Data returned (not repeated clarification)
```

---

## Related Code Sections

### IntentAnalyzer Prompt (Rule-Based Entity Matching)
**File**: `prompts/intent_analyzer_prompt.py:70-99`
- Case A: 0 results → is_ambiguous=True
- Case B: 1 exact match (and only result) → is_ambiguous=False
- Case C: Multiple results → is_ambiguous=True (ALWAYS)

### Supervisor Planner (Including Context)
**File**: `nodes/supervisor_subgraph/planner.py:68`
- Line 68: `payload_context["is_ambiguous"] = user_intent.is_ambiguous`
- Ensures LLM sees the ambiguity flag when making decisions

### Supervisor Validator (Propagating Flag)
**File**: `nodes/supervisor_subgraph/validator.py:107-110`
- Passes is_ambiguous to decision_payload for all agent types

### Supervisor Wrapper (Loop Prevention)
**File**: `nodes/supervisor.py:15-22`
- Detects CampaignAgent message and skips re-looping Supervisor
- Crucial to prevent Supervisor from processing clarification as new task

### Campaign Node Wrapper (Message Handling)
**File**: `nodes/campaign_node_wrapper.py:78-80`
- Detects clarification keywords and sets clarification_pending=True
- Ensures next iteration doesn't loop back through Supervisor

---

## Commits

| Commit | Change |
|--------|--------|
| **bd6f320** | Fix: Prevent infinite clarification loop by detecting is_ambiguous flag |
| **247288d** | Debug: Add is_ambiguous logging to CampaignNode |
| **ea6243d** | Docs: Add comprehensive clarification loop fix documentation |
| **34925a1** | Test: Add comprehensive clarification loop fix verification checklist |

---

## Performance Impact

**Positive**:
- ✅ Prevents infinite loops (saves computational resources)
- ✅ Faster user feedback (clarification shown immediately)
- ✅ Better UX (no repeated messages)
- ✅ Reduced API calls (no unnecessary SQL re-execution)

**Overhead**:
- Minimal: Simple flag check in Router (negligible performance cost)
- Flag propagation adds ~1 field to 3-4 payloads (insignificant memory)

---

## Design Principles Applied

1. **Layered Defense**: 3-layer detection ensures robustness
2. **Explicit Signaling**: is_ambiguous flag is unambiguous (not string-matching)
3. **Traceability**: Debug logs show flag propagation path
4. **Backward Compatible**: All changes are additive, no breaking changes
5. **Separation of Concerns**: Each layer has clear responsibility
   - IntentAnalyzer: Detect ambiguity
   - Supervisor: Route based on ambiguity
   - Router: Honor the ambiguity signal
   - ResponseSynthesizer: Show clarification appropriately

---

## Testing Instructions

1. **Unit Level**: Verify is_ambiguous field serialization in CampaignTask
2. **Integration Level**: Run test cases (see above) with debug logs enabled
3. **End-to-End Level**: Manual testing with ambiguous queries via CLI (`uv run run.py`)
4. **Regression Level**: Ensure non-ambiguous queries still work normally

---

## Future Improvements

1. Add metrics/monitoring for clarification frequency
2. Implement user feedback on clarification quality
3. Consider caching ambiguous entity lists for faster re-resolution
4. Add confidence scores to search results for better disambiguation

---

## Summary

The clarification loop fix implements a **robust, multi-layer detection system** that:
- ✅ Prevents infinite loops via is_ambiguous flag
- ✅ Provides redundancy with 3-layer detection
- ✅ Maintains clarity through explicit state propagation
- ✅ Enables easy debugging with comprehensive logging
- ✅ Follows clean architecture principles

The fix is **minimal, focused, and effective** - adding only necessary code to solve the specific problem without over-engineering or introducing unnecessary complexity.
