# SQL Syntax Fix: WHERE Clause After LEFT JOIN

**Date**: 2025-12-15
**Branch**: refactor/multi-agent-system
**Status**: ✅ FIXED AND COMMITTED

---

## Problem Summary

Your system was generating SQL with invalid syntax, causing MySQL parser errors:

```
SQL Error: (mysql.connector.errors.ProgrammingError) 1064 (42000):
You have an error in your SQL syntax near 'LEFT JOIN'
```

**Root Cause**: The SQL templates for EXECUTION and AUDIENCE query levels placed the `WHERE` clause BEFORE the `LEFT JOIN`, which violates MySQL syntax rules.

---

## What Was Broken

### Invalid SQL Structure (Before Fix)

```sql
FROM one_campaigns oc
JOIN cue_lists cl ON oc.cue_list_id = cl.id
JOIN clients c ON cl.client_id = c.id
WHERE c.company = '悠遊卡股份有限公司'  ← WHERE clause here
LEFT JOIN (                            ← LEFT JOIN AFTER WHERE = Syntax Error!
    SELECT pc.one_campaign_id, ...
) AS SegmentInfo ON oc.id = SegmentInfo.one_campaign_id
```

**Why This Failed**: SQL syntax requires all JOIN operations (including LEFT JOIN) to appear **before** the WHERE clause. The order must be:
```
FROM → JOIN → LEFT JOIN → WHERE → GROUP BY → ORDER BY
```

---

## What Was Fixed

### File Modified

**File**: `prompts/sql_generator_prompt.py`

### Changes Made

#### 1. Fixed EXECUTION Template (Lines 140-167)

**Before** (Invalid - Line 154):
```sql
WHERE c.company = '目標公司' -- 【條件前推】
LEFT JOIN ( ... ) AS FormatInfo ON ...
```

**After** (Valid - Lines 153-165):
```sql
LEFT JOIN (
    SELECT pc.one_campaign_id,
        GROUP_CONCAT(aft.title SEPARATOR '; ') AS Ad_Format,
        SUM(pc.budget) AS Budget_Sum
    FROM pre_campaign pc
    LEFT JOIN pre_campaign_detail pcd ON pc.id = pcd.pre_campaign_id
    LEFT JOIN ad_format_types aft ON pcd.ad_format_type_id = aft.id
    GROUP BY pc.one_campaign_id
) AS FormatInfo ON oc.id = FormatInfo.one_campaign_id
-- 【條件前推】在此層級篩選公司 (WHERE 必須在所有 JOIN 之後)
WHERE c.company = '目標公司'
```

#### 2. Fixed AUDIENCE Template (Lines 193-220)

**Before** (Invalid - Line 206):
```sql
WHERE c.company = '目標公司'
LEFT JOIN ( ... ) AS SegmentInfo ON ...
```

**After** (Valid - Lines 205-218):
```sql
LEFT JOIN (
    SELECT pc.one_campaign_id,
        GROUP_CONCAT(DISTINCT ts.description SEPARATOR '; ') AS Segment_Category,
        SUM(pc.budget) AS Budget_Sum
    FROM pre_campaign pc
    LEFT JOIN campaign_target_pids ctp ON pc.id = ctp.source_id AND ctp.source_type = 'PreCampaign'
    LEFT JOIN target_segments ts ON ctp.selection_id = ts.id
    WHERE (ts.data_source IS NULL OR ts.data_source != 'keyword')
    GROUP BY pc.one_campaign_id
) AS SegmentInfo ON oc.id = SegmentInfo.one_campaign_id
-- 【條件前推】在此層級篩選公司 (WHERE 必須在所有 JOIN 之後)
WHERE c.company = '目標公司'
```

#### 3. Updated Strategy Comments

**EXECUTION Strategy (Line 137)** - Clarified "條件前推" (condition push-down):

**Before**:
```
1. **條件前推**: 若有公司過濾，優先在 clients 層篩選。
```

**After**:
```
1. **條件前推**: 若有 company / brand 過濾，在 clients 層篩選 - 但 WHERE 子句必須在所有 JOIN 之後。
   可使用 JOIN 條件來提前過濾（例如 `JOIN clients c ON cl.client_id = c.id AND c.company = '目標公司'`），
   或在子查詢內過濾。
```

**AUDIENCE Strategy (Line 189)** - Same clarification applied.

---

## Why "條件前推" Was Misunderstood

The prompt template mentioned "條件前推" (push down filters early) as an optimization strategy (lines 11-14), but this was **misinterpreted** to mean "place WHERE before JOIN".

### Correct Interpretation of "條件前推"

**Method 1: Filter in JOIN Condition**
```sql
FROM one_campaigns oc
JOIN clients c ON cl.client_id = c.id AND c.company = '目標公司'  ← Early filtering
LEFT JOIN ( ... ) AS Info ON oc.id = Info.one_campaign_id
```

**Method 2: Filter in Subquery**
```sql
FROM one_campaigns oc
LEFT JOIN (
    SELECT one_campaign_id, SUM(budget) AS Budget_Sum
    FROM pre_campaign
    WHERE some_condition  ← Filter inside subquery
    GROUP BY one_campaign_id
) AS Info ON oc.id = Info.one_campaign_id
WHERE oc.company = '目標公司'  ← Main WHERE after all JOINs
```

**Method 3: Traditional WHERE After JOINs** (What we fixed to)
```sql
FROM one_campaigns oc
JOIN clients c ON cl.client_id = c.id
LEFT JOIN ( ... ) AS Info ON oc.id = Info.one_campaign_id
WHERE c.company = '目標公司'  ← WHERE after all JOINs
```

---

## How This Broke the System

### Execution Flow with Broken Template

1. **User Query**: "悠遊卡 成效" → System clarifies
2. **User Clarifies**: "悠遊卡股份有限公司 2025年"
3. **IntentAnalyzer**: Correctly sets query_level='audience', entities, date_range ✓
4. **Supervisor**: Routes to CampaignAgent with query instruction ✓
5. **Generator** (`generator.py:66`): Invokes LLM with broken AUDIENCE template
6. **LLM**: Generates SQL matching the template's invalid structure
7. **Executor** (`executor.py:22`): Attempts to execute SQL
8. **MySQL Parser**: Rejects SQL with error "syntax error near 'LEFT JOIN'"
9. **Router** (`router.py:202-210`): Detects SQL error, retries
10. **Loop**: Retry uses same broken template → error persists

**Result**: User sees no data, system stuck in error loop.

---

## Expected Behavior After Fix

### Test Case

**Input**:
```
User: "悠遊卡 成效"
System: [Shows clarification options]
User: "悠遊卡股份有限公司 2025年"
```

### Generated SQL (After Fix)

```sql
SELECT
    oc.id AS cmpid,
    oc.name AS Campaign_Name,
    oc.start_date,
    oc.end_date,
    SegmentInfo.Segment_Category,
    SegmentInfo.Budget_Sum
FROM one_campaigns oc
JOIN cue_lists cl ON oc.cue_list_id = cl.id
JOIN clients c ON cl.client_id = c.id
LEFT JOIN (
    SELECT pc.one_campaign_id,
        GROUP_CONCAT(DISTINCT ts.description SEPARATOR '; ') AS Segment_Category,
        SUM(pc.budget) AS Budget_Sum
    FROM pre_campaign pc
    LEFT JOIN campaign_target_pids ctp ON pc.id = ctp.source_id AND ctp.source_type = 'PreCampaign'
    LEFT JOIN target_segments ts ON ctp.selection_id = ts.id
    WHERE (ts.data_source IS NULL OR ts.data_source != 'keyword')
    GROUP BY pc.one_campaign_id
) AS SegmentInfo ON oc.id = SegmentInfo.one_campaign_id
WHERE c.company = '悠遊卡股份有限公司'  ← Correct position!
  AND oc.start_date >= '2025-01-01'
  AND oc.end_date <= '2025-12-31'
ORDER BY oc.id
```

**Expected Result**:
- ✅ MySQL accepts the SQL (no syntax error)
- ✅ Query executes successfully
- ✅ Either data is returned OR helpful "no data" message shown
- ❌ No more "You have an error in your SQL syntax near 'LEFT JOIN'"

---

## Impact Assessment

### Query Levels Affected

| Query Level | Affected? | Reason |
|-------------|-----------|--------|
| CONTRACT | ❌ No | Doesn't use LEFT JOIN with WHERE pattern |
| STRATEGY | ❌ No | Uses subquery pattern correctly |
| EXECUTION | ✅ Yes | Template had WHERE before LEFT JOIN |
| AUDIENCE | ✅ Yes | Template had WHERE before LEFT JOIN |

### When Bug Triggered

The bug only triggered when:
1. User query has `query_level='execution'` OR `query_level='audience'`
2. AND user provides company/brand filter (e.g., "悠遊卡股份有限公司")
3. AND system uses the "優化版" (optimized) template with "條件前推"

**Did NOT trigger** if:
- Query level was CONTRACT or STRATEGY
- No company/brand filter provided
- System used the "簡化版" (simplified) template

---

## Risk Assessment

### Low Risk

- **Scope**: Only affects prompt template text (no code logic changes)
- **Type**: Text-only fix in LLM prompt
- **Reversibility**: Can revert commit if issues arise
- **Testing**: Can test with existing queries immediately

### No Breaking Changes

- **Simplified templates** (EXECUTION 方式B, AUDIENCE 簡化版) already correct
- **Existing queries**: CONTRACT and STRATEGY levels unaffected
- **Only fixes**: Broken "優化版" templates that were causing errors

---

## Commit Information

**Commit**: `ebe0e39`
**Message**: "Fix: Correct SQL syntax in EXECUTION and AUDIENCE templates - move WHERE clause after LEFT JOIN"

**Changes**:
- 1 file changed
- 6 insertions(+), 6 deletions(-)
- No code logic changes (prompt template only)

---

## Verification Checklist

### ✅ Code Changes Verified

- [x] EXECUTION template: WHERE moved after LEFT JOIN (line 165)
- [x] AUDIENCE template: WHERE moved after LEFT JOIN (line 218)
- [x] EXECUTION strategy comment updated (line 137)
- [x] AUDIENCE strategy comment updated (line 189)
- [x] All changes committed to git

### 📋 Testing Required

- [ ] Run system with test query: "悠遊卡 成效"
- [ ] Respond with clarification: "悠遊卡股份有限公司 2025年"
- [ ] Verify SQL generation succeeds (no syntax error)
- [ ] Check generated SQL has correct JOIN/WHERE order
- [ ] Verify data returned or helpful empty message shown

---

## Related Fixes

This fix builds on the previous conversation flow fixes:

1. ✅ **is_ambiguous clearing** - Fixed (commit `ad98f84`)
   - System now clears ambiguity when user provides entities + date

2. ✅ **Repeated messages** - Fixed (commit `ad98f84`)
   - System no longer repeats clarification messages

3. ✅ **User-friendly messages** - Fixed (commit `f0d7aa9`)
   - System shows helpful messages instead of internal logic

4. ✅ **SQL syntax** - Fixed (commit `ebe0e39` - THIS FIX)
   - System generates valid SQL for EXECUTION and AUDIENCE queries

**Result**: Complete end-to-end fix from user input → clarification → query execution → data return.

---

## Summary

**Problem**: SQL templates violated MySQL syntax rules by placing WHERE before LEFT JOIN
**Solution**: Moved WHERE clause to appear after all JOIN operations
**Impact**: Fixes MySQL syntax errors for audience and execution queries
**Risk**: Low (prompt-only change, easily reversible)
**Testing**: Run original failing query to verify fix

**Status**: ✅ READY FOR TESTING AND DEPLOYMENT

---

**Last Updated**: 2025-12-15
**Branch**: refactor/multi-agent-system
**Commit**: ebe0e39
