# Ad Format Missing Fix

## Problem
When a user asks for "投遞的格式" (delivery format), the final result table was missing the `Ad_Format` column, and data aggregation was incorrect (grouping by Campaign instead of Format).

- **Root Cause**: The `CampaignAgent` (MySQL) was not receiving `Ad_Format` in its dimensions list, causing the LLM to generate SQL without the format column. Consequently, `data_fusion.py` couldn't merge the MySQL format data with the ClickHouse performance data properly.

## Solution
Implemented "Context Enrichment" logic in `nodes/campaign_subgraph/generator.py`, mirroring the robust logic already present in the `PerformanceAgent`.

```python
    # Check for Format Intent
    format_keywords = ["format", "格式", "ad_format", "投遞"]
    instruction = task.instruction_text or ""
    
    has_format_intent = (
        any(k in instruction.lower() for k in format_keywords) or 
        any(k in str(needs).lower() for k in format_keywords)
    )
    
    if has_format_intent:
        if "Ad_Format" not in dimensions:
            dimensions.append("Ad_Format")
            print("DEBUG [CampaignGenerator] Auto-enriched Dimensions with 'Ad_Format'")
```

## Verification Logic
1.  **Intent**: User asks "投遞的格式".
2.  **CampaignGenerator**:
    - Detects keyword "格式" or "投遞".
    - Auto-appends `Ad_Format` to dimensions.
3.  **SQL Prompt**: Receives `dimensions=['Ad_Format']`.
4.  **SQL Generation**:
    - Triggered by `Ad_Format` dimension, the LLM now selects `GROUP_CONCAT(aft.title) AS Ad_Format` AND `GROUP_CONCAT(aft.id) AS ad_format_type_id`.
5.  **Data Fusion**:
    - Receives `ad_format_type_id` from MySQL.
    - Receives `ad_format_type_id` from ClickHouse.
    - Merges on `['cmpid', 'ad_format_type_id']`.
    - Result: Correctly granular rows (e.g., Video vs Banner) instead of collapsed rows.
