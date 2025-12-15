# Test Case: Clarification Loop Fix Verification

## Test Scenario: Ambiguous Query
**Input**: "悠遊卡 投遞的格式、成效、數據鎖定"

### Expected Flow (After Fix)

```
1. User Input
   → "悠遊卡 投遞的格式、成效、數據鎖定"

2. IntentAnalyzer
   - Calls: search_ambiguous_term("悠遊卡")
   - Returns: Multiple results (e.g., 10 matches)
   - Analysis: Multiple matches found (Case C)
   - Sets: is_ambiguous = True
   - Returns: UserIntent with is_ambiguous=True, ambiguous_options=[]
   - User Message: "您好！根據您提到的「悠遊卡」，我在資料庫中找到了幾個相關項目..."

3. Supervisor
   - Receives: user_intent.is_ambiguous = True
   - Decision: Route to CampaignAgent with clarification instruction
   - Payload: Creates CampaignTask with is_ambiguous=True
   - Instructions: "使用者想查詢與「悠遊卡」相關的活動，但意圖不明確...請詢問使用者想查詢的具體活動名稱"

4. CampaignAgent Router (THE FIX)
   - Receives: task.is_ambiguous = True ✅
   - Checks: hasattr(task, 'is_ambiguous') and task.is_ambiguous
   - Result: is_clarification_request = True
   - Action: return {"next_action": "finish", "final_response": task.instruction_text}
   - Output: Passes clarification instruction to user WITHOUT executing SQL ✅

5. ResponseSynthesizer
   - Receives: CampaignAgent message (clarification)
   - Detects: name="CampaignAgent" and message contains "澄清"/"clarify"/etc.
   - Sets: clarification_pending = True
   - Output: Shows clarification message to user

6. User Response
   - Reads clarification message
   - Responds: "我要查詢品牌部分的悠遊卡"

7. Next Iteration
   - IntentAnalyzer Re-runs (because clarification_pending=True + new HumanMessage)
   - Searches: "品牌部分的悠遊卡" or extracts "悠遊卡"
   - Analysis: Now finds single result (或者至少找到對應的結果)
   - Sets: is_ambiguous = False
   - Supervisor sees: is_ambiguous=False
   - Routes to: CampaignAgent for actual SQL execution
   - Result: Returns data ✅

NO INFINITE LOOP ✅
```

## Key Detection Points (Debug Logs)

### Should See:
```
DEBUG [IntentAnalyzer] Final Structured Intent: UserIntent(...is_ambiguous=True...)
DEBUG [CampaignNode] is_ambiguous: True
DEBUG [CampaignRouter] is_ambiguous=True in task -> treating as clarification request
DEBUG [CampaignRouter] Logic: Clarification request detected -> FINISH
```

### Should NOT See:
```
DEBUG [CampaignExecutor] Executing: SELECT ...  (← This would mean SQL ran when shouldn't)
DEBUG [CampaignRouter] is_ambiguous=True... is_ambiguous=True... (← Repeated logs = loop)
```

## Verification Checklist

- [ ] Run the system with ambiguous query: "悠遊卡 成效"
- [ ] Check: IntentAnalyzer sets is_ambiguous=True
- [ ] Check: CampaignNode receives is_ambiguous=True (see debug log)
- [ ] Check: CampaignRouter detects is_ambiguous=True and returns clarification
- [ ] Check: NO SQL execution happens (no "Executing:" log)
- [ ] Check: Clarification message shown to user ONCE
- [ ] Respond: User selects "品牌部分的悠遊卡"
- [ ] Check: System re-analyzes with new intent (is_ambiguous=False)
- [ ] Check: CampaignAgent now executes SQL and returns data
- [ ] Check: NO infinite loop between Supervisor and CampaignAgent

## Files Modified

1. **schemas/agent_tasks.py**
   - Added: `is_ambiguous: Optional[bool] = Field(False, ...)`

2. **nodes/campaign_subgraph/router.py** (lines 64-82)
   - Enhanced: is_clarification_request detection with 3 levels
   - Added: Level 3 check for `task.is_ambiguous=True`

3. **nodes/supervisor_subgraph/validator.py** (lines 107-110)
   - Added: is_ambiguous propagation from user_intent to decision_payload

4. **nodes/campaign_node_wrapper.py** (line 42)
   - Added: Debug logging for is_ambiguous flag

## Related Files

- **prompts/intent_analyzer_prompt.py**: Guidance on setting is_ambiguous based on search results
- **tools/search_db.py**: Search tool that returns results for disambiguation
- **nodes/supervisor.py**: Supervisor decision logic
- **nodes/response_synthesizer.py**: Response synthesis with clarification detection

## Commits

- `bd6f320`: Fix - Prevent infinite clarification loop by detecting is_ambiguous flag
- `247288d`: Debug - Add is_ambiguous logging to CampaignNode
- `ea6243d`: Docs - Add comprehensive clarification loop fix documentation
