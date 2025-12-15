# Data Fusion & Column Hiding Fix

## Problem
1.  **Format Missing**: The `Ad_Format` column was missing because the system failed to merge MySQL data with ClickHouse data correctly.
2.  **Fusion Empty**: The `DataFusion` node sometimes returned an empty result, triggering a fallback to raw ClickHouse data.
3.  **Leaked IDs**: When falling back to raw data, technical columns like `cmpid` and `ad_format_type_id` were displayed because the fallback path lacked the column hiding logic present in `DataFusion`.

## Changes Implemented

### 1. Data Fusion (`nodes/data_fusion.py`)
- **Relaxed Ad Format Filter**: Updated the row filter to be case-insensitive (`'0', 'nan', '', 'none'`) and explicitly log dropped rows. This prevents valid data from being accidentally discarded if formatting issues occur during the merge.

### 2. Response Synthesizer (`nodes/response_synthesizer.py`)
- **Fallback Column Hiding**: Implemented a safety mechanism in the fallback logic. If `DataFusion` fails and raw data is used, the system now explicitly applies `config.get_hidden_columns()` to remove technical IDs (`cmpid`, `id`, `ad_format_type_id`) from the final output.

### 3. Campaign Generator (`nodes/campaign_subgraph/generator.py`)
- **Context Enrichment** (Previous Step): Added logic to automatically include `Ad_Format` in dimensions when format-related keywords are detected. This ensures MySQL queries fetch the necessary format IDs for merging.

## Verification Logic
1.  **Fusion Check**: The relaxed filter reduces the chance of Fusion returning empty due to minor data anomalies (e.g., `NaN` vs `None`).
2.  **Fallback Safety**: Even if Fusion fails (e.g., due to schema mismatch), the user will see the raw data *without* the confusing technical IDs, improving the UX.
3.  **Budget Visibility**: With Fusion likely succeeding (due to fixed merge keys and filters), `Budget_Sum` from MySQL should now correctly appear alongside ClickHouse metrics.
