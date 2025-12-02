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
        # Modified to use semicolon for separation to ensure Markdown table compatibility
        def join_unique_func(x):
            return '; '.join(sorted(set([str(v) for v in x if v and str(v).lower() != 'nan'])))

        # 定義 Group Key: 必須是能夠唯一識別 Campaign 的欄位，加上其他維度
        # 1. 核心 Key: cmpid
        # 2. 其他維度: Agency, Ad_Format, Campaign_Name 等
        # 3. 排除: start_date, end_date (日期會導致分組過細), id (內部ID), segment (要被聚合的)
        
        exclude_keywords = ['start_date', 'end_date', 'schedule_dates', 'id', 'date_month'] # Exclude dates from pre-agg grouping to avoid fragmentation
        
        group_keys = ['cmpid']
        for col in df_mysql.columns:
            if col.lower() == 'cmpid': continue
            if col == seg_col: continue
            if pd.api.types.is_numeric_dtype(df_mysql[col]): continue # Don't group by metrics
            
            # 如果欄位包含 exclude keywords，跳過
            if any(k in col.lower() for k in exclude_keywords):
                continue
                
            group_keys.append(col)
            
        debug_logs.append(f"Pre-Agg Group Keys: {group_keys}")
        
        # 定義 Agg Logic
        agg_dict_pre = {}
        # Segment -> Join
        agg_dict_pre[seg_col] = join_unique_func
        
        # Metrics -> Sum/Mean
        for col in df_mysql.columns:
            if col in group_keys or col == seg_col: continue
            
            if col.lower() == 'budget_sum':
                agg_dict_pre[col] = 'sum'
            elif pd.api.types.is_numeric_dtype(df_mysql[col]):
                agg_dict_pre[col] = 'mean' # default for others
            else:
                agg_dict_pre[col] = 'first' # Date columns etc. -> Take first

        # 執行 Pre-Aggregation
        df_mysql = df_mysql.groupby(group_keys, as_index=False).agg(agg_dict_pre)
        debug_logs.append(f"Pre-Aggregated MySQL Rows: {len(df_mysql)}")
        debug_logs.append(f"Pre-Aggregated MySQL Cols: {list(df_mysql.columns)}")

    # Strict MySQL Column Filtering BEFORE Merge with ClickHouse
    # Only keep 'cmpid', 'seg_col' (if present), numeric columns (Metrics), AND potential Grouping Dimensions.
    # We MUST NOT drop dimensions like 'Campaign_Name', 'Ad_Format', 'Agency' here, otherwise final grouping fails.
    
    mysql_cols_to_keep_for_merge = ['cmpid']
    if seg_col and seg_col in df_mysql.columns:
        mysql_cols_to_keep_for_merge.append(seg_col)
    
    # Identify potential dimensions to keep (String columns that are not in exclude list)
    # We reuse 'exclude_keywords' from above but make it strict for cleaning
    strict_exclude_keywords = ['start_date', 'end_date', 'schedule_dates', 'id', 'date_month', 'date_year'] 
    
    for col in df_mysql.columns:
        if col in mysql_cols_to_keep_for_merge: continue
        
        col_lower = col.lower()
        # 1. If it's a known excluded column, skip
        if any(k in col_lower for k in strict_exclude_keywords) and col_lower != 'cmpid':
            continue
            
        # 2. If it's numeric (Metric), keep it
        if pd.api.types.is_numeric_dtype(df_mysql[col]):
            mysql_cols_to_keep_for_merge.append(col)
            continue
            
        # 3. If it's a string/object (Dimension), keep it! (Crucial Fix)
        # This ensures 'Campaign_Name', 'Agency' etc. survive the merge.
        mysql_cols_to_keep_for_merge.append(col)
    
    # Filter df_mysql to only include these essential columns before merging
    df_mysql = df_mysql[mysql_cols_to_keep_for_merge]
    debug_logs.append(f"MySQL Cols After Pre-Merge Filter: {list(df_mysql.columns)}")

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
                return '; '.join(sorted(set([str(v) for v in x if v and str(v).lower() != 'nan'])))
            
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
            return '; '.join(sorted(set([str(v) for v in x if v and str(v).lower() != 'nan'])))
        for c in concat_cols:
            agg_dict[c] = join_unique
            
        if not agg_dict:
            # 如果沒有需要聚合的指標 (agg_dict 為空)，直接回傳去重後的 Dimensions
            final_df = merged_df[group_cols].drop_duplicates().reset_index(drop=True)
            debug_logs.append(f"Mode: Group By {group_cols} (No Metrics)")
        else:
            final_df = merged_df.groupby(group_cols).agg(agg_dict).reset_index()
            debug_logs.append(f"Mode: Group By {group_cols}")

    # 5. 重算衍生指標 (Derived Metrics Calculation) - Moved UP
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
    
    # 1. CTR (Click-Through Rate)
    ctr_denom_col = eff_imp_col if eff_imp_col else imp_col
    if click_col and ctr_denom_col:
         final_df['CTR'] = final_df.apply(
            lambda x: (x[click_col] / x[ctr_denom_col] * 100) if x[ctr_denom_col] > 0 else 0, axis=1
        ).round(2)
        
    # 2. VTR (View-Through Rate)
    if view100_col and imp_col:
        final_df['VTR'] = final_df.apply(
            lambda x: (x[view100_col] / x[imp_col] * 100) if x[imp_col] > 0 else 0, axis=1
        ).round(2)
        
    # 3. ER (Engagement Rate)
    if eng_col and imp_col:
        final_df['ER'] = final_df.apply(
            lambda x: (x[eng_col] / x[imp_col] * 100) if x[imp_col] > 0 else 0, axis=1
        ).round(2)

    # 6. 後處理：移除不必要的欄位與過濾無效資料 (Strict Filtering)
    # Fixed: Added '0' and 0 to ignored values list
    IGNORED_VALUES = ['Unknown', 'unknown', '', '0', 0]
    for col in group_cols:
        if col in final_df.columns:
            # Convert to string for comparison but handle original 0 integer
            final_df = final_df[~final_df[col].isin(IGNORED_VALUES)]
            final_df = final_df[~final_df[col].astype(str).isin([str(v) for v in IGNORED_VALUES])]
    
    # After all filtering, also filter rows where Ad_Format is '0'
    ad_format_col = next((c for c in final_df.columns if 'ad_format' in c.lower() and c != 'ad_format_type_id'), None)
    if ad_format_col and ad_format_col in final_df.columns:
        final_df = final_df[~final_df[ad_format_col].astype(str).isin(['0', 0])]


    # Strict Column Filtering: Only keep Dimensions + Calculated Metrics + Explicit Metrics
    cols_to_keep = []
    
    # A. Dimensions (Grouping Keys)
    for dim in group_cols:
        if dim in final_df.columns:
            cols_to_keep.append(dim)

    # B. Segment Column (if it was concatenated and exists)
    if seg_col and seg_col in final_df.columns and seg_col not in cols_to_keep:
        cols_to_keep.append(seg_col)

    # C. Explicit Metrics (Budget, Count, Price)
    # Only keep metrics that were actually requested in 'metrics' or are essential summaries
    requested_metrics_lower = [m.lower() for m in analysis_needs.get('metrics', [])]
    
    # Map specific requested metrics to DataFrame columns (loose matching)
    metric_map = {
        'budget_sum': ['budget', 'budget_sum'],
        'campaign_count': ['campaign_count', 'count'],
        'adprice_sum': ['price', 'adprice_sum', 'uniprice'],
        'impression_sum': ['impression', 'total_impressions', 'impressions'],
        'click_sum': ['click', 'total_clicks', 'clicks'],
        'view3s_sum': ['view3s', 'views_3s'],
        'q100_sum': ['q100', 'views_100']
    }

    for req_m in requested_metrics_lower:
        candidates = metric_map.get(req_m, [req_m])
        for cand in candidates:
            # Find matching column
            match = next((c for c in final_df.columns if cand in c.lower()), None)
            if match and match not in cols_to_keep:
                cols_to_keep.append(match)
                
    # Always keep Budget if strictly aggregating Total/Overview to avoid empty tables
    if not cols_to_keep: 
         match = next((c for c in final_df.columns if 'budget' in c.lower()), None)
         if match: cols_to_keep.append(match)

    # D. Calculated KPIs (CTR, VTR, ER)
    # Always show calculated KPIs if they exist and have non-zero values
    # This allows seeing performance metrics even if not explicitly requested
    kpi_whitelist = ['CTR', 'VTR', 'ER']
    for kpi in kpi_whitelist:
        if kpi in final_df.columns:
             # Filter out if all values are 0 (e.g. VTR for banner ads)
             if (final_df[kpi] == 0).all(): continue
             if kpi not in cols_to_keep:
                cols_to_keep.append(kpi)

    # Apply Selection - But ensure we don't return empty dataframe if logic fails
    if cols_to_keep:
        final_df = final_df[cols_to_keep]
    
    # ============================================================
    # 6.5 排序 (Sorting Logic) & Limit Truncation
    # ============================================================
    calc_type = analysis_needs.get('calculation_type', 'Total')
    
    if calc_type == 'Ranking':
        # Sort by the first requested metric (or Budget if none specified)
        sort_col = None
        if requested_metrics_lower:
            # Try to find the column name in final_df that matches the first requested metric
            first_req = requested_metrics_lower[0]
            
            # Use our metric map logic again or just search
            # 1. Check metric_map
            candidates = metric_map.get(first_req, [first_req])
            # 2. Check calculated metrics
            if 'ctr' in first_req: candidates = ['CTR']
            if 'vtr' in first_req: candidates = ['VTR']
            if 'er' in first_req: candidates = ['ER']
            
            for cand in candidates:
                match = next((c for c in final_df.columns if cand.lower() in c.lower()), None)
                if match:
                    sort_col = match
                    break
        
        # Fallback to Budget
        if not sort_col:
            sort_col = next((c for c in final_df.columns if 'budget' in c.lower()), None)
            
        if sort_col:
            debug_logs.append(f"Sorting by {sort_col} (Descending) for Ranking")
            final_df = final_df.sort_values(by=sort_col, ascending=False)
            
    elif calc_type == 'Trend':
        # Sort by Date dimension
        date_col = next((c for c in final_df.columns if 'date' in c.lower() or 'month' in c.lower()), None)
        if date_col:
            debug_logs.append(f"Sorting by {date_col} (Ascending) for Trend")
            final_df = final_df.sort_values(by=date_col, ascending=True)

    # Universal Limit Application (Moved outside of if-calc_type block)
    # This ensures limit applies to 'Total' or 'Comparison' modes as well if specified
    limit = state.get('limit')
    if limit and isinstance(limit, int) and limit > 0:
        debug_logs.append(f"Applying Limit: Top {limit}")
        final_df = final_df.head(limit)

    # 7. Final Formatting (Integer for Budget)
    for col in final_df.columns:
        if 'budget' in col.lower() and pd.api.types.is_numeric_dtype(final_df[col]):
             final_df[col] = final_df[col].fillna(0).astype(int)

    # 將 Debug 資訊加入回傳
    return {
        "final_dataframe": final_df.to_dict('records'),
        "final_result_text": " | ".join(debug_logs)
    }
