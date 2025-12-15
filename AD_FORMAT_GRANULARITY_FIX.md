# Ad Format Granularity Fix

## Problem
The `Ad_Format` column was being aggregated into a single string (e.g., "Format A; Format B") at the MySQL level using `GROUP_CONCAT`. This caused data granularity issues when merging with ClickHouse performance data, which is detailed by individual format ID.

## Solution
Updated `prompts/sql_generator_prompt.py` for both `EXECUTION` and `AUDIENCE` query levels:
1.  **Removed `GROUP_CONCAT`**: Changed the selection of `Ad_Format` (title) and `ad_format_type_id` to direct column selection.
2.  **Updated `GROUP BY`**: Added `aft.title` and `aft.id` to the grouping clause in the subquery.

## Result
-   **MySQL Output**: Now returns multiple rows for a single campaign if it has multiple ad formats (e.g., Row 1: Campaign A, Format A; Row 2: Campaign A, Format B).
-   **Data Fusion**: Can now correctly merge MySQL rows with ClickHouse rows using the composite key `['cmpid', 'ad_format_type_id']`.
-   **Display**: Users will see granular breakdowns of budget and performance per ad format.

## Verification
1.  **Input**: "Format" query.
2.  **SQL**: Generates `SELECT ..., aft.title AS Ad_Format ... GROUP BY ..., aft.title, aft.id`.
3.  **Output**: Distinct rows for each format type.
