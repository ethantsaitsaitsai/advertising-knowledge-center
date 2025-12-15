# Data Fusion Architecture Fix

## Problem
1.  **Missing `Segment_Category`**: `PerformanceGenerator`'s Context Enrichment logic polluted the global state with extra dimensions (like `cmpid`), causing `DataFusion`'s pre-merge filtering to aggressively drop columns (like `Segment_Category`) that weren't in the *enriched* list but were in the *original* request.
2.  **Missing `campaign_name` Grouping**: For strategy/audience queries, campaigns were being incorrectly aggregated together because `campaign_name` wasn't automatically included as a grouping key.
3.  **Missing Dates**: `start_date` and `end_date` were being merged into the campaign name and then hidden, confusing users who wanted to see them as separate columns.
4.  **Incorrect Filtering**: Valid rows with empty/NaN `Ad_Format` were being dropped even when the user didn't request that dimension, causing data loss for audience-centric queries.

## Solution
A comprehensive refactor of `nodes/data_fusion.py`:

1.  **Use Original Intent**: Extract `user_original_dims` and `user_original_metrics` directly from the raw state *before* any enrichment pollution. Use these original lists for filtering logic.
2.  **Remove Pre-Merge Filtering**: Deleted the logic that filtered MySQL columns *before* the merge. Now, ALL columns are carried through the merge and aggregation steps, and filtering happens only at the very end for display. This prevents accidental data loss.
3.  **Auto-Group by Campaign Name**: For strategy/audience/execution queries, automatically add `campaign_name` to the grouping keys to ensure correct granularity.
4.  **Preserve Columns**: Explicitly ensure `campaign_name`, `start_date`, `end_date`, and `Budget_Sum` are added to the `cols_to_keep` list so they survive the final filter.
5.  **Disable Date Merging**: Commented out the logic that merged dates into the name string. Dates are now kept as independent columns.
6.  **Smart Filtering**:
    -   Only filter invalid `Ad_Format` ('0') if the user *explicitly* requested the `Ad_Format` dimension.
    -   Only hide all-zero metrics (CTR/VTR/ER) if the user *didn't* explicitly request them.

## Verification Logic
1.  **Segment**: `Segment_Category` will now persist because it's no longer filtered out pre-merge.
2.  **Grouping**: Campaigns will be distinct rows.
3.  **Dates**: `start_date` and `end_date` will appear as columns.
4.  **Data Integrity**: Rows with valid segment data but no format data (if any) will no longer be dropped.
