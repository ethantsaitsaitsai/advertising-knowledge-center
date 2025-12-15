# Empty SQL Results & Clarification Message Fix

## Problem Found in Testing

After the user provides complete information (entity + date), the system was:
1. Executing SQL query ✓
2. Getting empty results ✓
3. But showing **"No data"** message ❌
4. Then asking for clarification on information **already provided** ❌
5. Repeating the same clarification message multiple times ❌

### Example Conversation

```
User Input 1: "悠遊卡 投遞的格式、成效、數據鎖定 格式投資金額"
System: [Shows search results] ✓

User Input 2: "悠遊卡股份有限公司，時間2025年"
System: "No data"  ← ❌ User already specified entity + date!
System: "我需要您提供更多信息..." ← ❌ But user DID provide info!
System: [REPEATED message] ← ❌ Why repeat?
```

---

## Root Cause Analysis

### Why "No data" Instead of Clarification?

**Flow**:
1. User responds with entity "悠遊卡股份有限公司" + date "2025年"
2. IntentAnalyzer re-runs → Extracts entity + date ✓
3. Supervisor routes to CampaignAgent
4. CampaignAgent Router checks: "Is this clarification request?"
   - Checks: `is_ambiguous` flag
   - Checks: Keywords in instruction text
   - **But doesn't check**: Whether SQL was just executed!
5. CampaignAgent **generates and executes SQL** → Gets 0 rows
6. Router detects empty results (lines 217-253)
7. Router should return clarification message
8. **BUT**: Before my fix, the logic was:
   ```python
   if executed_but_empty:
       if search_results is not None:  # ← This check!
           # Ask for clarification
       else:
           # Try to search again
   ```
9. **Problem**: User directly specified entity, so `search_results = None`!
10. Router took the `else` branch and tried to search again
11. This triggered **another** clarification detection
12. Result: Repeated clarification messages!

### Why Repeated Messages?

The loop was:
```
Step 1: SQL empty, search_results=None → Try search_entity
Step 2: Search entity → Router detects clarification needed (because searching is ambiguous)
Step 3: Return clarification message
Step 4: Supervisor wraps message, routes to ResponseSynthesizer
Step 5: ResponseSynthesizer sees campaign_data is empty, returns "No data" instead of using message!
```

Then the flow repeats, creating the repeated messages.

---

## Solution Implemented

### Fix 1: Simplify Router Empty SQL Logic (router.py, lines 212-239)

**Before**:
```python
if executed_but_empty:
    if search_results is not None:
        # Ask about filters
    else:
        # Try searching again  ← ❌ PROBLEM: Creates loop
```

**After**:
```python
if executed_but_empty:
    # ALWAYS ask for filter clarification
    # Don't try to search again - user already provided entity!
    clarification_msg = (
        "我找到了相關的項目，但根據您提供的條件（例如時間範圍）查無數據。\n\n"
        "這可能是因為：\n"
        "- 該活動/公司在您指定的時間範圍內沒有數據\n"
        "- 您指定的指標可能在該期間沒有記錄\n"
        "- 數據庫中該條件組合不存在\n\n"
        "請嘗試：\n"
        "- 調整時間範圍（例如：改為上個月或去年同期）\n"
        "- 確認指定的實體名稱是否正確\n"
        "- 嘗試查詢其他指標\n\n"
        "您想調整查詢條件嗎？"
    )
    return {"next_action": "finish", "final_response": clarification_msg}
```

**Why This Works**:
- ✅ Acknowledges that entity was found
- ✅ Explains why there's no data (date range, metrics, etc.)
- ✅ Suggests concrete next steps
- ✅ Doesn't ask for information already provided
- ✅ Breaks the search loop

### Fix 2: Better Empty Data Handling in ResponseSynthesizer (response_synthesizer.py)

**Added check for empty campaign_data** (lines 102-118):
```python
campaign_data = state.get("campaign_data")
if campaign_data and not campaign_data.get("data"):
    # Data exists but is empty
    # Show clarification instead of "No data"
    return {
        "messages": [AIMessage(content=(
            "根據您的查詢條件，我暫時找不到相符的數據。\n\n"
            "這可能是因為：\n"
            "- 時間範圍內沒有相關數據\n"
            "- 實體名稱或條件組合不存在\n\n"
            "您想調整查詢條件或嘗試其他時間範圍嗎？"
        ))]
    }
```

**Also changed final empty df check** (lines 158-169):
```python
if df.empty:
    # Instead of "查無資料"
    # Show helpful clarification message
    return {
        "messages": [AIMessage(content=(
            "根據您的查詢條件，我暫時找不到相符的數據。\n\n"
            "請嘗試：\n"
            "- 調整時間範圍（例如：查詢其他月份或年份）\n"
            "- 確認實體名稱是否正確\n"
            "- 嘗試查詢其他指標\n\n"
            "您想修改查詢條件嗎？"
        ))]
    }
```

---

## Impact on User Experience

### Before Fix

```
User: "悠遊卡股份有限公司，時間2025年"

System Response Sequence:
1. "No data"
2. "我需要您提供更多信息...
    請確認或提供：
    - 您要查詢的具體實體/活動名稱
    - 具體想查詢的指標..."
3. [EXACT SAME MESSAGE AS #2]
4. [REPEATS]

User: Confused - "But I already told you! What else do you need?"
```

### After Fix

```
User: "悠遊卡股份有限公司，時間2025年"

System Response:
1. "我找到了相關的項目，但根據您提供的條件（例如時間範圍）查無數據。

    這可能是因為：
    - 該活動/公司在您指定的時間範圍內沒有數據
    - 您指定的指標可能在該期間沒有記錄

    請嘗試：
    - 調整時間範圍（例如：改為上個月或去年同期）
    - 確認指定的實體名稱是否正確
    - 嘗試查詢其他指標

    您想調整查詢條件嗎？"

User: "Ah, I understand! Let me try a different time range."
```

---

## Testing & Verification

### Test Case: Empty Date Range

```bash
uv run run.py

Input 1: "Nike 成效"
Expected: Search results shown

Input 2: "Nike Corporation 2025年"  (assuming 2025 has no data)
Expected:
✅ One clarification message shown
✅ Explains entity found but no data for that date
✅ Suggests adjusting date range
✅ NOT repeated
✅ NO "No data" message
```

### Test Case: Entity + Date + Metrics

```bash
Input 1: "Nike 投遞的格式、成效、投資金額"
Expected: Search results

Input 2: "Nike 2024年"
Expected:
✅ If data exists: Returns data with metrics
✅ If no data: Shows clarification about date/metrics
✅ One clear message, not repeated
```

---

## Debug Logs to Expect

### Good Flow (After Fix)
```
DEBUG [CampaignRouter] Logic: SQL Empty Results -> Ask for filter clarification
DEBUG [CampaignNode] is_ambiguous: False
DEBUG [SupervisorWrapper] CampaignAgent returned a message. Stopping Supervisor loop.
DEBUG [Synthesizer] Clarification message detected from CampaignAgent: 我找到了相關...
```

### Bad Flow (Before Fix)
```
DEBUG [CampaignRouter] Logic: SQL Empty + Never Searched -> SEARCH_ENTITY
[Router loops back to search]
[Clarification detected again]
DEBUG [Synthesizer] DataFrame is empty. Showing "No data"
[Repeated messages]
```

---

## Files Modified

| File | Changes | Purpose |
|------|---------|---------|
| `nodes/campaign_subgraph/router.py` | Lines 212-239 | Always ask for filter clarification on empty SQL |
| `nodes/response_synthesizer.py` | Lines 87-118, 158-169 | Better empty data handling |

---

## Why This Solves the Problem

1. **No More Loops**: Removed the `else search_entity` branch that was causing loops
2. **Clear Messages**: Instead of vague "No data", explains specifically what went wrong
3. **No Repetition**: Only one clarification message, not repeated
4. **Preserves Information**: Doesn't ask for info user already provided
5. **Helpful Guidance**: Suggests specific actions (adjust date, check entity, try other metrics)

---

## Edge Cases Handled

### Case 1: Entity Found, No Data for Date
```
User: "Nike 2025年" (no data for 2025)
Response: "We found Nike but no data for 2025. Try 2024?"
✅ Fixed
```

### Case 2: Metrics Not Available
```
User: "Nike 投遞的格式 2024" (format metrics don't exist)
Response: "Try other metrics or check date range"
✅ Covered
```

### Case 3: Entity Name Wrong
```
User: "Nik 2024" (typo)
Response: "Check entity name or try other conditions"
✅ Covered
```

---

## Related Changes

This fix works together with:
- `CONVERSATION_FLOW_FIX.md` - Internal instruction exposure fix
- `CLARIFICATION_LOOP_SECONDARY_ISSUES.md` - is_ambiguous logic improvements

All work together to improve the clarification handling system.

---

## Summary

**Problem**: System showed "No data" and repeated clarification for already-provided information

**Root Cause**: Router logic for empty SQL results was trying to search again instead of asking for filter adjustment

**Solution**:
1. Simplify router logic to ALWAYS ask for filter clarification on empty SQL
2. Improve ResponseSynthesizer to show helpful messages instead of "No data"
3. Add fallback checks for empty campaign_data

**Result**: Clear, helpful messages that acknowledge provided information and suggest concrete next steps

---

**Commit**: `8a77aff`
**Date**: 2024-12-15
**Files Modified**: 2
**Lines Changed**: +57 lines
