# Audience Level Aggregation Fix

## Problem
When querying at the `AUDIENCE` level (e.g., asking for "Segment" and "Format"), the result was aggregating data by Campaign Name instead of breaking it down by Ad Format. This happened because the `Ad_Format` column (and its ID) was missing from the MySQL query result, causing the downstream `DataFusion` logic to default to a coarser grouping.

**Root Cause:**
The SQL template for `AUDIENCE` level in `prompts/sql_generator_prompt.py` had the selection of `ad_format_type_id` and `Ad_Format` commented out or omitted. The LLM followed this template literally, failing to select the format columns even when requested.

## Solution
Updated `prompts/sql_generator_prompt.py`:
-   **Modified `AUDIENCE` Template**: Explicitly added `GROUP_CONCAT(DISTINCT aft.title SEPARATOR '; ') AS Ad_Format` and `GROUP_CONCAT(DISTINCT pcd.ad_format_type_id SEPARATOR '; ') AS ad_format_type_id` to the subquery.
-   **Added Join**: Ensured `LEFT JOIN ad_format_types aft ON pcd.ad_format_type_id = aft.id` is present in the subquery logic.

## Verification
1.  **Input**: "Segment" and "Format" query.
2.  **SQL Generation**: Now produces a query that selects both `Segment_Category` and `Ad_Format` (with IDs).
3.  **Data Fusion**: Receives `Ad_Format` column.
4.  **Grouping**: `DataFusion` detects `Ad_Format` in the columns and includes it in the grouping keys.
5.  **Result**: Data is correctly aggregated by Campaign + Ad Format + Segment.

## Note on "Ad_Format None" Filtering
The user also asked why `None` values for `Ad_Format` weren't filtered. This is **by design**. The `DataFusion` logic (`nodes/data_fusion.py`) intentionally keeps `None`/`Empty` values to avoid dropping valid audience data that might not have an associated ad format. It only filters out explicit `'0'` values.
