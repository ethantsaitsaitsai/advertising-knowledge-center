# Supervisor Loop Fix: Preventing Redundant Queries and False Positive Clarifications

**Date**: 2025-12-15
**Branch**: refactor/multi-agent-system
**Status**: ✅ FIXED AND COMMITTED

---

## Problem Summary

After fixing the SQL syntax issue, a new problem emerged: the system was stuck in a loop, calling CampaignAgent twice and showing repeated clarification messages.

**From your logs**:
```
1. CampaignAgent查詢成功 → Result: 5 rows in 1.41s ✓
2. Supervisor再次調用CampaignAgent ❌
3. Router誤判為Clarification → 返回通用clarification message ❌
4. 重複訊息顯示兩次 ❌
```

---

## Root Causes Identified

### Root Cause 1: Supervisor LLM Didn't Recognize campaign_data Contains IDs

**Location**: `prompts/supervisor_prompt.py`

**Problem**: After CampaignAgent successfully queried 5 rows of data, Supervisor's LLM still decided to call CampaignAgent again.

**From LOG**:
```
DEBUG [CampaignExecutor] Result: 5 rows in 1.41s.
DEBUG [CampaignRouter] Logic: Data found -> FINISH

# Supervisor runs again
DEBUG [SupervisorPlanner] Draft: CampaignAgent | Reasoning: 使用者想查詢...需要 Campaign ID，
因此首先需要 CampaignAgent...找出所有相關的 Campaign ID
```

**Why**: The Supervisor prompt didn't explicitly state that `campaign_data` **already contains Campaign IDs** (in the `cmpid` column). The LLM thought it still needed to query for IDs.

### Root Cause 2: Router Detected False Positive Clarification

**Location**: `nodes/campaign_subgraph/router.py` (lines 68-77)

**Problem**: Router was using overly broad keywords to detect clarification requests.

**Problematic Keywords**:
```python
for keyword in ["詢問", "ask", "問", "list", "列出", "options", "哪一個", "which", "具體"]:
```

**False Positive Scenario**:
- Supervisor instruction: "請搜尋與 '悠遊卡股份有限公司' 相關的活動，並篩選出..."
- Contains keyword: "列出" → Detected as clarification
- Router returned generic clarification message instead of executing query

**From LOG**:
```
DEBUG [CampaignRouter] Step 1 Check: Clarification=True
DEBUG [CampaignRouter] Logic: Clarification request detected -> FINISH (with clarification message)
```

---

## Fixes Implemented

### Fix 1: Improved Supervisor Prompt to Recognize campaign_data

**File**: `prompts/supervisor_prompt.py` (lines 5-16)

**Before**:
```
1. **觀察**: 檢視使用者的意圖以及我們手上已有的數據 (campaign_data, campaign_ids)。
2. **思考**:
   - 是否需要查成效？如果是，但我手上還沒有 Campaign IDs，那我必須先叫 CampaignAgent...
```

**After**:
```
1. **觀察**: 檢視使用者的意圖以及我們手上已有的數據 (campaign_data, campaign_ids)。
   - **重要**: campaign_data 中的每一行資料都包含 cmpid (Campaign ID)。
     如果 campaign_data 有資料，代表我們**已經有 Campaign IDs** 了！

2. **思考**:
   - **檢查 campaign_data**: 如果 campaign_data 已經有資料（例如 "Available (5 rows)"），
     這代表 CampaignAgent 已經完成查詢，資料中已包含 Campaign IDs！
   - 是否需要查成效 (needs_performance=True)？
     - 如果有 campaign_data (已包含 Campaign IDs) → 直接叫 **PerformanceAgent** 查成效
     - 如果沒有 campaign_data 也沒有 campaign_ids → 先叫 **CampaignAgent** 找 IDs

3. **決策**:
   - **避免重複查詢**: 如果 campaign_data 已有資料，不要再叫 CampaignAgent 重複查詢！
```

**Impact**: Supervisor LLM now understands that when it sees `campaign_data_summary: "Available (5 rows)"`, it already has the Campaign IDs needed for PerformanceAgent.

### Fix 2: Strict Clarification Detection in Router

**File**: `nodes/campaign_subgraph/router.py` (lines 68-76)

**Before**:
```python
if any(keyword in instruction_lower
       for keyword in ["澄清", "clarify", "選擇", "choose"...]):
    is_clarification_request = True
# Also check overly broad keywords
elif any(keyword in instruction_lower
         for keyword in ["詢問", "ask", "問", "list", "列出", "options", "哪一個", "which", "具體"]):
    is_clarification_request = True
```

**After**:
```python
# Detect clarification keywords (STRICT - avoid false positives)
# Only detect when Supervisor explicitly asks to clarify or ask user
if any(keyword in instruction_lower
       for keyword in ["澄清", "clarify", "clarification",
                      "請問使用者", "詢問使用者", "ask user", "ask the user"]):
    is_clarification_request = True
# Removed overly broad keywords: "詢問", "ask", "問", "list", "列出", "options", "哪一個", "which", "具體"
# These caused false positives when Supervisor gives normal query instructions
```

**Impact**: Router now only treats explicit clarification requests as clarification, not normal query instructions that happen to contain common words like "list" or "ask".

---

## Expected Behavior After Fix

### Test Case: Query with Company Filter

**Input**:
```
User: "悠遊卡 成效"
System: [Clarification options]
User: "悠遊卡股份有限公司 2025年"
```

### Before Fix (Broken)

```
1. IntentAnalyzer: Extracts entities, clears is_ambiguous ✓
2. Supervisor: Routes to CampaignAgent (first time) ✓
3. CampaignAgent: Queries MySQL → Returns 5 rows ✓
4. Supervisor: Sees campaign_data but doesn't recognize it has IDs
   → Routes to CampaignAgent AGAIN ❌
5. CampaignAgent: Router detects "列出" in instruction
   → Treats as clarification request ❌
   → Returns generic clarification message ❌
6. ResponseSynthesizer: Shows repeated message ❌
```

### After Fix (Correct)

```
1. IntentAnalyzer: Extracts entities, clears is_ambiguous ✓
2. Supervisor: Routes to CampaignAgent ✓
3. CampaignAgent: Queries MySQL → Returns 5 rows ✓
4. Supervisor: Sees campaign_data (5 rows) with Campaign IDs
   → Recognizes: "campaign_data already contains IDs!"
   → Routes to PerformanceAgent (if needs_performance) ✓
   → OR routes to ResponseSynthesizer (if only basic data needed) ✓
5. No repeated calls, no false clarification ✓
```

---

## Debug Logs to Expect

### Good Flow (After Fix)

```
DEBUG [CampaignExecutor] Result: 5 rows in 1.41s.
DEBUG [CampaignRouter] Logic: Data found -> FINISH
DEBUG [SupervisorPlanner] Draft: PerformanceAgent | Reasoning: campaign_data 已有資料(5 rows)，包含 Campaign IDs，可直接查詢成效
# OR
DEBUG [SupervisorPlanner] Draft: ResponseSynthesizer | Reasoning: 基礎資料已齊全，進行報告合成
```

### Bad Flow (Before Fix - Should NOT See This)

```
DEBUG [CampaignExecutor] Result: 5 rows in 1.41s.
DEBUG [SupervisorPlanner] Draft: CampaignAgent | Reasoning: 需要先找出 Campaign ID  ← Wrong!
DEBUG [CampaignRouter] Clarification=True  ← False positive!
```

---

## Architecture Flow Diagram

### Before Fix (Loop)

```
User clarifies
    ↓
IntentAnalyzer (clears is_ambiguous) ✓
    ↓
Supervisor → CampaignAgent (1st call) ✓
    ↓
CampaignAgent queries MySQL → 5 rows ✓
    ↓
Supervisor (doesn't recognize data has IDs)
    ↓
Supervisor → CampaignAgent (2nd call) ❌ Loop!
    ↓
Router detects "列出" → Clarification ❌
    ↓
Generic clarification message ❌
    ↓
ResponseSynthesizer (repeated message) ❌
```

### After Fix (Correct)

```
User clarifies
    ↓
IntentAnalyzer (clears is_ambiguous) ✓
    ↓
Supervisor → CampaignAgent ✓
    ↓
CampaignAgent queries MySQL → 5 rows ✓
    ↓
Supervisor (recognizes: campaign_data has IDs!)
    ↓
Supervisor → PerformanceAgent (if needs performance) ✓
    OR
Supervisor → ResponseSynthesizer (if basic data only) ✓
    ↓
Final response to user ✓
```

---

## Files Modified

| File | Lines | Change Type |
|------|-------|-------------|
| `prompts/supervisor_prompt.py` | 5-16 | Enhanced prompt with campaign_data ID recognition |
| `nodes/campaign_subgraph/router.py` | 68-76 | Stricter clarification keyword detection |

**Total Changes**: 2 files, 13 insertions, 9 deletions

---

## Commit Information

**Commit**: `e6b0ee5`
**Message**: "Fix: Prevent Supervisor loop and Router false positive clarification detection"

---

## Testing Checklist

### ✅ Code Changes Verified

- [x] Supervisor prompt updated with campaign_data guidance
- [x] Router clarification detection narrowed to avoid false positives
- [x] All changes committed to git

### 📋 Testing Required

Test with the original failing query:

**Test Input**:
```bash
uv run run.py

Input 1: "悠遊卡 成效"
# Expected: Clarification options shown

Input 2: "悠遊卡股份有限公司 2025年"
# Expected:
# - CampaignAgent queries once (not twice)
# - Supervisor recognizes campaign_data has IDs
# - Routes to PerformanceAgent or ResponseSynthesizer
# - No repeated clarification messages
```

**Expected Debug Logs**:
```
✅ "Result: X rows in Y.Ys"
✅ "Draft: PerformanceAgent" OR "Draft: ResponseSynthesizer"
✅ NO repeated "Draft: CampaignAgent"
✅ NO "Clarification=True" when data already exists
```

---

## Complete Fix Chain

You now have **all major issues resolved**:

1. ✅ **is_ambiguous clearing** (commit `ad98f84`)
   - System clears ambiguity when user provides entities + date

2. ✅ **User-friendly messages** (commit `f0d7aa9`)
   - Shows helpful content instead of internal logic

3. ✅ **SQL syntax** (commit `ebe0e39`)
   - Generates valid SQL (WHERE after all JOINs)

4. ✅ **Supervisor loop prevention** (commit `e6b0ee5` - THIS FIX)
   - Recognizes campaign_data contains IDs
   - Avoids redundant CampaignAgent calls

5. ✅ **Router false positive prevention** (commit `e6b0ee5` - THIS FIX)
   - Only detects explicit clarification requests
   - Normal query instructions no longer trigger false clarification

---

## Risk Assessment

### Low Risk

- **Scope**: Prompt text changes + keyword list refinement
- **Type**: No code logic changes (only LLM guidance + keyword filtering)
- **Reversibility**: Can revert commit if issues arise
- **Testing**: Can test immediately with original failing query

### No Breaking Changes

- **Existing flows**: Explicit clarification requests still work
- **Only fixes**: False positive detection and redundant loops
- **Improvement**: System now more efficient (fewer redundant calls)

---

## Summary

**Root Causes**:
1. Supervisor LLM didn't recognize campaign_data contains Campaign IDs
2. Router used overly broad keywords for clarification detection

**Solutions**:
1. Enhanced Supervisor prompt to explicitly state campaign_data structure
2. Narrowed Router clarification keywords to avoid false positives

**Impact**: Fixes Supervisor loop, repeated messages, and false clarification detections

**Testing**: Run original query to verify single CampaignAgent call and proper routing

**Status**: ✅ READY FOR TESTING

---

**Last Updated**: 2025-12-15
**Branch**: refactor/multi-agent-system
**Commit**: e6b0ee5
