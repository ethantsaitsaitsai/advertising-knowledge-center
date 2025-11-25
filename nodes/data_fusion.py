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
    ch_data = state.get('clickhouse_result', [])

    # 【修正 1】只要有 MySQL 資料就應該繼續，不要因為缺 CH 資料就停下來
    if not mysql_data:
        return {"final_result_text": "查無數據 (MySQL 無回傳)。"}

    # 2. 轉換 DataFrame
    df_mysql = pd.DataFrame(mysql_data)
    df_ch = pd.DataFrame(ch_data) if ch_data else pd.DataFrame()

    # 轉型 cmpid 以確保能 Join
    if 'cmpid' in df_mysql.columns:
        df_mysql['cmpid'] = pd.to_numeric(df_mysql['cmpid'], errors='coerce')

    if not df_ch.empty and 'cmpid' in df_ch.columns:
        df_ch['cmpid'] = pd.to_numeric(df_ch['cmpid'], errors='coerce')

    # 3. 合併 (Merge)
    # 【修正 2】改用 Left Join (how='left')
    # 這樣即使 CH 沒資料，MySQL 的活動資訊還是會保留下來
    if not df_ch.empty:
        merged_df = pd.merge(df_mysql, df_ch, on='cmpid', how='left', suffixes=('', '_ch'))
    else:
        merged_df = df_mysql  # 如果 CH 沒資料，就直接用 MySQL 的資料

    # 4. 計算衍生指標 (Derived Metrics)
    # 這裡的計算不會因為欄位缺失而報錯，我們加了檢查

    # CTR
    if 'total_clicks' in merged_df.columns and 'effective_impressions' in merged_df.columns:
        merged_df['CTR'] = merged_df.apply(
            lambda x: (x['total_clicks'] / x['effective_impressions'] * 100)
            if pd.notnull(x['effective_impressions']) and x['effective_impressions'] > 0 else 0,
            axis=1
        )

    # CPC
    # 假設 MySQL 的預算欄位可能是 'budget', 'Budget_Sum' 等，這裡需對應你的 SQL
    budget_col = next((col for col in ['budget', 'Budget_Sum', 'total_budget'] if col in merged_df.columns), None)

    if budget_col and 'total_clicks' in merged_df.columns:
        merged_df['CPC'] = merged_df.apply(
            lambda x: (x[budget_col] / x['total_clicks'])
            if pd.notnull(x['total_clicks']) and x['total_clicks'] > 0 else 0,
            axis=1
        )

    # 5. 格式化輸出
    # 將 NaN (因為 Left Join 產生的空值) 填補為 0 或空字串，避免前端顯示錯誤
    final_df = merged_df.fillna(0)

    # 只要有 DataFrame 就輸出，不要管指標有沒有算出來
    return {"final_dataframe": final_df.to_dict('records')}
