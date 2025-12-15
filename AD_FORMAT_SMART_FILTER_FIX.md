# DataFusion Ad_Format Filtering Logic Refinement

## Problem
The user correctly identified that when querying for both "Ad_Format" and "Performance Metrics", rows with `Ad_Format = None` or empty are noise, as they cannot have format-specific performance data. The previous `DataFusion` logic retained these rows by default unless `Ad_Format` was explicitly '0'.

## Solution
Modified `nodes/data_fusion.py` to implement a more intelligent filtering rule for `Ad_Format`:

-   **Contextual Filtering**: Introduced a check for `user_requested_performance`.
-   **Strict Filtering**: If the user's original intent explicitly included `Ad_Format` as a dimension **AND** also requested any performance metrics (like CTR, VTR, ER, Impressions, Clicks), then rows where `Ad_Format` is `None`, empty, or `'nan'` are now strictly filtered out.
-   **Preserve Data Otherwise**: If `Ad_Format` is requested but *no* performance metrics are, the original behavior of only filtering out `'0'` is maintained. This allows preserving data where `Ad_Format` being `None` might signify "not set" (e.g., in a campaign detail query).

## Verification
This change ensures that the final report only shows meaningful format-level performance data, addressing the user's concern about irrelevant rows.
