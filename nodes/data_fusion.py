from schemas.state import AgentState
import pandas as pd
from typing import Dict, Any


def data_fusion_node(state: AgentState) -> Dict[str, Any]:
    """
    Simplified Fusion: Merges MySQL and ClickHouse data on cmpid and calculates rates.
    """
    # 1. 獲取資料
    mysql_data = state.get('sql_result', [])
    ch_data = state.get('clickhouse_result', [])

    # 若缺任一邊，直接回傳有的那一邊，或是提示不足
    if not mysql_data and not ch_data:
        return {"final_result_text": "查無數據。"}

    # 2. 轉換 DataFrame (標準化操作)
    df_mysql = pd.DataFrame(mysql_data) if mysql_data else pd.DataFrame()
    df_ch = pd.DataFrame(ch_data) if ch_data else pd.DataFrame()

    # 確保 cmpid 格式一致
    if 'cmpid' in df_mysql.columns:
        df_mysql['cmpid'] = pd.to_numeric(df_mysql['cmpid'], errors='coerce')
    if 'cmpid' in df_ch.columns:
        df_ch['cmpid'] = pd.to_numeric(df_ch['cmpid'], errors='coerce')

    # 3. 執行合併 (Merge)
    # 使用 outer join 以保留所有資料 (視你的業務需求可改為 inner)
    if not df_mysql.empty and not df_ch.empty:
        merged_df = pd.merge(df_mysql, df_ch, on='cmpid', how='left', suffixes=('', '_ch'))
    elif not df_mysql.empty:
        merged_df = df_mysql
    else:
        merged_df = df_ch

    # 4. 計算衍生指標 (Derived Metrics)
    # 直接在合併後的 DataFrame 上運算，不需要管維度是什麼

    # CTR = total_clicks / effective_impressions
    if 'total_clicks' in merged_df.columns and 'effective_impressions' in merged_df.columns:
        merged_df['CTR'] = merged_df.apply(
            lambda x: (x['total_clicks'] / x['effective_impressions'] * 100)
            if pd.notnull(x['effective_impressions']) and x['effective_impressions'] > 0 else 0,
            axis=1
        )

    # CPC = Budget_Sum / total_clicks
    # (假設 MySQL 欄位名稱有統一名為 Budget_Sum 或 budget，請依實際 SQL 修改)
    if 'budget' in merged_df.columns and 'total_clicks' in merged_df.columns:
        merged_df['CPC'] = merged_df.apply(
            lambda x: (x['budget'] / x['total_clicks'])
            if pd.notnull(x['total_clicks']) and x['total_clicks'] > 0 else 0,
            axis=1
        )

    # VTR = views_100 / total_impressions
    if 'views_100' in merged_df.columns and 'total_impressions' in merged_df.columns:
        merged_df['VTR'] = merged_df.apply(
            lambda x: (x['views_100'] / x['total_impressions'] * 100)
            if pd.notnull(x['total_impressions']) and x['total_impressions'] > 0 else 0,
            axis=1
        )

    # 5. 格式化輸出
    # 填充 NaN 為 0 或空白，避免 JSON 序列化錯誤
    final_df = merged_df.fillna(0)

    return {"final_dataframe": final_df.to_dict('records')}
