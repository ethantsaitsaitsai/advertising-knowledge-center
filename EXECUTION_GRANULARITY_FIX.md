# Execution Level Granularity Fix

## Problem
The SQL template for `EXECUTION` level queries (specifically "Way B") was aggregating `Ad_Format` into a single string using `GROUP_CONCAT`. This prevented granular analysis of performance metrics per ad format. Additionally, the budget calculation `SUM(pc.budget)` was incorrect for granular queries as it duplicated the campaign budget.

## Solution
Updated `prompts/sql_generator_prompt.py`:
1.  **Modified `EXECUTION` Template (Way B)**:
    -   Removed `GROUP_CONCAT` for `Ad_Format`.
    -   Added direct selection of `aft.title` and `aft.id`.
    -   Updated `GROUP BY` to include `aft.title` and `aft.id`.
    -   Changed budget calculation to `SUM(pcd.budget)` to reflect format-level budget allocation.

2.  **Verified `ResponseSynthesizer` Logic**:
    -   Reviewed `calculate_insights` in `nodes/response_synthesizer.py`.
    -   Confirmed that since the SQL now returns `pcd.budget` (format-specific budget), a simple `SUM` of the `Budget_Sum` column in the dataframe is correct for calculating the total budget of the result set. No de-duplication logic is needed because the budget is no longer duplicated at the campaign level.

## Verification
-   **Input**: "Format" query at Execution level.
-   **SQL**: Generates granular rows per format.
-   **Budget**: Accurately sums the specific budgets allocated to each format displayed.