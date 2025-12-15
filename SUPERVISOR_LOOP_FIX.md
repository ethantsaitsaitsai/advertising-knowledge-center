# Supervisor Loop & Missing Format ID Fix

## Problem Description
1.  **Infinite Supervisor Loop**: The Supervisor repeatedly called `CampaignAgent` even after receiving valid campaign data. This occurred because the Supervisor's prompt logic didn't explicitly instruct it to stop and move to `PerformanceAgent` when `campaign_data` was already present.
2.  **Missing `ad_format_type_id`**: Queries involving "format" were not returning the `ad_format_type_id`, which is crucial for joining ClickHouse performance data. This was due to the SQL templates in the prompt omitting this field.

## Changes Implemented

### 1. Supervisor Prompt (`prompts/supervisor_prompt.py`)
- **Updated `Thought` Section**: Added explicit "State Check" logic.
    - **Rule**: If `campaign_data` is present (meaning CampaignAgent finished), and `needs_performance=True`, the Supervisor **MUST** call `PerformanceAgent`.
    - **Rule**: If `needs_performance=False` and data is present, move to `ResponseSynthesizer`.
    - **Goal**: Break the loop by recognizing the "Data Found" state as a completion of the CampaignAgent's task.

### 2. SQL Generator Prompt (`prompts/sql_generator_prompt.py`)
- **Added Constraint #7**: "Format ID Requirement" - explicitly requires selecting `ad_format_type_id` when `Ad_Format` is involved.
- **Updated `EXECUTION` Template**: Added `ad_format_type_id` (via `GROUP_CONCAT`) to the standard execution query.
- **Updated `AUDIENCE` Template**: Added `ad_format_type_id` (via `GROUP_CONCAT` and `JOIN pre_campaign_detail`) to the audience query, ensuring format IDs are available even when querying segments.

## Verification Logic
1.  **Loop Test**:
    - Input: "悠遊卡 2025年 成效"
    - Expected:
        1. Supervisor -> CampaignAgent (get IDs)
        2. CampaignAgent -> Returns 5 rows (with IDs)
        3. Supervisor -> Checks `campaign_data` -> **PerformanceAgent** (NOT CampaignAgent again)
        4. PerformanceAgent -> ClickHouse
        5. Supervisor -> ResponseSynthesizer

2.  **Format ID Test**:
    - Input: "悠遊卡 投遞的格式"
    - Expected SQL: `SELECT ..., GROUP_CONCAT(aft.id) AS ad_format_type_id FROM ...`
    - Result: `data_fusion.py` can now join this ID with ClickHouse data correctly.