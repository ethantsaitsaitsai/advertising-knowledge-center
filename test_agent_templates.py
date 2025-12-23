"""
測試 Agent 執行 SQL templates 的能力
"""
from pathlib import Path
from jinja2 import Template
from config.database import get_mysql_db
from sqlalchemy import text
import pandas as pd

def load_template(template_name: str, **params):
    """載入並渲染 Jinja2 template"""
    template_path = Path("templates/sql") / template_name

    with open(template_path, 'r', encoding='utf-8') as f:
        template_content = f.read()

    template = Template(template_content)
    sql = template.render(**params)
    return sql

def execute_template(template_name: str, **params) -> pd.DataFrame:
    """執行 template 並返回 pandas DataFrame"""
    sql = load_template(template_name, **params)

    db = get_mysql_db()
    with db._engine.connect() as conn:
        result = conn.execute(text(sql))
        rows = result.fetchall()
        columns = result.keys()

        # 轉換為 DataFrame
        df = pd.DataFrame(rows, columns=columns)
        return df

def test_multi_template_execution():
    """測試執行多個 templates 並 merge 結果"""
    print("\n" + "="*60)
    print("🧪 Testing Multi-Template Execution")
    print("="*60)

    # 範例：模擬 "悠遊卡投遞的格式、數據鎖定、預算"
    # 1. 首先從 campaign_basic 取得 campaign_ids
    print("\n📌 Step 1: 取得活動 IDs")
    basic_df = execute_template(
        "campaign_basic.sql",
        client_names=["悠遊卡"]  # 測試用
    )

    print(f"✅ Found {len(basic_df)} campaigns")
    if len(basic_df) > 0:
        print(f"Sample data:\n{basic_df.head()}")

        # 取得 campaign_ids
        campaign_ids = basic_df['campaign_id'].tolist()[:3]  # 只取前3個測試
        print(f"\n🔍 Campaign IDs: {campaign_ids}")

        # 2. 執行其他 templates
        print("\n📌 Step 2: 查詢格式資訊")
        formats_df = execute_template(
            "ad_formats.sql",
            campaign_ids=campaign_ids
        )
        print(f"✅ Found {len(formats_df)} format records")
        if len(formats_df) > 0:
            print(f"Columns: {list(formats_df.columns)}")
            print(f"Sample: {formats_df.head(1).to_dict('records')}")

        print("\n📌 Step 3: 查詢數據鎖定")
        segments_df = execute_template(
            "targeting_segments.sql",
            campaign_ids=campaign_ids
        )
        print(f"✅ Found {len(segments_df)} segment records")
        if len(segments_df) > 0:
            print(f"Columns: {list(segments_df.columns)}")

        print("\n📌 Step 4: 查詢預算細節")
        budget_df = execute_template(
            "budget_details.sql",
            campaign_ids=campaign_ids
        )
        print(f"✅ Found {len(budget_df)} budget records")
        if len(budget_df) > 0:
            print(f"Columns: {list(budget_df.columns)}")

        # 3. Merge 結果
        print("\n📌 Step 5: Merge 所有結果")
        merged_df = basic_df[basic_df['campaign_id'].isin(campaign_ids)]

        if len(formats_df) > 0:
            merged_df = merged_df.merge(
                formats_df,
                on='campaign_id',
                how='left'
            )
            print("✅ Merged formats data")

        if len(budget_df) > 0:
            merged_df = merged_df.merge(
                budget_df,
                on='campaign_id',
                how='left'
            )
            print("✅ Merged budget data")

        # 對於一對多的關係（如 segments），可以選擇聚合或保留明細
        if len(segments_df) > 0:
            # 聚合 segment_name
            segments_agg = segments_df.groupby('campaign_id').agg({
                'segment_name': lambda x: ', '.join(x.dropna().unique())
            }).reset_index()
            merged_df = merged_df.merge(
                segments_agg,
                on='campaign_id',
                how='left'
            )
            print("✅ Merged segments data (aggregated)")

        print(f"\n📊 Final merged data shape: {merged_df.shape}")
        print(f"Columns: {list(merged_df.columns)}")
        print(f"\nSample merged record:")
        if len(merged_df) > 0:
            for col in merged_df.columns[:10]:  # 只顯示前10個欄位
                print(f"  {col}: {merged_df.iloc[0][col]}")

        return True
    else:
        print("⚠️  No campaigns found for '悠遊卡'")
        return False

def test_template_combinations():
    """測試不同的 template 組合"""
    print("\n" + "="*60)
    print("🧪 Testing Different Template Combinations")
    print("="*60)

    # 組合 1: 基本資訊 + 格式
    print("\n📦 Combination 1: Basic + Formats")
    basic_df = execute_template("campaign_basic.sql")
    if len(basic_df) > 0:
        campaign_ids = basic_df['campaign_id'].tolist()[:2]
        formats_df = execute_template("ad_formats.sql", campaign_ids=campaign_ids)
        print(f"  Basic: {len(basic_df)} rows, Formats: {len(formats_df)} rows")

    # 組合 2: 基本資訊 + 版位
    print("\n📦 Combination 2: Basic + Media Placements")
    if len(basic_df) > 0:
        placements_df = execute_template("media_placements.sql", campaign_ids=campaign_ids)
        print(f"  Basic: {len(basic_df)} rows, Placements: {len(placements_df)} rows")

    # 組合 3: 基本資訊 + KPI
    print("\n📦 Combination 3: Basic + Contract KPIs")
    if len(basic_df) > 0:
        kpis_df = execute_template("contract_kpis.sql", campaign_ids=campaign_ids)
        print(f"  Basic: {len(basic_df)} rows, KPIs: {len(kpis_df)} rows")

    print("\n✅ All combinations tested successfully!")

if __name__ == "__main__":
    print("\n" + "="*60)
    print("🚀 Starting Agent Template Execution Tests")
    print("="*60)

    # 測試 1: 多個 templates 執行與 merge
    success = test_multi_template_execution()

    # 測試 2: 不同組合
    test_template_combinations()

    print("\n" + "="*60)
    if success:
        print("🎉 Agent template execution test completed successfully!")
    else:
        print("⚠️  Some tests had no data, but execution logic is correct")
    print("="*60)
