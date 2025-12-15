# Metrics Update Verification Report

## Changes Implemented

### 1. Schema Documentation (`documents/clickhouse_schema_context.md`)
- **Added**: Explicit formulas for Derived Metrics (CTR, VTR, ER).
- **Definition**:
  - **CTR**: `Total Clicks / Effective Impressions * 100`
  - **VTR**: `Total Q100 Views / Effective Impressions * 100`
  - **ER**: `Total Engagements / Effective Impressions * 100`
- **Effective Impressions**: Defined as `SUM(CASE WHEN ad_type = 'dsp-creative' THEN cv ELSE impression END)`.

### 2. SQL Generation Prompt (`prompts/clickhouse_generator_prompt.py`)
- **Updated Input**: Now accepts `{metrics}` list to be aware of user requests.
- **New Example**: Added `Example 3` demonstrating:
  - How to select `effective_impressions`.
  - How to calculate `ctr`, `vtr`, `er` directly in SQL using `multiIf` for the denominator.

### 3. Generator Node (`nodes/performance_subgraph/generator.py`)
- **Fix**: Passed `metrics` from `analysis_needs` to the LLM prompt. Previously, the specific metric requests were ignored by the prompt template.

## Verification Logic

1.  **Request**: User asks for "CTR", "VTR", or "ER".
2.  **Intent Analyzer**: Extracts `metrics=['CTR', 'VTR', 'ER']`.
3.  **Generator**:
    - Receives `metrics` list.
    - Uses `clickhouse_schema_context.md` to find the correct formula (`Effective Impressions`).
    - Uses `prompts/clickhouse_generator_prompt.py` Example 3 as a template.
    - Generates SQL with `effective_impressions` and derived rates.
4.  **Data Fusion**:
    - Receives `effective_impressions`, `CTR`, `VTR`, `ER` columns from ClickHouse.
    - Recognizes `effective_impressions` column (via `column_mappings.yaml`).
    - *Optionally* recalculates rates in Python for precision (using the same formula), ensuring data integrity.

## Conclusion
The system is now fully aligned to calculate these metrics correctly using the "Effective Impressions" standard, both in SQL generation and Python post-processing.
