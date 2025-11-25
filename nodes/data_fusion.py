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

    # 4. 計算衍生指標 (Derived Metrics)
    # CTR
    if 'total_clicks' in merged_df.columns and 'effective_impressions' in merged_df.columns:
        merged_df['CTR'] = merged_df.apply(
            lambda x: (x['total_clicks'] / x['effective_impressions'] * 100) 
            if pd.notnull(x['effective_impressions']) and x['effective_impressions'] > 0 else 0, 
            axis=1
        )

    # CPC
    budget_col = next((col for col in ['Budget_Sum', 'total_budget', '媒體預算'] if col in merged_df.columns), None)
    if budget_col and 'total_clicks' in merged_df.columns:
        merged_df['CPC'] = merged_df.apply(
            lambda x: (x[budget_col] / x['total_clicks']) 
            if pd.notnull(x['total_clicks']) and x['total_clicks'] > 0 else 0,
            axis=1
        )

    # 5. 格式化輸出
    # Fill NaN values resulting from the left join with 0.
    final_df = merged_df.fillna(0)

    return {"final_dataframe": final_df.to_dict('records')}
