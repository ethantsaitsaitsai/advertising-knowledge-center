# Budget Calculation Fix

## Problem
The system was calculating `Budget_Sum` by summing `pre_campaign.budget` (`pc.budget`) in queries that involved joining `pre_campaign_detail` (`pcd`) or `target_segments`. This led to two issues:
1.  **Duplicate Summation**: If a `pre_campaign` had multiple detail rows (formats), the parent budget was summed multiple times.
2.  **Incorrect Granularity**: The budget for a specific Ad Format is stored in `pcd.budget`, not `pc.budget`.

## Solution
Updated `prompts/sql_generator_prompt.py` for **EXECUTION** and **AUDIENCE** levels:
-   Changed `SUM(pc.budget)` to `SUM(pcd.budget)`.
-   This ensures that the budget is summed from the granular detail level, which is correct for queries broken down by Ad Format.

## Risk Assessment
The schema documentation mentions that `pcd.budget` might be a "virtual limit" in some cases (`same_budget_pool_symbol`). However, for the purpose of "Format Breakdown" reporting, using `pcd.budget` is the only way to attribute specific amounts to specific formats. If the system evolves to handle shared pools more strictly, additional logic may be needed, but this change resolves the immediate multiplication bug.

## Verification
-   **SQL Logic**: Now aggregates `pcd.budget`.
-   **Result**: The `Budget_Sum` in the final report should now accurately reflect the sum of the format-level budgets, rather than an inflated multiple of the campaign budget.
