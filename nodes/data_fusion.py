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
        
        # 1. 找出 Metric 欄位 (這些欄位在重複行中是重複的，取 mean/first)
        # 排除 ID, 日期
        exclude_cols_lower = {c.lower() for c in ['cmpid', 'id', 'start_date', 'end_date', 'schedule_dates', seg_col.lower()]}
        pre_numeric_cols = [c for c in df_mysql.columns 
                        if pd.api.types.is_numeric_dtype(df_mysql[c]) 
                        and c.lower() not in exclude_cols_lower]
        
        # 2. 找出 Group Keys (除了 Segment 以外的所有欄位)
        # 這樣可以保留 cmpid, Agency, Format 等資訊
        group_keys = [c for c in df_mysql.columns if c != seg_col and c not in pre_numeric_cols]
        
        if group_keys:
            # 定義聚合邏輯
            agg_dict = {col: 'first' for col in pre_numeric_cols} # 數值取 first (避免重複加總)
            # Segment 用 join
            def join_unique(x):
                return ', '.join(sorted(set([str(v) for v in x if v and str(v).lower() != 'nan'])))
            agg_dict[seg_col] = join_unique
            
            # 執行 Pre-Aggregation
            df_mysql = df_mysql.groupby(group_keys).agg(agg_dict).reset_index()
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
        "Ad_Format": "Ad_Format", 
        "Industry": "Industry", 
        "廣告計價單位": "Pricing_Unit",
        "Date_Month": "Date_Month",
        "Segment_Category_Name": "Segment_Category"
    }

    group_cols = []
    col_lower_map = {c.lower(): c for c in merged_df.columns}
    
    # 建立要聚合的 Segment 欄位列表 (如果在 Final GroupBy 中不需要分組，就要 Join 它)
    concat_cols = []

    for d in dimensions:
        target_alias = intent_to_alias.get(d, d)
        found_col = None
        
        if target_alias.lower() in col_lower_map:
            found_col = col_lower_map[target_alias.lower()]
        elif d.lower() in col_lower_map:
            found_col = col_lower_map[d.lower()]
            
        if found_col:
            # 特殊處理：如果 dimension 是 Segment_Category，且我們已經做過 Pre-Aggregation
            # 這裡還是可以 Group By 它 (如果使用者想依 Segment 分組)
            # 但如果使用者想看 Format 並列出 Segment，那 Segment 應該不在 dimensions 裡?
            # 不，如果 dimensions 有 Segment，代表要 Group By Segment。
            # 如果 dimensions 沒有 Segment，但 merged_df 有，它會被視為 Metric 嗎? 不會。
            # 
            # 如果我們希望在 Group By Format 時保留 Segment 資訊 (Join)，
            # 那 Segment 不應該在 group_cols 裡，而應該在 concat_cols 裡。
            # 但目前的 dimensions 來自 Intent，如果 Intent 沒說要 Segment，我們就丟棄它?
            # 為了讓資訊更豐富，如果 Segment 存在但不在 dimensions，我們可以把它加入 concat_cols
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

    cols_to_drop_lower = {c.lower() for c in ['start_date', 'end_date', 'cmpid', 'id']}
    current_cols = list(final_df.columns)
    for col in current_cols:
        if col.lower() in cols_to_drop_lower and col not in group_cols:
            final_df = final_df.drop(columns=[col])

    # 6. 重算衍生指標 (CTR, CPC)
    imp_col = next((c for c in final_df.columns if c in ['effective_impressions', 'Impression_Sum', 'impressions']), None)
    click_col = next((c for c in final_df.columns if c in ['total_clicks', 'Click_Sum', 'clicks']), None)
    budget_col = next((c for c in final_df.columns if c in ['Budget_Sum', 'total_budget', 'media_budget', 'budget', '媒體預算']), None)

    if imp_col and click_col:
        final_df['CTR'] = final_df.apply(
            lambda x: (x[click_col] / x[imp_col] * 100) if x[imp_col] > 0 else 0, axis=1
        ).round(2)

    if budget_col and click_col:
        final_df['CPC'] = final_df.apply(
            lambda x: (x[budget_col] / x[click_col]) if x[click_col] > 0 else 0, axis=1
        ).round(2)

    # 將 Debug 資訊加入回傳
    return {
        "final_dataframe": final_df.to_dict('records'),
        "final_result_text": " | ".join(debug_logs)
    }
