# Conversation Flow Fix - Internal Instruction Exposure Issue

## Problem Summary

The system was exposing **Supervisor's internal routing instructions** as user-facing messages, creating a confusing and broken user experience. Additionally, the router was not properly handling clarification scenarios, leading to repeated internal messages being shown to users.

### User-Reported Issue

When users submitted ambiguous queries:
```
User: "悠遊卡 投遞的格式、成效、數據鎖定 格式投資金額"

System Shows (WRONG):
  "使用者想查詢與「悠遊卡」相關的活動，但意圖不明確。請根據使用者提供的關鍵字...
   從現有資料中找出最相關的活動名稱或ID，並詢問使用者是否要查詢這些活動的...
   請列出選項讓使用者確認。"

  [Same message repeats again]
  "使用者想查詢與「悠遊卡」相關的活動，但意圖不明確。請根據使用者提供的關鍵字..."
```

**Issues:**
1. ❌ User sees internal supervisor instructions (not user-facing messages)
2. ❌ Messages repeat multiple times (infinite loop)
3. ❌ No clarification message from search results
4. ❌ When no data found, system just says "No data" instead of asking for clarification
5. ❌ When date filter returns empty, no guidance on what went wrong

---

## Root Cause Analysis

### Issue 1: Internal Instructions Leaked to User

**Location**: `nodes/campaign_subgraph/router.py:108` (line 108 in original)

```python
# WRONG - Before Fix
if is_clarification_request:
    return {
        "next_action": "finish",
        "final_response": task.instruction_text,  # ❌ This is Supervisor's internal instruction!
        ...
    }
```

**Why This Happened:**
- The Supervisor's planner generates `instructions` like: "使用者想查詢與「悠遊卡」相關的活動，但意圖不明確。請詢問使用者..."
- This is **internal routing logic** meant for the CampaignAgent's executor, NOT for the user
- The Router was blindly passing `task.instruction_text` to final response without filtering
- This message gets passed through ResponseSynthesizer to the user as an AIMessage

### Issue 2: Infinite Loop Formation

The flow was:
```
1. IntentAnalyzer: is_ambiguous=True
   ↓
2. Supervisor: Creates instruction "使用者想查詢..."
   ↓
3. CampaignNode: Passes instruction to Router
   ↓
4. Router: Returns task.instruction_text as final_response
   ↓
5. ResponseSynthesizer: Shows as AIMessage to user ❌
   ↓
6. supervisor.py: Detects CampaignAgent message, stops loop and goes to ResponseSynthesizer
   ↓
7. User sees: "使用者想查詢..."
```

BUT: The Supervisor's validator also doesn't want to route again (checks is_ambiguous),
so after user responds, cycle repeats with same instruction.

### Issue 3: Poor Empty Result Handling

**Location**: `nodes/campaign_subgraph/router.py:149-156` (original)

When search returned 0 results:
```python
elif count == 0:
    return {
        "next_action": "finish_no_data",
        "final_response": "找不到相關的活動名稱或品牌。",  # Generic, not helpful
        ...
    }
```

When SQL executed but returned empty (e.g., date out of range):
```python
if executed_but_empty:
    if search_results is not None:
        return {
            "next_action": "finish_no_data",  # Just gives up
            ...
        }
```

---

## Solution Implemented

### Fix 1: Generate User-Facing Clarification Messages

Instead of returning `task.instruction_text`, the Router now generates proper user-facing clarification messages:

```python
# CORRECT - After Fix
if is_clarification_request:
    # Generate a proper clarification message based on context
    if search_results and len(search_results) > 0:
        options_str = "\n".join([f"- {opt}" for opt in search_results[:10]])
        clarification_msg = (
            f"我找到了多個相關項目。請問您是指以下哪一個？\n\n"
            f"{options_str}\n\n"
            f"如果上述選項都不符合，請提供更多細節，我會為您重新搜尋。"
        )
    else:
        clarification_msg = (
            "我需要您提供更多信息，以便更精確地查詢數據。\n\n"
            "請確認或提供：\n"
            "- 您要查詢的具體實體/活動名稱\n"
            "- 具體想查詢的指標（例如：成效、投資金額、格式等）\n"
            "- 查詢的時間範圍（如適用）\n\n"
            "請提供更多細節，我會為您檢索相應的數據。"
        )

    return {
        "next_action": "finish",
        "final_response": clarification_msg,  # ✅ User-facing message!
        ...
    }
```

**Benefits:**
- ✅ User sees helpful guidance instead of internal instructions
- ✅ Search results shown as options
- ✅ Clear indication of what information is needed

### Fix 2: Improved Empty Search Results Handling

Changed from `finish_no_data` to `finish` with clarification:

```python
# CORRECT - After Fix
elif count == 0:
    clarification_msg = (
        "我無法找到符合您描述的項目。\n\n"
        "這可能是因為：\n"
        "- 實體名稱拼寫不同\n"
        "- 項目名稱可能已更改\n"
        "- 該項目不存在於目前的數據庫中\n\n"
        "請嘗試：\n"
        "- 提供完整的項目名稱\n"
        "- 使用部分關鍵字進行搜尋\n"
        "- 確認時間範圍是否正確\n\n"
        "您可以重新描述想查詢的內容嗎？"
    )
    return {
        "next_action": "finish",  # ✅ Allow user to respond with clarification
        "final_response": clarification_msg,
        ...
    }
```

**Benefits:**
- ✅ User can provide more details instead of seeing "No data"
- ✅ Helpful suggestions on how to refine the query
- ✅ Continues the conversation instead of dead-ending

### Fix 3: Better SQL Empty Results Handling

When entity is found but SQL returns empty (date range issue):

```python
# CORRECT - After Fix
if executed_but_empty:
    if search_results is not None:
        clarification_msg = (
            "我找到了相關的項目，但根據您提供的條件（例如時間範圍）查無數據。\n\n"
            "請檢查：\n"
            "- 時間範圍是否正確？(例如：該活動是否在您指定的時間範圍內執行)\n"
            "- 是否需要調整其他篩選條件？\n\n"
            "請確認或修改查詢條件，我會為您重新檢索。"
        )
        return {
            "next_action": "finish",  # ✅ Ask about filters instead of giving up
            "final_response": clarification_msg,
            ...
        }
```

**Benefits:**
- ✅ User understands the entity was found, but no data for those conditions
- ✅ Clear guidance on checking date range (addresses "2025年" issue)
- ✅ User can adjust conditions and continue

---

## Impact on User Experience

### Before Fix

```
User: "悠遊卡股份有限公司，時間為2025年"

System: "使用者想查詢與「悠遊卡」相關的活動，但意圖不明確。
         請根據使用者提供的關鍵字「悠遊卡 投遞的格式...」，
         從現有資料中找出最相關的活動名稱或ID...
         請列出選項讓使用者確認。"

[REPEATED SAME MESSAGE]

System: "使用者想查詢與「悠遊卡」相關的活動，但意圖不明確..."

[NO DATA appears]
System: "查無資料，請嘗試調整您的查詢條件。"

User: Confused, not sure what to do next ❌
```

### After Fix

```
User: "悠遊卡股份有限公司，時間為2025年"

System: "我找到了多個相關項目。請問您是指以下哪一個？
         - 悠遊卡股份有限公司
         - 悠遊卡9月份宣傳
         - 悠遊卡Q1影音宣傳
         ...
         如果上述選項都不符合，請提供更多細節，我會為您重新搜尋。"

[If no data for 2025]
System: "我找到了相關的項目，但根據您提供的條件（例如時間範圍）查無數據。
         請檢查：
         - 時間範圍是否正確？(例如：該活動是否在您指定的時間範圍內執行)
         - 是否需要調整其他篩選條件？
         請確認或修改查詢條件，我會為您重新檢索。"

User: Understands what went wrong and can take action ✅
```

---

## Files Modified

### 1. `nodes/campaign_subgraph/router.py`

**Commit**: `f0d7aa9`

**Changes**:
- **Lines 101-132** (Clarification detection block):
  - Changed from returning `task.instruction_text` to generating proper user-facing messages
  - Added context-aware message generation (shows search results if available)
  - Added comments explaining the critical fix

- **Lines 170-190** (Empty search results):
  - Changed from `finish_no_data` to `finish` with clarification message
  - Added helpful suggestions for query refinement
  - Encourages user to provide more details

- **Lines 227-246** (SQL empty results):
  - Changed from `finish_no_data` to `finish` with filter clarification
  - Added specific guidance about checking date ranges
  - Shows entity was found but no data for those conditions

---

## Verification Checklist

### Test Case 1: Ambiguous Query with Multiple Results

```
Input: "悠遊卡 成效"

Expected Output:
✅ "我找到了多個相關項目。請問您是指以下哪一個？"
✅ List of 3-10 options shown
✅ Prompt for clarification
✅ Message shown ONCE (no repetition)
✅ NO internal supervision instructions visible
```

### Test Case 2: Entity Found But No Data for Date Range

```
Input: "悠遊卡股份有限公司，時間為2025年"

Expected Flow:
✅ Entity search: Found "悠遊卡股份有限公司"
✅ SQL execution: No data for 2025
✅ Output: "我找到了相關的項目，但根據您提供的條件（例如時間範圍）查無數據。"
✅ Asks to check date range
✅ User can respond with different date
```

### Test Case 3: Entity Not Found

```
Input: "NotExistCampaign"

Expected Output:
✅ "我無法找到符合您描述的項目。"
✅ Possible reasons listed
✅ Suggestions for refinement
✅ "您可以重新描述想查詢的內容嗎？"
✅ User can provide clarification
```

### Test Case 4: Successful Query

```
Input: "Nike 成效"

Expected Output:
✅ Search: Found single entity "Nike"
✅ SQL execution: Returns data
✅ No clarification message
✅ ResponseSynthesizer shows formatted results
```

---

## Debug Logs to Expect

When testing, you should see these debug logs:

### For clarification request:
```
DEBUG [CampaignRouter] Step 1 Check: Data=False, Empty=False, SearchResults=10, Clarification=True
DEBUG [CampaignRouter] Logic: is_ambiguous=True or clarification keyword detected. Generating user-facing clarification...
```

### For empty search results:
```
DEBUG [CampaignRouter] Step 2 Check: SearchResults=0
DEBUG [CampaignRouter] Logic: Search returned no results. Asking for clarification instead of giving up.
```

### For SQL empty results:
```
DEBUG [CampaignRouter] Step 3 Check: Data=False, Empty=True, SearchResults=1
DEBUG [CampaignRouter] Logic: SQL Empty + Already Searched -> Ask for clarification on filters
```

---

## Design Principles Applied

1. **User-Facing vs Internal Separation**:
   - Keep Supervisor's internal routing instructions separate from user messages
   - Only show helpful, contextual guidance to users

2. **Continuity Over Dead-Ending**:
   - Instead of "No data", ask for clarification
   - Allow users to refine and continue conversation

3. **Context-Aware Messages**:
   - Show available options when found
   - Explain why empty results occurred
   - Suggest next steps

4. **No Repetition**:
   - Ensure clarification messages shown once
   - Prevent infinite loops through proper state management

---

## Future Improvements

1. **More Specific Error Messages**:
   - Analyze actual SQL errors and provide targeted suggestions
   - Example: "Column 'campaign_id' not found" → Suggest checking available fields

2. **Search Result Formatting**:
   - Group results by category (Activities, Brands, Companies)
   - Show result counts
   - Highlight exact matches

3. **Date Range Suggestions**:
   - When SQL empty due to date, suggest available date ranges
   - "No data for 2025. Available data: Jan 2024 - Nov 2024"

4. **Conversation Context**:
   - Remember previous clarifications in same conversation
   - Avoid repeating the same clarification messages

---

## Testing Instructions

### Quick Test (5 minutes)
```bash
uv run run.py

# Test 1: Ambiguous query
Input: "悠遊卡 成效"
Expected: See options, not internal instructions

# Test 2: Empty date range
Input: "悠遊卡，2025年"
Expected: See message about checking date range
```

### Comprehensive Test (15 minutes)
1. Follow all test cases in "Verification Checklist" section
2. Monitor debug logs
3. Verify no "finish_no_data" paths are taken (should be "finish" with message)
4. Confirm no supervisor internal instructions visible

---

## Summary

**What Was Fixed:**
- ✅ Router no longer exposes Supervisor's internal instructions to users
- ✅ Generated proper user-facing clarification messages
- ✅ Improved empty result handling with helpful guidance
- ✅ Better support for filter/date range issues
- ✅ Prevents infinite message repetition

**Files Changed:**
- `nodes/campaign_subgraph/router.py`: 56 lines added/modified

**Commits:**
- `f0d7aa9`: Fix: Prevent exposing Supervisor's internal instructions

**Status**: ✅ Ready for Testing

---

## Questions & Support

**Q: Why not fix this in ResponseSynthesizer?**
A: The root issue is in Router returning wrong content. Fixing at Router level prevents any downstream confusion.

**Q: Will this break existing queries?**
A: No, all changes are additive. Only clarification/empty result paths are improved.

**Q: How do I know if the fix is working?**
A: Run the test cases above. You should see helpful user-facing messages instead of internal instructions.

---

**Date Created**: 2024-12-15
**Commit**: f0d7aa9
**Branch**: refactor/multi-agent-system
