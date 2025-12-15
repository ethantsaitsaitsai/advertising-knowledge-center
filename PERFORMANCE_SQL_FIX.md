# Performance Agent SQL Persistence Fix

## Problem
The `PerformanceAgent` was executing queries but not saving the generated SQL in the global state, unlike `CampaignAgent`. This made debugging and auditing difficult.

## Solution
Modified `nodes/performance_node_wrapper.py` to:
1.  Extract `generated_sql` from the `performance_subgraph` result.
2.  Construct a structured `performance_data` dictionary (mirroring `campaign_data`).
3.  Return this dictionary to the global state under the `performance_data` key.

## Verification
-   **Output State**: Now contains `performance_data: {'data': [...], 'generated_sqls': ['SELECT ...']}`.
-   **Compatibility**: Still returns `final_dataframe` so `DataFusion` and `ResponseSynthesizer` continue to work without modification.

## Note on Supervisor Instruction
The user questioned whether `Campaign ID` was the correct key for ClickHouse queries when filtering by "Ad Format".
-   **Analysis**: ClickHouse links to MySQL via `cmpid` (Campaign ID).
-   **Logic**: To get metrics for a campaign broken down by format, we filter by `cmpid` and then `GROUP BY ad_format_type_id`.
-   **Conclusion**: The Supervisor's instruction to fetch Campaign IDs first is **correct**. Passing `cmpid` to PerformanceAgent allows it to scope the query correctly while selecting `ad_format_type` for the breakdown.
