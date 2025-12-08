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

    # -----------------------------------------------------------
    # Column Name Normalization (Fix for KeyError: 'cmpid')
    # -----------------------------------------------------------
    # Normalize MySQL columns
    mysql_rename_map = {}
    for col in df_mysql.columns:
        if col.lower() == 'cmpid':
            mysql_rename_map[col] = 'cmpid'
        elif col.lower() == 'id' and 'cmpid' not in [c.lower() for c in df_mysql.columns]:
             mysql_rename_map[col] = 'cmpid'
        # Normalize ad_format_type_id if present
        elif 'ad_format_type_id' in col.lower():
             mysql_rename_map[col] = 'ad_format_type_id'
             
    if mysql_rename_map:
        df_mysql.rename(columns=mysql_rename_map, inplace=True)
        
    # Ensure 'cmpid' is present
    if 'cmpid' not in df_mysql.columns:
        debug_logs.append("CRITICAL WARNING: 'cmpid' column missing in MySQL result. Using first column as cmpid fallback.")
        if not df_mysql.empty:
            df_mysql.rename(columns={df_mysql.columns[0]: 'cmpid'}, inplace=True)

    # Normalize CH columns
    if not df_ch.empty:
        ch_rename_map = {}
        for col in df_ch.columns:
            if col.lower() == 'cmpid':
                ch_rename_map[col] = 'cmpid'
            elif 'ad_format_type_id' in col.lower():
                ch_rename_map[col] = 'ad_format_type_id'
        if ch_rename_map:
            df_ch.rename(columns=ch_rename_map, inplace=True)

    # Helper: 安全的數值轉型函式
    def safe_numeric_convert(df, name="df"):
        for col in df.columns:
            col_lower = col.lower()
            if col_lower in ['cmpid', 'id', 'ad_format_type_id']: continue
            
            # 強制嘗試轉換包含 'budget', 'sum', 'price', 'count' 的欄位
            is_metric_candidate = any(k in col_lower for k in ['budget', 'sum', 'price', 'count', 'impression', 'click', 'view'])
            
            if is_metric_candidate:
                 # 先移除可能的千分位逗號
                if df[col].dtype == 'object':
                    df[col] = df[col].astype(str).str.replace(',', '', regex=False)
            
            converted = pd.to_numeric(df[col], errors='coerce')
            
            # 如果轉換後全是 NaN，但原本不是全空，則保留原值 (可能是純文字欄位)
            # 但對於 metric candidates，我們傾向於認為它是數值，保留 NaN 也比錯誤的文字好
            if converted.isna().all() and df[col].notna().any() and not is_metric_candidate:
                continue 
            
            # 覆蓋
            df[col] = converted
        return df

    df_mysql = safe_numeric_convert(df_mysql, "MySQL")
    if not df_ch.empty:
        df_ch = safe_numeric_convert(df_ch, "CH")

    # DEBUG: Check Total Budget from Raw SQL Data
    raw_budget_total = 0
    budget_col = next((c for c in df_mysql.columns if 'budget' in c.lower()), None)
    if budget_col:
        raw_budget_total = df_mysql[budget_col].sum()
        debug_logs.append(f"DEBUG: Raw SQL Budget Total: {raw_budget_total:,.0f}")

    # Ensure ID columns are numeric/consistent
    for df in [df_mysql, df_ch]:
        if 'cmpid' in df.columns:
            df['cmpid'] = pd.to_numeric(df['cmpid'], errors='coerce')
        if 'ad_format_type_id' in df.columns:
            df['ad_format_type_id'] = pd.to_numeric(df['ad_format_type_id'], errors='coerce')

    # STRING NORMALIZATION: Strip whitespace from all object columns to prevent GroupBy fragmentation
    for col in df_mysql.columns:
        if df_mysql[col].dtype == 'object':
            df_mysql[col] = df_mysql[col].astype(str).str.strip()
    
    # ============================================================
    # Pre-Aggregation
    # ============================================================
    seg_col_candidates = ['Segment_Category', 'Segment_Category_Name', 'segment_category', '數據鎖定']
    seg_col = next((c for c in df_mysql.columns if c in seg_col_candidates), None)

    if seg_col:
        debug_logs.append(f"Found Segment Column: {seg_col}. Performing Pre-Aggregation.")
        
        def join_unique_func(x):
            return '; '.join(sorted(set([str(v) for v in x if v and str(v).lower() != 'nan'])))

        exclude_keywords = ['schedule_dates', 'id', 'date_month']
        
        # Group by EVERYTHING except segment and exclude_keywords
        group_keys = ['cmpid']
        if 'ad_format_type_id' in df_mysql.columns:
            group_keys.append('ad_format_type_id')

        for col in df_mysql.columns:
            if col in group_keys: continue # Already added
            if col == seg_col: continue
            if pd.api.types.is_numeric_dtype(df_mysql[col]): continue 
            if any(k in col.lower() for k in exclude_keywords): continue
            group_keys.append(col)
            
        debug_logs.append(f"Pre-Agg Group Keys: {group_keys}")
        
        agg_dict_pre = {}
        agg_dict_pre[seg_col] = join_unique_func
        
        for col in df_mysql.columns:
            if col in group_keys or col == seg_col: continue
            
            # Critical Fix for Budget duplication
            if 'budget' in col.lower():
                agg_dict_pre[col] = 'max' 
            elif pd.api.types.is_numeric_dtype(df_mysql[col]):
                agg_dict_pre[col] = 'mean'
            else:
                agg_dict_pre[col] = 'first'

        # CRITICAL FIX: dropna=False is required to keep rows where ad_format_type_id is NaN/NULL
        df_mysql = df_mysql.groupby(group_keys, as_index=False, dropna=False).agg(agg_dict_pre)

    # -----------------------------------------------------------
    # Strict MySQL Column Filtering BEFORE Merge
    # -----------------------------------------------------------
    raw_analysis_needs = state.get('analysis_needs')
    if hasattr(raw_analysis_needs, 'model_dump'):
        analysis_needs = raw_analysis_needs.model_dump()
    elif hasattr(raw_analysis_needs, 'dict'):
        analysis_needs = raw_analysis_needs.dict()
    elif isinstance(raw_analysis_needs, dict):
        analysis_needs = raw_analysis_needs
    else:
        analysis_needs = {}
    
    requested_dims = analysis_needs.get('dimensions', [])
    dim_protection_list = [d.lower() for d in requested_dims]
    if 'campaign_name' in dim_protection_list: dim_protection_list.append('campaign_name')
    if 'date_month' in dim_protection_list: dim_protection_list.append('date_month')
    if 'date_year' in dim_protection_list: dim_protection_list.append('date_year')

    mysql_cols_to_keep_for_merge = ['cmpid']
    if 'ad_format_type_id' in df_mysql.columns:
        mysql_cols_to_keep_for_merge.append('ad_format_type_id')
    if seg_col and seg_col in df_mysql.columns:
        mysql_cols_to_keep_for_merge.append(seg_col)
    
    strict_exclude_keywords = ['schedule_dates', 'id', 'date_month', 'date_year'] 
    
    for col in df_mysql.columns:
        if col in mysql_cols_to_keep_for_merge: continue
        col_lower = col.lower()
        
        if col_lower in dim_protection_list:
            mysql_cols_to_keep_for_merge.append(col)
            continue

        if any(k in col_lower for k in strict_exclude_keywords) and col_lower != 'cmpid':
            continue
            
        if pd.api.types.is_numeric_dtype(df_mysql[col]):
            mysql_cols_to_keep_for_merge.append(col)
            continue
            
        mysql_cols_to_keep_for_merge.append(col)
    
    df_mysql = df_mysql[mysql_cols_to_keep_for_merge]
    debug_logs.append(f"MySQL Cols After Pre-Merge Filter: {list(df_mysql.columns)}")

    # ============================================================
    # 3. 合併 (Merge) - Dynamic Merge Keys
    # ============================================================
    merge_on = ['cmpid']
    if not df_ch.empty and 'ad_format_type_id' in df_ch.columns and 'ad_format_type_id' in df_mysql.columns:
        merge_on.append('ad_format_type_id')
        debug_logs.append("Using Composite Merge Key: ['cmpid', 'ad_format_type_id']")
    else:
        debug_logs.append("Using Simple Merge Key: ['cmpid']")

    if not df_ch.empty:
        merged_df = pd.merge(df_mysql, df_ch, on=merge_on, how='left', suffixes=('', '_ch'))
    else:
        merged_df = df_mysql

    merged_df = merged_df.fillna(0)
    
    # DEBUG: Check Budget After Merge
    merge_budget_total = 0
    budget_col_merge = next((c for c in merged_df.columns if 'budget' in c.lower()), None)
    if budget_col_merge:
        merge_budget_total = merged_df[budget_col_merge].sum()
        debug_logs.append(f"DEBUG: Post-Merge Budget Total: {merge_budget_total:,.0f}")

    debug_logs.append(f"Merged Cols: {list(merged_df.columns)}")

    # 4. 二次聚合 (Re-aggregation)
    dimensions = analysis_needs.get('dimensions', [])
    
    intent_to_alias = {
        "Agency": "Agency",
        "Brand": "Brand",
        "Advertiser": "Advertiser",
        "Campaign_Name": "Campaign_Name",
        "Industry": "Industry", 
        "廣告計價單位": "Pricing_Unit",
        "Date_Month": "Date_Month",
        "Date_Year": "Date_Year",
        "Segment_Category_Name": "Segment_Category",
        # Fixed Priority: Title (Ad_Format) > ID to ensure titles are used for grouping and display
        "Ad_Format": ["Ad_Format", "ad_format_type_ch", "ad_format_type", "ad_format_type_id_ch", "ad_format_type_id"] 
    }

    group_cols = []
    col_lower_map = {c.lower(): c for c in merged_df.columns}
    
    concat_cols = []

    for d in dimensions:
        target_aliases = intent_to_alias.get(d, [d])
        if not isinstance(target_aliases, list):
            target_aliases = [target_aliases]

        found_col = None
        for alias in target_aliases:
            if alias.lower() in col_lower_map:
                found_col = col_lower_map[alias.lower()]
                break 

        if found_col and found_col not in group_cols:
            group_cols.append(found_col)

    debug_logs.append(f"Final Group Cols: {group_cols}")

    exclude_cols_lower = {c.lower() for c in ['cmpid', 'id', 'start_date', 'end_date', 'schedule_dates']}
    for gc in group_cols:
        exclude_cols_lower.add(gc.lower())
        
    numeric_cols = [c for c in merged_df.columns 
                    if pd.api.types.is_numeric_dtype(merged_df[c]) 
                    and c.lower() not in exclude_cols_lower]
    
    debug_logs.append(f"Numeric Cols: {numeric_cols}")

    if seg_col and seg_col not in group_cols and seg_col in merged_df.columns:
        concat_cols.append(seg_col)

    if not group_cols:
        # Case A: Total
        if not numeric_cols and not concat_cols:
            final_df = merged_df 
        else:
            if numeric_cols:
                numeric_res = merged_df[numeric_cols].sum()
            else:
                numeric_res = pd.Series(dtype='float64')
            
            def join_unique(x):
                return '; '.join(sorted(set([str(v) for v in x if v and str(v).lower() != 'nan'])))
            
            if concat_cols:
                text_res = merged_df[concat_cols].apply(join_unique)
            else:
                text_res = pd.Series(dtype='object')
                
            final_series = pd.concat([numeric_res, text_res])
            final_df = final_series.to_frame().T
            final_df['Item'] = 'Total'
    else:
    # Case B: Group By Dimensions
            agg_dict = {col: 'sum' for col in numeric_cols}
            
            # Explicitly force SUM for known metric columns if they exist, regardless of type detection
            for col in merged_df.columns:
                col_lower = col.lower()
                if 'budget' in col_lower or 'sum' in col_lower:
                     if col not in group_cols and col not in agg_dict:
                         # Try to convert again just in case
                         merged_df[col] = pd.to_numeric(merged_df[col], errors='coerce').fillna(0)
                         agg_dict[col] = 'sum'
                         
            # Preserve Date Columns if they exist
            for date_col in ['start_date', 'end_date']:
                if date_col in merged_df.columns and date_col not in group_cols:
                    agg_dict[date_col] = 'max'
        
            def join_unique(x):            
                return '; '.join(sorted(set([str(v) for v in x if v and str(v).lower() != 'nan'])))
        
            for c in concat_cols:
                agg_dict[c] = join_unique
                
            # CRITICAL FIX: Also use dropna=False here to preserve groups with NaN keys (if any ID keys remain)
            if not agg_dict:
                final_df = merged_df[group_cols].drop_duplicates().reset_index(drop=True)
            else:
                final_df = merged_df.groupby(group_cols, dropna=False).agg(agg_dict).reset_index()

    # DEBUG: Check Budget After Aggregation
    agg_budget_total = 0
    budget_col_agg = next((c for c in final_df.columns if 'budget' in c.lower()), None)
    if budget_col_agg:
        agg_budget_total = final_df[budget_col_agg].sum()
        debug_logs.append(f"DEBUG: Post-Agg Budget Total: {agg_budget_total:,.0f}")

    # 5. 重算衍生指標
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
    
    if click_col and imp_col:
        final_df['CTR'] = final_df.apply(
            lambda x: (x[click_col] / x[imp_col] * 100) if x[imp_col] > 0 else 0, axis=1
        ).round(2)
        
    if view3s_col and imp_col:
        final_df['VTR'] = final_df.apply(
            lambda x: (x[view3s_col] / x[imp_col] * 100) if x[imp_col] > 0 else 0, axis=1
        ).round(2)
        
    if eng_col and imp_col:
        final_df['ER'] = final_df.apply(
            lambda x: (x[eng_col] / x[imp_col] * 100) if x[imp_col] > 0 else 0, axis=1
        ).round(2)

    # 6. 後處理
    IGNORED_VALUES = ['Unknown', 'unknown', '', '0', 0]
    for col in group_cols:
        if col in final_df.columns:
            final_df = final_df[~final_df[col].isin(IGNORED_VALUES)]
            final_df = final_df[~final_df[col].astype(str).isin([str(v) for v in IGNORED_VALUES])]
    
    ad_format_col = next((c for c in final_df.columns if 'ad_format' in c.lower() and c != 'ad_format_type_id'), None)
    if ad_format_col and ad_format_col in final_df.columns:
        final_df = final_df[~final_df[ad_format_col].astype(str).isin(['0', 0])]

    # Strict Column Filtering
    cols_to_keep = []
    
    for dim in group_cols:
        if dim in final_df.columns:
            cols_to_keep.append(dim)

    if seg_col and seg_col in final_df.columns and seg_col not in cols_to_keep:
        cols_to_keep.append(seg_col)

    requested_metrics_lower = [m.lower() for m in analysis_needs.get('metrics', [])]
    
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
            match = next((c for c in final_df.columns if cand in c.lower()), None)
            if match and match not in cols_to_keep:
                cols_to_keep.append(match)
                
    if not cols_to_keep: 
         match = next((c for c in final_df.columns if 'budget' in c.lower()), None)
         if match: cols_to_keep.append(match)

    kpi_whitelist = ['CTR', 'VTR', 'ER']
    for kpi in kpi_whitelist:
        if kpi in final_df.columns:
             if (final_df[kpi] == 0).all(): continue
             if kpi not in cols_to_keep:
                cols_to_keep.append(kpi)
                
    # CONDITIONAL KEEP DATES: Only keep start_date/end_date if Campaign-level dimensions are in group_cols
    # This prevents showing misleading campaign-level dates when aggregated by month/advertiser.
    if any(dim in group_cols for dim in ['Campaign_Name', 'cmpid']):
        for date_col in ['start_date', 'end_date']:
            if date_col in final_df.columns and date_col not in cols_to_keep:
                cols_to_keep.append(date_col)

    if cols_to_keep:
        final_df = final_df[cols_to_keep]
    
    # 6.5 排序 & Limit
    calc_type = analysis_needs.get('calculation_type', 'Total')
    
    if calc_type == 'Ranking':
        sort_col = None
        
        # Strategy 1: Use explicitly requested metrics (Smart Priority)
        if requested_metrics_lower:
            # Check if any KPI is requested, prioritize Rate metrics over Volume metrics for "Ranking"
            kpi_candidates = ['ctr', 'vtr', 'er']
            found_kpi = None
            for req in requested_metrics_lower:
                if any(k in req for k in kpi_candidates):
                    found_kpi = req
                    break
            
            target_metric = found_kpi if found_kpi else requested_metrics_lower[0]
            
            # Map generic terms to specific columns
            candidates = metric_map.get(target_metric, [target_metric])
            
            # Smart Mapping for common abbreviations
            if 'ctr' in target_metric: candidates = ['CTR']
            if 'vtr' in target_metric: candidates = ['VTR']
            if 'er' in target_metric: candidates = ['ER']
            
            for cand in candidates:
                match = next((c for c in final_df.columns if cand.lower() in c.lower()), None)
                if match:
                    sort_col = match
                    break
        
        # Strategy 2: Smart Defaults for "Performance" (Qualitative > Quantitative)
        if not sort_col:
            # Priority: CTR > VTR > ER > Clicks > Impressions
            kpi_priority = ['CTR', 'VTR', 'ER']
            for kpi in kpi_priority:
                if kpi in final_df.columns:
                    sort_col = kpi
                    break
        
        # Strategy 3: Quantitative Fallback
        if not sort_col:
            qty_priority = ['total_clicks', 'clicks', 'total_impressions', 'impressions']
            for qty in qty_priority:
                match = next((c for c in final_df.columns if qty in c.lower()), None)
                if match:
                    sort_col = match
                    break

        # Strategy 4: Budget Fallback
        if not sort_col:
            sort_col = next((c for c in final_df.columns if 'budget' in c.lower()), None)
            
        if sort_col:
            debug_logs.append(f"Sorting by {sort_col} (Descending) for Ranking")
            final_df = final_df.sort_values(by=sort_col, ascending=False)
            
    elif calc_type == 'Trend':
        date_col = next((c for c in final_df.columns if 'date' in c.lower() or 'month' in c.lower()), None)
        if date_col:
            debug_logs.append(f"Sorting by {date_col} (Ascending) for Trend")
            final_df = final_df.sort_values(by=date_col, ascending=True)

    limit = state.get('limit')
    if limit and isinstance(limit, int) and limit > 0:
        debug_logs.append(f"Applying Limit: Top {limit}")
        final_df = final_df.head(limit)

    # 7. Final Formatting
    for col in final_df.columns:
        if 'budget' in col.lower() and pd.api.types.is_numeric_dtype(final_df[col]):
             final_df[col] = final_df[col].fillna(0).astype(int)

    # Reorder Columns: Campaign Name -> Dates -> Format -> Segment -> Metrics
    preferred_order = ['Campaign_Name', 'start_date', 'end_date', 'Ad_Format', 'Segment_Category', 'Segment_Category_Name']
    new_cols = []
    
    # Add preferred columns if they exist
    for p_col in preferred_order:
        match = next((c for c in final_df.columns if c.lower() == p_col.lower()), None)
        if match:
            new_cols.append(match)
            
    # Add remaining columns
    for col in final_df.columns:
        if col not in new_cols:
            new_cols.append(col)
            
    final_df = final_df[new_cols]

    # Generate Budget Note
    query_level = state.get("query_level", "strategy")
    budget_note = ""
    if query_level == "contract":
        budget_note = "這是合約層級的進單金額 (Booking Amount)，不包含執行細節。"
    elif query_level in ["execution", "strategy", "audience"]:
        budget_note = "這是系統設定的執行預算上限 (Execution Budget)。"

    return {
        "final_dataframe": final_df.to_dict('records'),
        "final_result_text": f"MySQL Rows: {len(df_mysql)} | " + " | ".join(debug_logs),
        "budget_note": budget_note
    }
