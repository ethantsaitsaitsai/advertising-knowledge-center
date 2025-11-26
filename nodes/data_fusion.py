from schemas.state import AgentState
import pandas as pd
from typing import Dict, Any


def data_fusion_node(state: AgentState) -> Dict[str, Any]:
    """
    Robust Data Fusion:
    1. 以 MySQL 資料為主 (Left Join)。
    2. 容許 ClickHouse 資料缺失 (會顯示預算但成效為 0)。
    """
    # 1. 獲取資料
    mysql_data = state.get('sql_result', [])
    sql_result_columns = state.get('sql_result_columns', [])
    ch_data = state.get('clickhouse_result', [])

    # If there's no primary data from MySQL, we can't proceed.
    if not mysql_data or not sql_result_columns:
        return {"final_dataframe": None, "final_result_text": "查無數據 (MySQL 無回傳)。"}

    # 2. 轉換 DataFrame
    df_mysql = pd.DataFrame(mysql_data, columns=sql_result_columns)
    df_ch = pd.DataFrame(ch_data) if ch_data else pd.DataFrame()

    # 轉型 cmpid 以確保能 Join
    if 'cmpid' in df_mysql.columns:
        df_mysql['cmpid'] = pd.to_numeric(df_mysql['cmpid'], errors='coerce')

    if not df_ch.empty and 'cmpid' in df_ch.columns:
        df_ch['cmpid'] = pd.to_numeric(df_ch['cmpid'], errors='coerce')

    # 3. 合併 (Merge)
    # Use a left join to prioritize MySQL data.
    if not df_ch.empty:
        merged_df = pd.merge(df_mysql, df_ch, on='cmpid', how='left', suffixes=('', '_ch'))
    else:
        merged_df = df_mysql

    merged_df = merged_df.fillna(0)

    # 4. 二次聚合 (Re-aggregation)
    analysis_needs = state.get('search_intent', {}).get('analysis_needs', {})
    dimensions = analysis_needs.get('dimensions', [])
    
    # Dimension Mapping (Intent -> DataFrame Column)
    # 必須與 SQL Generator 的 Select 欄位對齊
    dim_map = {
        "Agency": "agencyname",
        "Brand": "product",
        "Advertiser": "company",
        "Campaign_Name": "campaign_name",
        "Ad_Format": "title", 
        "Industry": "name", 
        "廣告計價單位": "name"
    }

    # 找出實際存在的維度欄位
    group_cols = []
    for d in dimensions:
        mapped_col = dim_map.get(d, d)
        if mapped_col in merged_df.columns:
            group_cols.append(mapped_col)
        # 處理 name 衝突 (若 SQL 沒有 alias，可能會有多個 name? 通常 sqlalchemy 會 handle 成 name_1)
        # 這裡簡單處理：若找不到 mapped_col，試著找原始 dimension 名稱
        elif d in merged_df.columns:
            group_cols.append(d)

    # 定義數值欄位 (Metrics)
    # 排除 ID, 日期, 和維度欄位
    exclude_cols = ['cmpid', 'id', 'start_date', 'end_date', 'schedule_dates'] + group_cols
    numeric_cols = [c for c in merged_df.columns if pd.api.types.is_numeric_dtype(merged_df[c]) and c not in exclude_cols]

    if not group_cols:
        # Case A: Total (不分組) -> 雖然 user 沒說要分組，但為了不讓表格只有一行 Total 導致細節全失，
        # 我們通常還是會預設保留 Campaign 層級的列表，除非 user 明確說 "總共多少" (Calculation Type = Total?)
        # 但這裡我們先依據 AnalysisNeeds，若 dimensions 空，就真的給 Total。
        # 不過，如果 calculation_type 是 "Total" 且沒有 dimensions，通常意味著 Summary。
        
        # 修正策略：如果 merged_df 筆數 > 1 且 dimensions 為空，
        # 我們不應該強制縮成一行，除非這是一個純指標查詢。
        # 但為了回應您的需求「不要看到每一行日期」，我們這裡執行聚合。
        if not numeric_cols:
             final_df = merged_df # 無數值可聚，直接回傳
        else:
             final_df = merged_df[numeric_cols].sum().to_frame().T
             final_df['Item'] = 'Total'
    else:
        # Case B: Group By Dimensions
        final_df = merged_df.groupby(group_cols)[numeric_cols].sum().reset_index()

    # 5. 重算衍生指標 (Derived Metrics) - Must be done AFTER aggregation
    # CTR = Total Clicks / Total Impressions * 100
    # 需動態尋找欄位名稱 (ClickHouse 回傳的名稱可能不同)

    # 移除不必要的日期與ID欄位，除非它們是分組維度
    cols_to_drop_lower = {c.lower() for c in ['start_date', 'end_date', 'cmpid', 'id']}
    # 找出所有目前存在的欄位
    current_cols = list(final_df.columns)
    for col in current_cols:
        if col.lower() in cols_to_drop_lower and col not in group_cols:
            final_df = final_df.drop(columns=[col])

    # 找 Impression 欄位
    imp_col = next((c for c in final_df.columns if c in ['effective_impressions', 'Impression_Sum', 'impressions']), None)
    # 找 Click 欄位
    click_col = next((c for c in final_df.columns if c in ['total_clicks', 'Click_Sum', 'clicks']), None)
    # 找 Budget 欄位
    budget_col = next((c for c in final_df.columns if c in ['Budget_Sum', 'total_budget', 'media_budget', 'budget', '媒體預算']), None)

    if imp_col and click_col:
        final_df['CTR'] = final_df.apply(
            lambda x: (x[click_col] / x[imp_col] * 100) if x[imp_col] > 0 else 0, axis=1
        ).round(2)

    if budget_col and click_col:
        final_df['CPC'] = final_df.apply(
            lambda x: (x[budget_col] / x[click_col]) if x[click_col] > 0 else 0, axis=1
        ).round(2)

    return {"final_dataframe": final_df.to_dict('records')}
