from schemas.state import AgentState
import pandas as pd
from typing import Dict, Any


def data_fusion_node(state: AgentState) -> Dict[str, Any]:
    """
    Robust Data Fusion:
    1. 以 MySQL 資料為主 (Left Join)。
    2. 容許 ClickHouse 資料缺失。
    3. 執行資料轉型與二次聚合 (Re-aggregation)。
    4. 特殊處理 Segment Category 的合併 (去重)。
    """
    debug_logs = []
    
    # 1. 獲取資料
    mysql_data = state.get('sql_result', [])
    sql_result_columns = state.get('sql_result_columns', [])
    ch_data = state.get('clickhouse_result', [])

    if not mysql_data or not sql_result_columns:
        return {"final_dataframe": None, "final_result_text": "查無數據 (MySQL 無回傳)。"}

    # 2. 資料前處理 (Preprocessing)
    debug_logs.append(f"Raw MySQL Cols: {sql_result_columns}")
    df_mysql = pd.DataFrame(mysql_data, columns=sql_result_columns)
    df_ch = pd.DataFrame(ch_data) if ch_data else pd.DataFrame()

    # Helper: 安全的數值轉型函式 (Try-Convert-And-Revert)
    def safe_numeric_convert(df, name="df"):
        for col in df.columns:
            if col.lower() in ['cmpid', 'id']: continue
            
            # 嘗試轉型
            converted = pd.to_numeric(df[col], errors='coerce')
            
            # 若轉完變全空但原本有值 (代表是純文字欄位)，則還原
            if converted.isna().all() and df[col].notna().any():
                continue 
            
            df[col] = converted
        return df

    df_mysql = safe_numeric_convert(df_mysql, "MySQL")
    if not df_ch.empty:
        df_ch = safe_numeric_convert(df_ch, "CH")

    # 確保 ID 類欄位格式一致
    if 'cmpid' in df_mysql.columns:
        df_mysql['cmpid'] = pd.to_numeric(df_mysql['cmpid'], errors='coerce')
    if not df_ch.empty and 'cmpid' in df_ch.columns:
        df_ch['cmpid'] = pd.to_numeric(df_ch['cmpid'], errors='coerce')

    # ============================================================
    # Pre-Aggregation: 處理 Segment Category 的去重合併
    # 目標：將同一 cmpid + Format 下的多個 Segment 合併成一行，避免 Budget 重複計算
    # ============================================================
    seg_col_candidates = ['Segment_Category', 'Segment_Category_Name', 'segment_category', '數據鎖定']
    seg_col = next((c for c in df_mysql.columns if c in seg_col_candidates), None)

    if seg_col:
        debug_logs.append(f"Found Segment Column: {seg_col}. Performing Pre-Aggregation.")
        
        # Define helper for joining strings (used in aggregation)
        def join_unique_func(x):
            return ', '.join(sorted(set([str(v) for v in x if v and str(v).lower() != 'nan'])))

        # 定義在 Pre-Aggregation 階段要排除的非 Group Key 欄位 (ID, Date, Segment 本身)
        exclude_from_grouping = {c.lower() for c in ['cmpid', 'id', 'start_date', 'end_date', 'schedule_dates', seg_col.lower()]}
        
        # 找出所有非 Segment, 非 Metric 的維度作為 Pre-Aggregation 的 Group Key
        # 邏輯：不是要排除的 ID/Date，也不是數值型別 (Metric)
        other_dims = [c for c in df_mysql.columns 
                      if c.lower() not in exclude_from_grouping 
                      and not pd.api.types.is_numeric_dtype(df_mysql[c])]
        
        # 定義 Pre-Aggregation 的邏輯
        agg_dict_pre = {}
        for col in df_mysql.columns:
            # 如果欄位已經是 Group Key，就不需要再聚合 (它會在 Index 裡)
            if col in other_dims:
                continue
                
            if col == seg_col:
                agg_dict_pre[col] = join_unique_func # Segment 欄位進行合併
            elif col.lower() == 'budget_sum':
                agg_dict_pre[col] = 'sum' # Budget_Sum 在 Pre-Agg 階段要加總
            elif pd.api.types.is_numeric_dtype(df_mysql[col]):
                agg_dict_pre[col] = 'mean' # 其他數值 (如其他計數) 可以取平均或 first
            else:
                agg_dict_pre[col] = 'first' # 其他維度取 first (反正都是重複值)

        # 執行 Pre-Aggregation
        df_mysql = df_mysql.groupby(other_dims).agg(agg_dict_pre).reset_index()
        debug_logs.append(f"Pre-Aggregated MySQL Rows: {len(df_mysql)}")

    # ============================================================

    # 3. 合併 (Merge)
    if not df_ch.empty:
        merged_df = pd.merge(df_mysql, df_ch, on='cmpid', how='left', suffixes=('', '_ch'))
    else:
        merged_df = df_mysql

    merged_df = merged_df.fillna(0)
    debug_logs.append(f"Merged Cols: {list(merged_df.columns)}")

    # 4. 二次聚合 (Re-aggregation)
    # FIX: 直接從 state 讀取 analysis_needs，而不是不存在的 search_intent
    raw_analysis_needs = state.get('analysis_needs')
    
    if hasattr(raw_analysis_needs, 'model_dump'):
        analysis_needs = raw_analysis_needs.model_dump()
    elif hasattr(raw_analysis_needs, 'dict'):
        analysis_needs = raw_analysis_needs.dict()
    elif isinstance(raw_analysis_needs, dict):
        analysis_needs = raw_analysis_needs
    else:
        analysis_needs = {}

    dimensions = analysis_needs.get('dimensions', [])
    debug_logs.append(f"Intent Dimensions: {dimensions}")
    
    # 簡潔的 Mapping: 僅定義 Intent 到標準 SQL Alias 的對應
    intent_to_alias = {
        "Agency": "Agency",
        "Brand": "Brand",
        "Advertiser": "Advertiser",
        "Campaign_Name": "Campaign_Name",
        "Industry": "Industry", 
        "廣告計價單位": "Pricing_Unit",
        "Date_Month": "Date_Month",
        "Segment_Category_Name": "Segment_Category",
        # 顯式映射 Ad_Format 意圖，優先使用 ClickHouse 欄位
        "Ad_Format": ["ad_format_type_ch", "ad_format_type", "ad_format_type_id_ch", "ad_format_type_id", "Ad_Format"] # 優先級: CH string, CH ID, MySQL string
    }

    group_cols = []
    col_lower_map = {c.lower(): c for c in merged_df.columns}
    
    # 建立要聚合的 Segment 欄位列表 (如果在 Final GroupBy 中不需要分組，就要 Join 它)
    concat_cols = []

    for d in dimensions:
        target_aliases = intent_to_alias.get(d, [d]) # 現在可以是列表
        if not isinstance(target_aliases, list):
            target_aliases = [target_aliases]

        found_col = None
        for alias in target_aliases:
            if alias.lower() in col_lower_map:
                found_col = col_lower_map[alias.lower()]
                break # 找到最佳匹配，使用它

        if found_col and found_col not in group_cols: # 確保沒有重複
            group_cols.append(found_col)

    debug_logs.append(f"Final Group Cols: {group_cols}")

    # 定義數值欄位 (Metrics)
    exclude_cols_lower = {c.lower() for c in ['cmpid', 'id', 'start_date', 'end_date', 'schedule_dates']}
    for gc in group_cols:
        exclude_cols_lower.add(gc.lower())
        
    numeric_cols = [c for c in merged_df.columns 
                    if pd.api.types.is_numeric_dtype(merged_df[c]) 
                    and c.lower() not in exclude_cols_lower]
    
    debug_logs.append(f"Numeric Cols: {numeric_cols}")

    # 定義需要 Concatenate 的欄位 (非 Group Key, 非 Numeric, 但有價值的 Text)
    # 例如 Segment_Category (如果它不在 Group Key 裡)
    if seg_col and seg_col not in group_cols and seg_col in merged_df.columns:
        concat_cols.append(seg_col)

    if not group_cols:
        # Case A: Total (總計)
        if not numeric_cols and not concat_cols:
            final_df = merged_df 
            debug_logs.append("Mode: No Grouping, No Numeric, No Concat - Return Raw")
        else:
            # 分開計算以避免 Pandas agg 錯誤
            # 1. 數值取 SUM
            if numeric_cols:
                numeric_res = merged_df[numeric_cols].sum()
            else:
                numeric_res = pd.Series(dtype='float64')
            
            # 2. 文字取 Join
            def join_unique(x):
                # 確保轉成字串且去重
                return ', '.join(sorted(set([str(v) for v in x if v and str(v).lower() != 'nan'])))
            
            if concat_cols:
                text_res = merged_df[concat_cols].apply(join_unique)
            else:
                text_res = pd.Series(dtype='object')
                
            # 3. 合併結果
            final_series = pd.concat([numeric_res, text_res])
            final_df = final_series.to_frame().T
            final_df['Item'] = 'Total'
            debug_logs.append("Mode: Total Summary")
    else:
        # Case B: Group By Dimensions
        # 構建 Agg Dict
        agg_dict = {col: 'sum' for col in numeric_cols}
        def join_unique(x):
            return ', '.join(sorted(set([str(v) for v in x if v and str(v).lower() != 'nan'])))
        for c in concat_cols:
            agg_dict[c] = join_unique
            
        final_df = merged_df.groupby(group_cols).agg(agg_dict).reset_index()
        debug_logs.append(f"Mode: Group By {group_cols}")

    # 5. 後處理：移除不必要的欄位與過濾無效資料
    IGNORED_VALUES = ['Unknown', 'unknown', '']
    for col in group_cols:
        if col in final_df.columns:
            final_df = final_df[~final_df[col].astype(str).isin(IGNORED_VALUES)]

    cols_to_drop_lower = {c.lower() for c in ['cmpid', 'id', 'start_date', 'end_date', 'cmpid_ch', 'ad_format_type_id_ch', 'ad_format_type_id']}
    current_cols = list(final_df.columns)
    for col in current_cols:
        if col.lower() in cols_to_drop_lower and col not in group_cols:
            final_df = final_df.drop(columns=[col])

    # 6. 重算衍生指標 (Derived Metrics Calculation)
    # Identify columns flexibly using a helper function
    all_cols_lower = {c.lower(): c for c in final_df.columns}
    
    def find_col(keywords):
        for k in keywords:
            if k in all_cols_lower:
                return all_cols_lower[k]
        return None

    imp_col = find_col(['total_impressions', 'impression', 'impressions'])
    eff_imp_col = find_col(['effective_impressions'])
    click_col = find_col(['total_clicks', 'click_sum', 'clicks'])
    view100_col = find_col(['views_100', 'q100'])
    view3s_col = find_col(['views_3s', 'view3s'])
    eng_col = find_col(['total_engagements', 'eng'])
    
    # 1. CTR (Click-Through Rate) = Clicks / Effective Impressions * 100
    # Note: Prefer effective_impressions for CTR denominator if available
    ctr_denom_col = eff_imp_col if eff_imp_col else imp_col
    
    if click_col and ctr_denom_col:
         final_df['CTR'] = final_df.apply(
            lambda x: (x[click_col] / x[ctr_denom_col] * 100) if x[ctr_denom_col] > 0 else 0, axis=1
        ).round(2)
        
    # 2. VTR (View-Through Rate) = Completed Views (views_100) / Impressions * 100
    if view100_col and imp_col:
        final_df['VTR'] = final_df.apply(
            lambda x: (x[view100_col] / x[imp_col] * 100) if x[imp_col] > 0 else 0, axis=1
        ).round(2)
        
    # 3. ER (Engagement Rate) = Total Engagements / Impressions * 100
    if eng_col and imp_col:
        final_df['ER'] = final_df.apply(
            lambda x: (x[eng_col] / x[imp_col] * 100) if x[imp_col] > 0 else 0, axis=1
        ).round(2)

    # 7. 清理原始指標 (只保留比率)
    # 根據使用者需求，一般成效表格只需顯示 CTR, VTR, ER，因此移除用於計算的原始欄位
    raw_metrics_to_drop = [imp_col, eff_imp_col, click_col, view100_col, view3s_col, eng_col]
    # 過濾掉 None (沒找到的欄位)
    raw_metrics_to_drop = [c for c in raw_metrics_to_drop if c is not None]
    
    if raw_metrics_to_drop:
        final_df = final_df.drop(columns=raw_metrics_to_drop, errors='ignore')

    # 8. 條件式隱藏無效指標
    # 如果 VTR 全為 0 (表示本次查詢無影片相關數據)，則從結果中移除該欄位
    if 'VTR' in final_df.columns and (final_df['VTR'] == 0).all():
        final_df = final_df.drop(columns=['VTR'])

    # 將 Budget_Sum 轉為整數 (台幣無小數點)
    if 'Budget_Sum' in final_df.columns:
        final_df['Budget_Sum'] = final_df['Budget_Sum'].astype(int)

    # 將 Debug 資訊加入回傳
    return {
        "final_dataframe": final_df.to_dict('records'),
        "final_result_text": " | ".join(debug_logs)
    }
