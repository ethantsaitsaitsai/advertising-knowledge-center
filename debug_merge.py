import pandas as pd
from tools.data_processing_tool import pandas_processor

# --- Mock Data based on Logs ---

# 1. Investment Budget (Anchor) - 2 rows
# 假設兩個 Campaign，每個有一筆投資
mock_investment = [
    {"campaign_id": 21530, "format_name": "Format A", "investment_amount": 1000},
    {"campaign_id": 21531, "format_name": "Format B", "investment_amount": 2000}
]

# 2. Ad Formats - 6 rows (Multiplication Source?)
# 模擬：每個 Campaign 有多個 Format 記錄 (可能是不同尺寸或 ID)
mock_ad_formats = [
    {"campaign_id": 21530, "format_name": "Format A", "format_type_id": 101},
    {"campaign_id": 21530, "format_name": "Format A", "format_type_id": 102}, # Duplicate Name, Diff ID
    {"campaign_id": 21530, "format_name": "Format X", "format_type_id": 103}, # Diff Name
    {"campaign_id": 21531, "format_name": "Format B", "format_type_id": 201},
    {"campaign_id": 21531, "format_name": "Format B", "format_type_id": 202},
    {"campaign_id": 21531, "format_name": "Format Y", "format_type_id": 203}
]

# 3. Performance (Unified) - 10 rows
mock_performance = [
    {"campaign_id": 21530, "ad_format_type_id": 101, "clicks": 10},
    {"campaign_id": 21530, "ad_format_type_id": 102, "clicks": 20},
    {"campaign_id": 21531, "ad_format_type_id": 201, "clicks": 30},
    {"campaign_id": 21531, "ad_format_type_id": 202, "clicks": 40},
    # ... more rows
]

# --- Debug Flow ---

print("=== Debug Start ===")
current_data = mock_investment
print(f"Step 0 (Anchor): {len(current_data)} rows. Total Inv: {sum(r['investment_amount'] for r in current_data)}")

# Step 1: Merge Ad Formats
# Reporter Log says: "Ad Formats merge using dual keys: ['campaign_id', 'format_name']"
# And: "Merged 2 rows with 6 rows on 'campaign_id,format_name' (left) -> 4 rows"

print("\n--- Step 1: Merge Ad Formats ---")
# Simulate dual key merge
merge_keys = ["campaign_id", "format_name"]

res = pandas_processor.invoke({
    "data": current_data,
    "merge_data": mock_ad_formats,
    "merge_on": ",".join(merge_keys),
    "operation": "merge",
    "merge_how": "left"
})
current_data = res['data']
print(f"Result: {len(current_data)} rows.")
print(f"Total Inv: {sum(r['investment_amount'] for r in current_data)}")
for row in current_data:
    print(f"  CID: {row.get('campaign_id')}, Fmt: {row.get('format_name')}, ID: {row.get('format_type_id')}, Inv: {row.get('investment_amount')}")

# Analysis:
# If Campaign 21530 has 'Format A' in Anchor, but 'Format A' appears TWICE in Ad Formats (ID 101, 102),
# The merge will split the row into 2 rows.
# BOTH rows will carry the original 'investment_amount' (1000).
# Total Inv becomes 1000 + 1000 + ... = Inflated.

print("\n=== Debug End ===")

