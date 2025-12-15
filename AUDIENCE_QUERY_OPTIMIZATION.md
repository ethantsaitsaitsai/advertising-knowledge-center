# Audience Query Optimization (Split Subquery)

## Problem
The `AUDIENCE` level query was extremely slow (taking > 3 minutes) because it attempted to join `PreCampaign`, `AdFormats`, and `TargetSegments` in a single subquery. Since both Ad Formats and Target Segments have a 1-to-Many relationship with PreCampaign, this created a massive **Cartesian Product (Cross Join)** explosion, exponentially increasing the number of rows MySQL had to process before grouping.

## Solution
Implemented a **Split Subquery Strategy** in `prompts/sql_generator_prompt.py`:

1.  **FormatInfo Subquery**: Independently aggregates `PreCampaign` + `AdFormats` to calculate `Budget_Sum` and get `Ad_Format` rows. Grouped by `one_campaign_id`, `ad_format_title`, `ad_format_id`.
2.  **SegmentInfo Subquery**: Independently aggregates `PreCampaign` + `TargetSegments` to get `Segment_Category`. Grouped by `one_campaign_id`.
3.  **Main Query**: Joins `one_campaigns` with `FormatInfo` and `SegmentInfo`.

## Benefits
-   **Performance**: Eliminates the Cartesian product. Format calculation is fast; Segment calculation is isolated.
-   **Accuracy**: Budget sum is no longer inflated by the number of segments multiplied by the number of formats.
-   **Structure**: Maintains the "Granular Ad Format" requirement (one row per format) while still attaching the aggregated Segment information to each row.

## Verification
-   **SQL Logic**: `one_campaigns` -> LEFT JOIN (Formats) -> LEFT JOIN (Segments).
-   **Expected Result**: Execution time should drop significantly (from minutes to seconds).
