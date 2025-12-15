# Campaign ID Extraction Fix

## Problem
The Supervisor Validator was rejecting transitions to `PerformanceAgent` because `campaign_ids` were missing from the global state, even though `campaign_data` (containing the IDs) was available.

- **Root Cause**: `nodes/campaign_node_wrapper.py` was returning `campaign_data` but failing to extract the IDs into a separate `campaign_ids` list. The Validator strictly checks `state.get("campaign_ids")`.

## Solution
Modified `campaign_node` in `nodes/campaign_node_wrapper.py` to automatically extract IDs from the query result.

```python
    # Extract IDs for Supervisor State
    if campaign_data and "data" in campaign_data:
        ids = []
        for row in campaign_data["data"]:
            # Check common ID keys
            cid = row.get("cmpid") or row.get("id") or row.get("one_campaign_id")
            if cid:
                ids.append(cid)
        if ids:
            result["campaign_ids"] = ids
            print(f"DEBUG [CampaignNode] Extracted {len(ids)} IDs: {ids}")
```

## Verification
1. **CampaignAgent** runs and gets 5 rows.
2. **CampaignNode** extracts `[101, 102, ...]` from the rows.
3. **Global State** updates with `campaign_ids = [101, 102, ...]`.
4. **Supervisor** plans "PerformanceAgent".
5. **Validator** checks `if next_node == "PerformanceAgent" and not ids`.
6. Since `ids` is now present, validation passes.
