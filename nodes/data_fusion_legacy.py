from schemas.state import AgentState
from config.registry import config
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
    mysql_data = state.get('sql_result')
    sql_result_columns = state.get('sql_result_columns')
    
    # Fallback to campaign_data (Single Path Execution)
    if not mysql_data:
        campaign_data = state.get('campaign_data')
        if campaign_data:
            mysql_data = campaign_data.get('data')
            sql_result_columns = campaign_data.get('columns')

    ch_data = state.get('clickhouse_result', [])

    if not mysql_data or not sql_result_columns:
        return {"final_dataframe": None, "final_result_text": "查無數據 (MySQL 無回傳)。"}

    # 2. 資料前處理 (Preprocessing)
    debug_logs.append(f"Raw MySQL Cols: {sql_result_columns}")
    df_mysql = pd.DataFrame(mysql_data, columns=sql_result_columns)
    df_ch = pd.DataFrame(ch_data) if ch_data else pd.DataFrame()

    # -----------------------------------------------------------
    # Column Name Standardization (Global Lowercase)
    # -----------------------------------------------------------
    # Force all columns to lowercase to prevent duplicates (e.g. 'CTR' vs 'ctr')
    # and ensure consistent mapping logic.
    df_mysql.columns = df_mysql.columns.str.lower()
    if not df_ch.empty:
        df_ch.columns = df_ch.columns.str.lower()
    
    debug_logs.append(f"Standardized MySQL Cols: {list(df_mysql.columns)}")

    # -----------------------------------------------------------
    # Column Name Normalization (Fix for KeyError: 'cmpid')
    # -----------------------------------------------------------
    # Normalize MySQL columns
    mysql_rename_map = {}
    for col in df_mysql.columns:
        if col == 'cmpid': # Already lowercased
            mysql_rename_map[col] = 'cmpid'
        elif col == 'id' and 'cmpid' not in df_mysql.columns:
             mysql_rename_map[col] = 'cmpid'
        # Normalize ad_format_type_id if present
        elif 'ad_format_type_id' in col:
             mysql_rename_map[col] = 'ad_format_type_id'
             
    if mysql_rename_map:
        df_mysql.rename(columns=mysql_rename_map, inplace=True)
            
    if not df_ch.empty:
        ch_rename_map = {}
        for col in df_ch.columns:
            if col == 'cmpid':
                ch_rename_map[col] = 'cmpid'
            elif 'ad_format_type_id' in col:
                ch_rename_map[col] = 'ad_format_type_id'
        if ch_rename_map:
            df_ch.rename(columns=ch_rename_map, inplace=True)

    # Helper: 安全的數值轉型函式
    def safe_numeric_convert(df, name="df"):
        for col in df.columns:
            # col is already lowercase
            if col in ['cmpid', 'id', 'ad_format_type_id']: continue
            
            # 強制嘗試轉換包含 'budget', 'sum', 'price', 'count' 的欄位
            is_metric_candidate = any(k in col for k in ['budget', 'sum', 'price', 'count', 'impression', 'click', 'view'])
            
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
    seg_col_candidates = config.get_segment_column_candidates()
    seg_col = next((c for c in df_mysql.columns if c in seg_col_candidates), None)

    if seg_col:
        debug_logs.append(f"Found Segment Column: {seg_col}. Performing Pre-Aggregation.")
        
        def join_unique_func(x):
            return '; '.join(sorted(set([str(v) for v in x if v and str(v).lower() != 'nan'])))

        exclude_keywords = config.get_exclude_keywords()
        
        # Group by EVERYTHING except segment and exclude_keywords
        group_keys = []
        if 'cmpid' in df_mysql.columns: group_keys.append('cmpid')
        if 'ad_format_type_id' in df_mysql.columns: group_keys.append('ad_format_type_id')

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

    # ============================================================
    # CRITICAL REFACTOR: Extract UserIntent ONCE (avoid pollution from enriched state)
    # ============================================================
    # Get user's ORIGINAL intent (not enriched by PerformanceGenerator or others)
    user_intent = state.get('user_intent')
    if user_intent and user_intent.analysis_needs:
        raw_analysis_needs = user_intent.analysis_needs
    else:
        raw_analysis_needs = state.get('analysis_needs')

    if hasattr(raw_analysis_needs, 'model_dump'):
        user_original_analysis_needs = raw_analysis_needs.model_dump()
    elif hasattr(raw_analysis_needs, 'dict'):
        user_original_analysis_needs = raw_analysis_needs.dict()
    elif isinstance(raw_analysis_needs, dict):
        user_original_analysis_needs = raw_analysis_needs
    else:
        user_original_analysis_needs = {}

    # Store original user dimensions/metrics for later use (after aggregation)
    user_original_dims = user_original_analysis_needs.get('dimensions', [])
    user_original_metrics = user_original_analysis_needs.get('metrics', [])

    debug_logs.append(f"User Original Dimensions: {user_original_dims}")
    debug_logs.append(f"User Original Metrics: {user_original_metrics}")

    # -----------------------------------------------------------
    # REMOVED: Pre-Merge Column Filtering (causes data loss)
    # -----------------------------------------------------------
    # Previously: Filtered MySQL columns before merge based on user dimensions
    # Problem: PerformanceGenerator enriches dimensions (adds cmpid, campaign_name, etc.)
    #          This pollutes the dimension list, causing wrong columns to be filtered
    # Solution: Keep ALL columns through merge and aggregation, filter at the end
    #
    # New Architecture: Merge ALL → Aggregate ALL → Filter for Display

    debug_logs.append(f"MySQL Cols Before Merge (ALL): {list(df_mysql.columns)}")

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

    # Smart Fillna: Don't fill dates with 0
    # Fill numeric columns with 0
    num_cols = merged_df.select_dtypes(include=['number']).columns
    merged_df[num_cols] = merged_df[num_cols].fillna(0)
    
    # Fill object columns with empty string (except dates maybe? empty string is fine for display)
    obj_cols = merged_df.select_dtypes(include=['object']).columns
    merged_df[obj_cols] = merged_df[obj_cols].fillna("")
    
    # --- Consolidate Campaign Name ---
    # Priority: MySQL (Campaign_Name) > ClickHouse (campaign_name)
    # Since we lowercased everything, we look for 'campaign_name'
    name_cols = [c for c in merged_df.columns if c == 'campaign_name']
    
    # Check for '_ch' suffix variants if they exist from merge
    name_cols_ch = [c for c in merged_df.columns if 'campaign_name' in c and c != 'campaign_name']
    
    # Primary is usually 'campaign_name' (from MySQL which kept it or renamed it)
    if 'campaign_name' in merged_df.columns:
        # If we have multiple (e.g. campaign_name_ch), coalesce them
        for other_col in name_cols_ch:
             merged_df['campaign_name'] = merged_df['campaign_name'].combine_first(merged_df[other_col])
    
    # Restore Capitalized Output for Display (Optional, but good for UI)
    # We will do this at the very end in reorder step.
    
    # DEBUG: Check Budget After Merge
    merge_budget_total = 0
    budget_col_merge = next((c for c in merged_df.columns if 'budget' in c), None)
    if budget_col_merge:
        merge_budget_total = merged_df[budget_col_merge].sum()
        debug_logs.append(f"DEBUG: Post-Merge Budget Total: {merge_budget_total:,.0f}")

    debug_logs.append(f"Merged Cols: {list(merged_df.columns)}")
    print(f"DEBUG [DataFusion] Merged Columns: {list(merged_df.columns)}")

    # 4. 二次聚合 (Re-aggregation)
    # CRITICAL: Use user's ORIGINAL dimensions (not enriched by PerformanceGenerator)
    dimensions = user_original_dims  # Use the extracted original dims, not polluted state
    print(f"DEBUG [DataFusion] User Original Dimensions (for grouping): {dimensions}")
    
    intent_to_alias = config.get_intent_to_alias_map()

    group_cols = []
    # Since all cols are lowercase, map is simple
    col_lower_map = {c: c for c in merged_df.columns}
    
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

    # ============================================================
    # CRITICAL FIX: Always include campaign_name in group_cols for campaign-level queries
    # ============================================================
    # For strategy/audience/execution queries, campaign_name should always be a grouping dimension
    # to maintain campaign identity. Otherwise, campaigns get aggregated together incorrectly.
    query_level = state.get('query_level', 'strategy')
    if query_level in ['strategy', 'audience', 'execution']:
        if 'campaign_name' in merged_df.columns and 'campaign_name' not in group_cols:
            # Insert at beginning for better display order
            group_cols.insert(0, 'campaign_name')
            print(f"DEBUG [DataFusion] Auto-added campaign_name to group_cols for {query_level} level query")

    debug_logs.append(f"Final Group Cols: {group_cols}")

    exclude_cols_lower = {c for c in ['cmpid', 'id', 'start_date', 'end_date', 'schedule_dates']}
    for gc in group_cols:
        exclude_cols_lower.add(gc)
        
    numeric_cols = [c for c in merged_df.columns 
                    if pd.api.types.is_numeric_dtype(merged_df[c]) 
                    and c not in exclude_cols_lower]
    
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
                col_lower = col # already lower
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
    budget_col_agg = next((c for c in final_df.columns if 'budget' in c), None)
    if budget_col_agg:
        agg_budget_total = final_df[budget_col_agg].sum()
        debug_logs.append(f"DEBUG: Post-Agg Budget Total: {agg_budget_total:,.0f}")

    # ============================================================
    # Budget Consistency Validation
    # ============================================================
    # Compare budget totals across three stages to detect potential duplication
    if raw_budget_total > 0 and agg_budget_total > 0:
        budget_diff_pct = abs(agg_budget_total - raw_budget_total) / raw_budget_total * 100

        # Tolerance based on query level and granularity
        tolerance = 5  # 5% for most queries
        query_level = state.get('query_level', 'strategy')

        # Higher tolerance for format-level queries due to potential floating point rounding
        if query_level == 'execution' and 'ad_format_type_id' in final_df.columns:
            tolerance = 10

        if budget_diff_pct > tolerance:
            warning = (
                f"⚠️ Budget Consistency Warning:\n"
                f"   Query Level: {query_level}\n"
                f"   Raw SQL Total: {raw_budget_total:,.0f}\n"
                f"   Post-Merge Total: {merge_budget_total:,.0f}\n"
                f"   Post-Agg Total: {agg_budget_total:,.0f}\n"
                f"   Difference: {budget_diff_pct:.1f}% (Tolerance: {tolerance}%)\n"
                f"   Possible causes: SQL duplication, incorrect GROUP BY, or Cartesian product"
            )
            debug_logs.append(warning)
            print(f"DEBUG [DataFusion] {warning}")
        else:
            debug_logs.append(f"✅ Budget Consistency Check PASSED: Diff {budget_diff_pct:.2f}% < {tolerance}%")

    print(f"DEBUG [DataFusion] Pre-KPI Calc Columns: {list(final_df.columns)}")

    # 5. 重算衍生指標
    all_cols_lower = {c: c for c in final_df.columns}

    def find_col(metric_key: str):
        """Find column by metric key using config-defined keywords."""
        keywords = config.get_metric_keywords(metric_key)
        for k in keywords:
            if k.lower() in all_cols_lower:
                return all_cols_lower[k.lower()]
        return None

    imp_col = find_col('impressions')
    eff_imp_col = find_col('effective_impressions')
    click_col = find_col('clicks')
    view100_col = find_col('views_100')
    view3s_col = find_col('views_3s')
    eng_col = find_col('engagements')
    
    print(f"DEBUG [DataFusion] Found imp_col: {imp_col}, eff_imp_col: {eff_imp_col}, click_col: {click_col}, view100_col: {view100_col}, eng_col: {eng_col}")

    # Denominator priority: Effective Impressions > Total Impressions
    denom_col = eff_imp_col if eff_imp_col else imp_col
    
    if denom_col:
        debug_logs.append(f"Calculating KPIs using denominator: {denom_col}")
        print(f"DEBUG [DataFusion] Denominator found: {denom_col}")
        
        if click_col:
            print(f"DEBUG [DataFusion] Calculating CTR using {click_col} / {denom_col}")
            # Use 'ctr' lowercase
            final_df['ctr'] = final_df.apply(lambda x: (x[click_col] / x[denom_col] * 100) if x[denom_col] > 0 else 0, axis=1).round(2)
        if view100_col: # Use Q100 for VTR (per domain knowledge)
            print(f"DEBUG [DataFusion] Calculating VTR using {view100_col} / {denom_col}")
            final_df['vtr'] = final_df.apply(lambda x: (x[view100_col] / x[denom_col] * 100) if x[denom_col] > 0 else 0, axis=1).round(2)
        if eng_col:
            print(f"DEBUG [DataFusion] Calculating ER using {eng_col} / {denom_col}")
            final_df['er'] = final_df.apply(lambda x: (x[eng_col] / x[denom_col] * 100) if x[denom_col] > 0 else 0, axis=1).round(2)
    else:
        debug_logs.append("No impression column found. Skipping KPI calculation.")
        print("DEBUG [DataFusion] No impression column found.")

    print(f"DEBUG [DataFusion] Post-KPI Calc Columns: {list(final_df.columns)}")

    # ============================================================
    # 6. 後處理 (Column Filtering) - AFTER Aggregation
    # ============================================================
    # CRITICAL: This is where we filter columns based on user's ORIGINAL request
    # (not enriched dimensions from PerformanceGenerator)

    # Start with group columns (these are based on user's original dimensions)
    cols_to_keep = []
    for dim in group_cols:
        if dim in final_df.columns: cols_to_keep.append(dim)
    if seg_col and seg_col in final_df.columns and seg_col not in cols_to_keep: cols_to_keep.append(seg_col)

    # Add user-requested metrics (from ORIGINAL intent, not enriched)
    requested_metrics = [m.lower() for m in user_original_metrics]
    # Add other metrics...
    metric_map = {
        'budget_sum': ['budget', 'budget_sum'],
        'impression_sum': ['impression', 'total_impressions'],
        'click_sum': ['click', 'total_clicks'],
        'view3s_sum': ['view3s', 'views_3s'],
        'q100_sum': ['q100', 'views_100']
    }
    for req_m in requested_metrics:
        candidates = metric_map.get(req_m, [req_m])
        for cand in candidates:
            match = next((c for c in final_df.columns if cand in c), None)
            if match and match not in cols_to_keep: cols_to_keep.append(match)
            
    # Always add KPIs if they exist (using lowercase)
    for kpi in ['ctr', 'vtr', 'er']:
        if kpi in final_df.columns:
             if kpi not in cols_to_keep:
                cols_to_keep.append(kpi)

    # ============================================================
    # CRITICAL FIX: Always include fundamental identification columns
    # ============================================================
    # 1. Campaign Name - Essential for identifying campaigns
    if 'campaign_name' in final_df.columns and 'campaign_name' not in cols_to_keep:
        # Insert at beginning for better display order
        cols_to_keep.insert(0, 'campaign_name')

    # 2. Start/End Date - Provides timeline context
    #    Note: These will be merged into campaign_name later (Lines 500-524) and then hidden (Lines 526-534)
    #    But we need them in cols_to_keep now so they survive the filter
    for date_col in ['start_date', 'end_date']:
        if date_col in final_df.columns and date_col not in cols_to_keep:
            cols_to_keep.append(date_col)

    # 3. Budget - Fundamental financial data (always useful for audience/execution queries)
    budget_col_match = next((c for c in final_df.columns if 'budget' in c), None)
    if budget_col_match and budget_col_match not in cols_to_keep:
        cols_to_keep.append(budget_col_match)

    # Add budget fallback if nothing selected (LEGACY - now redundant with above logic)
    if len(cols_to_keep) == len(group_cols):
         match = next((c for c in final_df.columns if 'budget' in c), None)
         if match and match not in cols_to_keep: cols_to_keep.append(match)
         # Also add impressions/clicks if available for context
         if imp_col and imp_col not in cols_to_keep: cols_to_keep.append(imp_col)

    print(f"DEBUG [DataFusion] Cols to Keep BEFORE Final Filter: {cols_to_keep}")

    if cols_to_keep:
        final_df = final_df[cols_to_keep]
    
    # 6.5 排序 & Limit
    calc_type = user_original_analysis_needs.get('calculation_type', 'Total')
    
    # Smart Sorting: If rows > 20 and no specific sort requested, force Ranking to show top items
    if len(final_df) > 20 and calc_type == 'Total':
        calc_type = 'Ranking'
        debug_logs.append("Auto-switching to Ranking mode due to large dataset.")
    
    if calc_type == 'Ranking':
        sort_col = None
        # ... (Existing Ranking Logic) ...
        # Strategy 4: Budget Fallback
        if not sort_col:
            sort_col = next((c for c in final_df.columns if 'budget' in c), None)
            
        if sort_col:
            debug_logs.append(f"Sorting by {sort_col} (Descending) for Ranking")
            final_df = final_df.sort_values(by=sort_col, ascending=False)
            
    elif calc_type == 'Trend':
        date_col = next((c for c in final_df.columns if 'date' in c or 'month' in c), None)
        if date_col:
            debug_logs.append(f"Sorting by {date_col} (Ascending) for Trend")
            final_df = final_df.sort_values(by=date_col, ascending=True)

    # Apply Default Limit
    limit = state.get('limit') or 20
    total_rows = len(final_df)
    
    if total_rows > limit:
        debug_logs.append(f"Applying Limit: Top {limit} of {total_rows}")
        final_df = final_df.head(limit)

    # 7. Final Formatting
    for col in final_df.columns:
        if 'budget' in col and pd.api.types.is_numeric_dtype(final_df[col]):
             final_df[col] = final_df[col].fillna(0).astype(int)

    # ============================================================
    # 7.1 Date Display (DISABLED - keep start_date and end_date separate)
    # ============================================================
    # Previously: Combined dates into campaign_name as "Name (2025-01-01~2025-03-31)"
    # User Feedback: "走期可以獨立成start_date和end_date兩個欄位"
    # Solution: Keep start_date and end_date as independent columns, don't merge into name

    # Still need to identify column names for later use (filtering invalid names)
    camp_name_col = next((c for c in final_df.columns if c == 'campaign_name'), None)
    start_col = next((c for c in final_df.columns if c == 'start_date'), None)
    end_col = next((c for c in final_df.columns if c == 'end_date'), None)

    # DISABLED: Date merging logic (keep dates separate per user request)
    # if camp_name_col and start_col and end_col:
    #     final_df[camp_name_col] = final_df.apply(lambda row: f"{row[camp_name_col]} ({row[start_col]}~{row[end_col]})", axis=1)

    print(f"DEBUG [DataFusion] Keeping start_date and end_date as separate columns (not merging into campaign_name)")

    # 7.2 Hide Technical IDs (but NOT dates - keep them visible)
    cols_to_hide = list(config.get_hidden_columns())  # Copy to avoid mutating config

    # REMOVED: Don't hide start_date and end_date anymore
    # Previously: if camp_name_col: cols_to_hide.append(start_col); cols_to_hide.append(end_col)
    # Now: Keep start_date and end_date visible as independent columns
        
    # Drop columns using case-insensitive match
    final_df = final_df.drop(columns=[c for c in final_df.columns if c.lower() in cols_to_hide], errors='ignore')

    # Reorder Columns: Campaign Name -> Format -> Segment -> Metrics
    preferred_order = config.get_display_order()
    
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

    # Filter out invalid Campaign Names (e.g. '0' or 0)
    if camp_name_col and camp_name_col in final_df.columns:
        final_df = final_df[final_df[camp_name_col].astype(str) != '0']
        
    # Find ad_format column again just to be safe
    ad_format_col = next((c for c in final_df.columns if 'ad_format' in c and c != 'ad_format_type_id'), None)

    # ============================================================
    # CRITICAL FIX: Only filter invalid Ad Format if user requested it as dimension
    # ============================================================
    # If user didn't request Ad_Format dimension, don't filter out rows with empty ad_format
    # This is important for Segment_Category queries where ad_format might be NULL/empty
    # Use user's ORIGINAL dimensions (not enriched by PerformanceGenerator)
    user_requested_ad_format = 'ad_format' in [d.lower() for d in user_original_dims] # Check for lowercased 'ad_format'
    user_requested_performance = any(m.lower() in ['ctr', 'vtr', 'er', 'impression', 'click'] for m in user_original_metrics)

    if ad_format_col and ad_format_col in final_df.columns and user_requested_ad_format:
        initial_count = len(final_df)
        
        if user_requested_performance:
            # User wants format-specific performance -> strictly filter out rows without valid format
            print(f"DEBUG [DataFusion] User requested Ad_Format + Performance. Strictly filtering empty/null Ad_Format.")
            mask = ~final_df[ad_format_col].astype(str).str.strip().isin(['0', 'nan', 'none', '', 'None'])
        else:
            # User just wants Ad_Format as a dimension (e.g., for campaign details) -> keep empty/null (represents 'not set')
            print(f"DEBUG [DataFusion] User requested Ad_Format only. Filtering '0', keeping empty/null.")
            mask = ~final_df[ad_format_col].astype(str).str.strip().isin(['0'])
        
        filtered_df = final_df[mask]
        dropped_count = initial_count - len(filtered_df)

        # Safety Check: If filtering would remove ALL data, keep original (don't filter)
        # This prevents losing all data when Ad_Format legitimately doesn't exist
        if dropped_count == initial_count and initial_count > 0:
            print(f"DEBUG [DataFusion] Ad_Format filter would remove all {initial_count} rows. Keeping data with empty Ad_Format.")
            # Keep ad_format_col but replace invalid values with empty string for display
            final_df[ad_format_col] = final_df[ad_format_col].astype(str).replace(['0', 'nan', 'None'], '')
        else:
            final_df = filtered_df
            if dropped_count > 0:
                debug_logs.append(f"Dropped {dropped_count} rows with invalid Ad Format (user requested Ad_Format dimension).")
                print(f"DEBUG [DataFusion] Dropped {dropped_count} rows due to invalid Ad Format in col '{ad_format_col}'.")
    elif ad_format_col and ad_format_col in final_df.columns and not user_requested_ad_format:
        # User didn't request Ad_Format, but it exists in merged data
        # Drop the ad_format column instead of filtering rows
        print(f"DEBUG [DataFusion] User didn't request Ad_Format. Dropping column '{ad_format_col}' instead of filtering rows.")
        final_df = final_df.drop(columns=[ad_format_col], errors='ignore')
        
    # Filter out rows where Agency is None or empty string (for Agency grouping)
    agency_col = next((c for c in final_df.columns if c == 'agency'), None)
    if agency_col and agency_col in final_df.columns:
        # Filter out 'None', 'nan', and empty strings (case-insensitive check for None/nan if needed, but explicit list is safer)
        final_df = final_df[~final_df[agency_col].astype(str).isin(['None', 'nan', ''])]
        final_df = final_df[final_df[agency_col].notna()]

    # Filter out rows where Advertiser is None (similar to Agency)
    adv_col = next((c for c in final_df.columns if c == 'advertiser'), None)
    if adv_col and adv_col in final_df.columns:
        final_df = final_df[~final_df[adv_col].astype(str).isin(['None', 'nan', ''])]
        final_df = final_df[final_df[adv_col].notna()]
        
    # ============================================================
    # Hide All-Zero Metrics (ONLY if they are default metrics)
    # ============================================================
    # Logic:
    # - If user EXPLICITLY requested a metric (e.g., "show me VTR"), keep it even if all 0
    # - If metric was auto-added as DEFAULT (e.g., "成效" → CTR/VTR/ER), hide if all 0
    # - This keeps the table clean while preserving user intent
    was_default = state.get("was_default_metrics", False)

    for metric in ['ctr', 'vtr', 'er']:
        if metric in final_df.columns:
            # Check if user explicitly requested this metric
            user_requested_metric = metric.upper() in [m.upper() for m in user_original_metrics]

            if (final_df[metric] == 0).all():
                # All values are 0
                if was_default and not user_requested_metric:
                    # Default metric with all zeros → hide it
                    final_df = final_df.drop(columns=[metric])
                    print(f"DEBUG [DataFusion] Hiding all-zero DEFAULT metric '{metric}'")
                elif user_requested_metric:
                    # User explicitly requested it → keep it (0 is meaningful)
                    print(f"DEBUG [DataFusion] Keeping all-zero metric '{metric}' (user explicitly requested it)")
                elif not was_default:
                    # Not default and user didn't request → hide it
                    final_df = final_df.drop(columns=[metric])
                    print(f"DEBUG [DataFusion] Hiding all-zero metric '{metric}' (not requested)")

    # --- 8. Final Renaming (Restore Capitalization for Display) ---
    # Restore capitalization based on intent_to_alias (backward mapping) or config
    display_map = {}
    valid_dims_map = config.get_valid_dimensions() # e.g. {'agency': 'Agency'}
    
    # Map metrics
    metric_display_map = {
        'ctr': 'CTR',
        'vtr': 'VTR',
        'er': 'ER',
        'budget_sum': 'Budget_Sum',
        'impression': 'Impression',
        'click': 'Click'
    }
    
    for col in final_df.columns:
        if col in valid_dims_map:
            display_map[col] = valid_dims_map[col]
        elif col in metric_display_map:
            display_map[col] = metric_display_map[col]
        # Ad-hoc fixes
        elif 'ad_format' in col and 'type' in col:
             display_map[col] = 'Ad_Format'
        elif 'segment' in col:
             display_map[col] = 'Segment_Category'
             
    if display_map:
        final_df.rename(columns=display_map, inplace=True)

    return {
        "final_dataframe": final_df.to_dict('records'),
        "final_result_text": f"MySQL Rows: {len(df_mysql)} | " + " | ".join(debug_logs),
        "budget_note": budget_note
    }
