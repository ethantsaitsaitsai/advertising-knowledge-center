# Data Fusion Column Standardization Fix

## Problem
1.  **Duplicate CTR**: The output contained both `CTR` (uppercase, calculated) and `ctr` (lowercase, from raw data) because the code was case-sensitive.
2.  **Missing Segment_Category**: The `Segment_Category` column was being dropped because the filtering logic expected specific casing that didn't match the input.

## Solution
Modified `nodes/data_fusion.py` to enforce **Global Lowercase Standardization** at the very beginning of the fusion process.

1.  **Force Lowercase**: `df.columns = df.columns.str.lower()` applied immediately to both MySQL and ClickHouse dataframes.
2.  **Updated Logic**: All internal logic (filtering, merging, calculating) now strictly uses lowercase keys (e.g., `ctr`, `segment_category`, `budget_sum`).
3.  **Restore Display Names**: Added a final mapping step to restore capitalized column names (e.g., `CTR`, `Ad_Format`) based on the configuration for user-friendly output.

## Verification
-   **CTR**: Will now be calculated into the existing `ctr` column (or overwrite it), preventing duplicates.
-   **Segment**: Since logic looks for `segment_category` (lowercase) and the input is forced to lowercase, it will be correctly identified and preserved.
-   **Display**: The final output will still show "Ad_Format", "CTR", etc., thanks to the restoration step.
