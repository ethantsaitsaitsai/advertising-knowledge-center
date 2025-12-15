# Supervisor Context Injection Fix

## Problem
The Supervisor was entering an infinite loop of calling `CampaignAgent` even when data was available.
- **Root Cause**: The `planner_node` in `nodes/supervisor_subgraph/planner.py` was calculating valuable context (`payload_context` containing the data summary and `user_intent_context`), but these variables were **not included** in the `SUPERVISOR_SYSTEM_PROMPT`.
- **Consequence**: The LLM never saw the "Available (5 rows)" summary, so it assumed it still needed to fetch data, ignoring the prompt's instructions to check for `campaign_data`.

## Solution
Modified `prompts/supervisor_prompt.py` to explicitly append the context variables at the end of the system prompt:

```python
**上下文資訊 (Context Data)**:
以下是系統自動提取的狀態，請作為決策依據：

1. **User Intent (意圖分析)**:
{user_intent_context}

2. **System Payload (現有數據狀態)**:
{payload_context}
```

## Expected Behavior
1. `planner_node` generates `payload_context` (e.g., "Available (5 rows)...").
2. Prompt template now injects this string.
3. Supervisor LLM reads "System Payload: Available (5 rows)".
4. Supervisor follows the rule: "If campaign_data has rows -> Go to PerformanceAgent".
5. Loop breaks.
