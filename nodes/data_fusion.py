from schemas.state import AgentState
import pandas as pd
from typing import Dict, Any


def data_fusion_node(state: AgentState) -> Dict[str, Any]:
    """
    Fuses MySQL and ClickHouse data, performs aggregation and calculates derived metrics.
    """
    # 1. 獲取資料
    mysql_data = state.get('mysql_bridge_result', [])
    ch_data = state.get('clickhouse_result', []) # 從 state.clickhouse_result 獲取 CH 結果
    
    if not mysql_data or not ch_data:
        return {"final_result_text": "查無足夠數據進行分析。"}

    # 2. 轉換為 DataFrame
    df_mysql = pd.DataFrame(mysql_data)
    df_ch = pd.DataFrame(ch_data)
    
    # Ensure cmpid is of the same type for merging
    if 'cmpid' in df_mysql.columns:
        df_mysql['cmpid'] = pd.to_numeric(df_mysql['cmpid'], errors='coerce')
    if 'cmpid' in df_ch.columns:
        df_ch['cmpid'] = pd.to_numeric(df_ch['cmpid'], errors='coerce')

    # Drop rows with NaN cmpid after conversion
    df_mysql.dropna(subset=['cmpid'], inplace=True)
    df_ch.dropna(subset=['cmpid'], inplace=True)
    
    # 3. 合併 (Merge on cmpid)
    merged_df = pd.merge(df_mysql, df_ch, on='cmpid', how='inner', suffixes=('_mysql', '_ch'))
    
    # 4. 聚合 (Aggregation)
    analysis_needs = state.get('analysis_needs', {})
    dims = analysis_needs.get('dimensions', [])
    metrics = analysis_needs.get('metrics', [])

    # Mapping SlotManager dimensions to actual DataFrame columns
    dimension_mapping = {
        'Brand': '品牌',
        'Agency': '代理商',
        'Ad_Format': '廣告格式名稱', 
        'Date_Month': 'Date_Month', # 假設已從 MySQL 提取或需要進一步處理
        'Date_Year': 'Date_Year',   # 假設已從 MySQL 提取或需要進一步處理
    }
    actual_dims = [dimension_mapping[d] for d in dims if d in dimension_mapping and dimension_mapping[d] in merged_df.columns]
    
    # Prepare aggregation rules for raw metrics
    agg_rules = {}
    if "Budget_Sum" in metrics:
        agg_rules['媒體預算'] = 'sum'
    if "AdPrice_Sum" in metrics:
        agg_rules['廣告賣價'] = 'sum'
    if "Impression_Sum" in metrics or "CTR_Calc" in metrics:
        agg_rules['effective_imps'] = 'sum' # For CTR denominator
        agg_rules['imps'] = 'sum' # For VTR denominator
    if "Click_Sum" in metrics or "CTR_Calc" in metrics or "CPC_Calc" in metrics:
        agg_rules['clicks'] = 'sum' # For CTR numerator and CPC denominator
    if "View3s_Sum" in metrics:
        agg_rules['view3s'] = 'sum'
    if "Q100_Sum" in metrics or "VTR_Calc" in metrics:
        agg_rules['completions'] = 'sum' # For VTR numerator
    if "Engagement_Sum" in metrics or "ER_Calc" in metrics:
        agg_rules['engagements'] = 'sum' # For ER numerator

    if not agg_rules:
        return {"final_result_text": "未指定有效的聚合指標。"}

    # Perform aggregation
    if actual_dims:
        for col in agg_rules.keys():
            if col in merged_df.columns:
                merged_df[col] = pd.to_numeric(merged_df[col], errors='coerce')
        final_df = merged_df.groupby(actual_dims).agg(agg_rules).reset_index()
    else:
        cols_to_sum = [col for col in agg_rules.keys() if col in merged_df.columns]
        for col in cols_to_sum:
            merged_df[col] = pd.to_numeric(merged_df[col], errors='coerce')
        final_df = pd.DataFrame(merged_df[cols_to_sum].sum(), index=[0]) # Sum all, then transpose

    # 5. 計算衍生指標 (Derived Metrics) - 避開 Divide by Zero
    if "CTR_Calc" in metrics and 'clicks' in final_df.columns and 'effective_imps' in final_df.columns:
        final_df['CTR'] = final_df.apply(
            lambda x: (x['clicks'] / x['effective_imps'] * 100) if x['effective_imps'] > 0 else 0, 
            axis=1
        )
    
    if "VTR_Calc" in metrics and 'completions' in final_df.columns and 'imps' in final_df.columns:
        final_df['VTR'] = final_df.apply(
            lambda x: (x['completions'] / x['imps'] * 100) if x['imps'] > 0 else 0, 
            axis=1
        )

    if "ER_Calc" in metrics and 'engagements' in final_df.columns and 'imps' in final_df.columns:
        final_df['ER'] = final_df.apply(
            lambda x: (x['engagements'] / x['imps'] * 100) if x['imps'] > 0 else 0,
            axis=1
        )

    if "CPC_Calc" in metrics and '媒體預算' in final_df.columns and 'clicks' in final_df.columns:
        final_df['CPC'] = final_df.apply(
            lambda x: (x['媒體預算'] / x['clicks']) if x['clicks'] > 0 else 0, 
            axis=1
        )
    
    # 6. 格式化輸出
    return {"final_dataframe": final_df.to_dict('records')}
