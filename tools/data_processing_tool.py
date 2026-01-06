import pandas as pd
from typing import List, Dict, Any, Optional
from langchain_core.tools import tool

@tool
def pandas_processor(
    data: List[Dict[str, Any]],
    operation: str,
    groupby_col: Optional[str] = None,
    sum_col: Optional[str] = None,
    concat_col: Optional[str] = None,
    sep: str = ", ",
    sort_col: Optional[str] = None,
    top_n: Optional[int] = None,
    merge_data: Optional[List[Dict[str, Any]]] = None,
    merge_on: Optional[str] = None,
    merge_how: str = "inner",
    ascending: bool = False,
    date_col: Optional[str] = None,
    new_col: Optional[str] = None,
    period: Optional[str] = None,
    select_columns: Optional[List[str]] = None,
    rename_map: Optional[Dict[str, str]] = None  # [NEW] Explicit rename map
) -> Dict[str, Any]:
    """
    對資料進行 Pandas 處理與分析，並回傳 Markdown 表格。

    Args:
        rename_map: (選填) 欄位重命名映射 {old_name: new_name}。在篩選前執行。
    """
    if not data:
        return {
            "status": "error",
            "markdown": "⚠️ 無資料可供處理。",
            "data": [],
            "count": 0
        }

    df = pd.DataFrame(data)

    # --- [MOVED] Explicit Renaming moved to end (after all operations) ---
    # We'll apply rename_map at the very end to avoid column name mismatch issues

    # 0. 輔助功能：新增時間週期欄位
    if operation == 'add_time_period':
        # 使用直接傳入的參數，而非 kwargs
        target_new_col = new_col if new_col else 'period'
        target_period = period if period else 'month'

        if not date_col or date_col not in df.columns:
            return {
                "status": "error",
                "markdown": f"❌ Error: add_time_period 需要有效的 date_col。現有欄位: {list(df.columns)}",
                "data": data,
                "count": len(df)
            }

        try:
            # 轉換為 datetime
            df[date_col] = pd.to_datetime(df[date_col])
            
            if target_period == 'month':
                df[target_new_col] = df[date_col].dt.strftime('%Y-%m')
            elif target_period == 'year':
                df[target_new_col] = df[date_col].dt.strftime('%Y')
            elif target_period == 'quarter':
                df[target_new_col] = df[date_col].dt.to_period('Q').astype(str)
            
            result_df = df
            processed_data = result_df.to_dict('records')
            return {
                "status": "success",
                "markdown": f"✅ 已新增 {target_new_col} 欄位 ({target_period})。前 5 筆預覽：\n\n" + result_df.head(5).to_markdown(index=False),
                "data": processed_data,
                "count": len(result_df)
            }
        except Exception as e:
            return {"status": "error", "markdown": f"❌ Time processing error: {str(e)}", "data": data, "count": len(df)}

    # 1. 強制型別轉換：將所有能轉成數字的欄位都轉成數字 (處理 Decimal, String 數字)
    for col in df.columns:
        try:
            df[col] = pd.to_numeric(df[col])
        except (ValueError, TypeError):
            pass

    # 處理 NaN
    numeric_cols = df.select_dtypes(include=['number']).columns
    for col in numeric_cols:
        df[col] = df[col].fillna(0)

    result_df = df

    try:
        # ===== 新增：Merge 操作 =====
        if operation == 'merge':
            if not merge_data or not merge_on:
                return {
                    "status": "error",
                    "markdown": "❌ Error: merge 操作需要 merge_data 和 merge_on 參數。",
                    "data": [],
                    "count": 0
                }

            # 將第二個數據集轉為 DataFrame
            df2 = pd.DataFrame(merge_data)

            # 同樣進行型別轉換
            for col in df2.columns:
                try:
                    df2[col] = pd.to_numeric(df2[col])
                except (ValueError, TypeError):
                    pass

            # Handle multiple merge columns (comma-separated)
            if isinstance(merge_on, str) and ',' in merge_on:
                merge_on_keys = [col.strip() for col in merge_on.split(',')]
            else:
                merge_on_keys = merge_on

            # --- [NEW] Auto-Aggregation for Targeting Data (Prevent One-to-Many Explosion) ---
            # 如果是合併「受眾數據」(segment_name)，則先進行聚合，避免讓主表 (Format Level) 產生重複列
            if 'segment_name' in df2.columns and 'campaign_id' in df2.columns:
                print("DEBUG [PandasProcessor] Detected Targeting Data. Auto-aggregating segments by campaign_id...")
                
                # 1. 找出除了 merge_on_keys 和 segment_name 以外的欄位，這些通常是雜訊 (如 placement_id)
                # 我們只保留 merge keys 和要聚合的目標
                agg_target_col = 'segment_name'
                
                # 確保 Key 存在
                actual_merge_key = merge_on_keys if isinstance(merge_on_keys, list) else [merge_on_keys]
                
                # 執行聚合：將多個 segment_name 合併成一個字串
                df2 = df2.groupby(actual_merge_key)[agg_target_col].agg(
                    lambda x: ', '.join(sorted(set(str(v) for v in x if pd.notna(v) and str(v).strip() != '')))
                ).reset_index()
                
                print(f"DEBUG [PandasProcessor] Aggregated targeting data to {len(df2)} unique campaign rows.")

            # --- [NEW] Smart Merge Key Detection (防止重複) ---
            # 如果兩邊都有 format_type_id 或 format_name，自動加入 merge key
            # 這能解決 "Campaign + Format" 層級的資料合併產生 Cartesian Product 的問題
            candidate_keys = ['format_type_id', 'format_name', 'placement_id']
            
            # 確保 merge_on_keys 是 list
            current_keys = merge_on_keys if isinstance(merge_on_keys, list) else [merge_on_keys]
            
            for k in candidate_keys:
                if k in df.columns and k in df2.columns:
                    if k not in current_keys:
                        print(f"DEBUG [PandasProcessor] Smart Merge: Adding '{k}' to merge keys.")
                        current_keys.append(k)
            
            merge_on_keys = current_keys

            # 執行 merge
            result_df = pd.merge(df, df2, on=merge_on_keys, how=merge_how, suffixes=('_1', '_2'))

            # 填充 merge 後的 NaN 值為 0
            numeric_cols_after_merge = result_df.select_dtypes(include=['number']).columns
            for col in numeric_cols_after_merge:
                result_df[col] = result_df[col].fillna(0)

            print(f"DEBUG [PandasProcessor] Merged {len(df)} rows with {len(df2)} rows on '{merge_on}' ({merge_how}) → {len(result_df)} rows")

        # ===== 原有操作 =====
        elif operation == 'groupby_sum':
            if not groupby_col or not sum_col:
                return {
                    "status": "error",
                    "markdown": "❌ Error: groupby_sum 需要 groupby_col 與 sum_col。",
                    "data": [],
                    "count": 0
                }

            # Handle multiple groupby columns (comma-separated)
            groupby_cols_list = [col.strip() for col in groupby_col.split(',')]

            # Handle multiple sum columns (comma-separated)
            sum_cols_list = [col.strip() for col in sum_col.split(',')]
            
            # Ensure all sum columns are numeric
            for col in sum_cols_list:
                if col not in df.columns:
                    # If column missing, try to ignore or create it with 0? 
                    # Better to skip or error. Let's create it with 0 to be safe for "flexible" SQL returns
                    df[col] = 0
                
                # Force numeric conversion
                try:
                    df[col] = pd.to_numeric(df[col])
                except (ValueError, TypeError):
                    df[col] = 0

            # Check if all groupby cols exist
            valid_groupby_cols = [c for c in groupby_cols_list if c in df.columns]
            if not valid_groupby_cols:
                 return {
                    "status": "error",
                    "markdown": f"❌ Error: Groupby columns {groupby_cols_list} not found in data columns {list(df.columns)}.",
                    "data": [],
                    "count": 0
                }

            # [NEW] Enhanced Aggregation (Sum + Concat)
            agg_dict = {col: 'sum' for col in sum_cols_list}

            if concat_col:
                concat_cols_list = [col.strip() for col in concat_col.split(',')]
                for c_col in concat_cols_list:
                    if c_col in df.columns:
                        # Lambda to concat unique values
                        agg_dict[c_col] = lambda x: sep.join(sorted(set(str(v) for v in x if pd.notna(v) and str(v).strip() != '')))

            # Perform Aggregation
            result_df = df.groupby(valid_groupby_cols).agg(agg_dict).reset_index()

            # [FIX] Don't sort yet - wait until after CTR/VTR/ER calculation
            # Store sort_col and top_n for later use
            _pending_sort_col = sort_col
            _pending_ascending = ascending
            _pending_top_n = top_n

        elif operation == 'groupby_concat':
            # 新增：字串聚合功能
            # 參數：groupby_col (必要), concat_col (必要), sep (可選)
            
            if not groupby_col or not concat_col:
                return {
                    "status": "error",
                    "markdown": "❌ Error: groupby_concat 需要 groupby_col 與 concat_col。",
                    "data": [],
                    "count": 0
                }

            groupby_cols_list = [col.strip() for col in groupby_col.split(',')]
            concat_cols_list = [col.strip() for col in concat_col.split(',')]
            
            # 檢查欄位是否存在
            valid_groupby = [c for c in groupby_cols_list if c in df.columns]
            valid_concat = [c for c in concat_cols_list if c in df.columns]
            
            if not valid_groupby or not valid_concat:
                return {
                     "status": "error", 
                     "markdown": f"❌ Error: Columns not found. Groupby: {valid_groupby}, Concat: {valid_concat}",
                     "data": [],
                     "count": 0
                }
                
            # 執行聚合 (使用 lambda 確保非字串也能轉字串並去重)
            result_df = df.groupby(valid_groupby)[valid_concat].agg(
                lambda x: sep.join(sorted(set(str(v) for v in x if pd.notna(v) and str(v).strip() != '')))
            ).reset_index()

        elif operation == 'top_n':
            if not sort_col:
                return {
                    "status": "error",
                    "markdown": "❌ Error: top_n 需要 sort_col。",
                    "data": [],
                    "count": 0
                }
            # [FIX] Ensure ascending parameter is respected
            result_df = result_df.sort_values(by=sort_col, ascending=ascending)
            if top_n:
                result_df = result_df.head(top_n)

        elif operation == 'groupby_top_n':
            # [NEW] Group-wise Top N: 每個組內取 top N
            # 適用場景: 「各格式的 top5 客戶」
            # 參數:
            #   - groupby_col: 分組欄位 (e.g., "format_name")
            #   - sort_col: 排序欄位 (e.g., "ctr DESC")
            #   - top_n: 每組取前 N 筆

            if not groupby_col or not sort_col or not top_n:
                return {
                    "status": "error",
                    "markdown": "❌ Error: groupby_top_n 需要 groupby_col, sort_col, top_n。",
                    "data": [],
                    "count": 0
                }

            groupby_cols_list = [col.strip() for col in groupby_col.split(',')]

            # Parse sort_col (e.g., "ctr DESC" → col="ctr", ascending=False)
            parts = sort_col.strip().split()
            actual_sort_col = parts[0]
            sort_ascending = False if len(parts) > 1 and parts[1].upper() == 'DESC' else True

            # Use pandas groupby + head for group-wise top N
            result_df = (
                result_df.sort_values(by=actual_sort_col, ascending=sort_ascending)
                .groupby(groupby_cols_list, as_index=False)
                .head(top_n)
            )

            print(f"DEBUG [PandasProcessor] Applied groupby_top_n: grouped by {groupby_cols_list}, sorted by {actual_sort_col}, took top {top_n} per group")

        elif operation == 'add_percentage_column':
            # 新增：計算佔比欄位
            # 參數：sum_col (必要，要計算佔比的欄位), new_col (可選，新欄位名稱，預設為 "percentage")

            if not sum_col:
                return {
                    "status": "error",
                    "markdown": "❌ Error: add_percentage_column 需要 sum_col 參數（指定要計算佔比的欄位）。",
                    "data": [],
                    "count": 0
                }

            value_col = sum_col.strip()  # 使用 sum_col 作為要計算佔比的欄位
            percentage_col = new_col if new_col else "percentage"

            if value_col not in df.columns:
                return {
                    "status": "error",
                    "markdown": f"❌ Error: 欄位 '{value_col}' 不存在。現有欄位: {list(df.columns)}",
                    "data": [],
                    "count": 0
                }

            # 確保欄位是數值型
            try:
                df[value_col] = pd.to_numeric(df[value_col])
            except (ValueError, TypeError):
                return {
                    "status": "error",
                    "markdown": f"❌ Error: 欄位 '{value_col}' 無法轉換為數值。",
                    "data": [],
                    "count": 0
                }

            # 計算總和
            total = df[value_col].sum()

            if total == 0:
                # 避免除以零
                result_df[percentage_col] = 0.0
            else:
                # 計算佔比 (百分比)
                result_df[percentage_col] = (df[value_col] / total * 100).round(2)

            print(f"DEBUG [PandasProcessor] Added percentage column '{percentage_col}' based on '{value_col}' (Total: {total:,.0f})")

        # 通用排序和 Top N (for non-groupby_sum operations)
        print(f"DEBUG [PandasProcessor] Before general sort: operation={operation}, sort_col={sort_col}")
        if sort_col and operation not in ['groupby_sum', 'top_n', 'add_percentage_column', 'groupby_top_n']:
            print(f"DEBUG [PandasProcessor] Executing general sort with sort_col={sort_col}")
            result_df = result_df.sort_values(by=sort_col, ascending=ascending)

        # [FIX] Don't apply top_n here for groupby_sum - will apply after delayed sorting
        if top_n and operation not in ['groupby_sum', 'top_n', 'add_percentage_column', 'groupby_top_n']:
            result_df = result_df.head(top_n)

        # --- [NEW] Automatic Rate Recalculation (自動重算成效指標) ---
        # 如果 groupby_sum 導致百分比指標遺失，但分子分母存在，則自動算回來
        # 欄位名稱可能是原始 snake_case 或帶有後綴

        def safe_div(n, d):
            return (n / d * 100) if d > 0 else 0

        # 標準化欄位查找 (處理 potential suffixes + 支援中文欄位名)
        def find_col(base_names):
            """
            Args:
                base_names: list of possible column names (English + Chinese)
            Returns:
                The first matching column name, or None
            """
            if not isinstance(base_names, list):
                base_names = [base_names]

            for base_name in base_names:
                if base_name in result_df.columns: return base_name
                if f"{base_name}_1" in result_df.columns: return f"{base_name}_1"
                if f"{base_name}_x" in result_df.columns: return f"{base_name}_x"
            return None

        # [FIX] Added 'total_impressions' and 'total_q100' to support ClickHouse/Benchmark data
        col_imps = find_col(["effective_impressions", "total_impressions", "有效曝光"])
        col_clicks = find_col(["total_clicks", "總點擊"])
        col_q100 = find_col(["total_q100_views", "total_q100", "完整觀看數"])
        col_eng = find_col(["total_engagements", "總互動"])

        if col_imps:
            # CTR
            if col_clicks:
                result_df['ctr'] = result_df.apply(lambda row: safe_div(row[col_clicks], row[col_imps]), axis=1)
                # [FIX] Alias to common names to satisfy Planner/Sort expectations
                if 'avg_ctr' not in result_df.columns: result_df['avg_ctr'] = result_df['ctr']
                if 'Ctr' not in result_df.columns: result_df['Ctr'] = result_df['ctr']

            # VTR
            if col_q100:
                result_df['vtr'] = result_df.apply(lambda row: safe_div(row[col_q100], row[col_imps]), axis=1)
                # [FIX] Alias
                if 'avg_vtr' not in result_df.columns: result_df['avg_vtr'] = result_df['vtr']
                if 'Vtr' not in result_df.columns: result_df['Vtr'] = result_df['vtr']

            # ER
            if col_eng:
                result_df['er'] = result_df.apply(lambda row: safe_div(row[col_eng], row[col_imps]), axis=1)
                # [FIX] Alias
                if 'avg_er' not in result_df.columns: result_df['avg_er'] = result_df['er']
                if 'Er' not in result_df.columns: result_df['Er'] = result_df['er']

        # --- [NEW] Apply Delayed Sorting for groupby_sum (After CTR/VTR/ER Calculation) ---
        # Parse sort_col to extract column name and direction (e.g., "ctr DESC" → col="ctr", asc=False)
        if operation == 'groupby_sum' and '_pending_sort_col' in locals():
            if _pending_sort_col:
                # Parse "ctr DESC" or "ctr ASC" or "ctr"
                parts = _pending_sort_col.strip().split()
                actual_col = parts[0]
                direction = parts[1].upper() if len(parts) > 1 else "DESC"  # Default to DESC
                sort_ascending = (direction == "ASC")

                if actual_col in result_df.columns:
                    print(f"DEBUG [PandasProcessor] Applying delayed sort: {actual_col} {'ASC' if sort_ascending else 'DESC'}")
                    result_df = result_df.sort_values(by=actual_col, ascending=sort_ascending)
                else:
                    print(f"WARN [PandasProcessor] Sort column '{actual_col}' not found in result. Available: {list(result_df.columns)}")

            # [NEW] Apply top_n after sorting
            if '_pending_top_n' in locals() and _pending_top_n:
                print(f"DEBUG [PandasProcessor] Applying delayed top_n: {_pending_top_n}")
                result_df = result_df.head(_pending_top_n)

            # Clean up variables
            del _pending_sort_col, _pending_ascending
            if '_pending_top_n' in locals():
                del _pending_top_n

        # --- [NEW] Column Name Cleanup (自動清理 Merge 後綴) ---
        # 救回因 Merge 而變成 _1 的欄位
        clean_rename_map = {}
        for col in result_df.columns:
            if col.endswith('_1'):
                original_name = col[:-2]
                if original_name not in result_df.columns:
                    clean_rename_map[col] = original_name
            elif col.endswith('_x'):
                original_name = col[:-2]
                if original_name not in result_df.columns:
                    clean_rename_map[col] = original_name

        if clean_rename_map:
            print(f"DEBUG [PandasProcessor] Renaming suffixed columns: {clean_rename_map}")
            result_df = result_df.rename(columns=clean_rename_map)

        # 2. [NEW] Apply Explicit Rename Map (After all operations completed)
        # This ensures operations like groupby_sum can find columns by their original names
        if rename_map:
            valid_rename = {k: v for k, v in rename_map.items() if k in result_df.columns}
            if valid_rename:
                print(f"DEBUG [PandasProcessor] Applying explicit rename: {valid_rename}")
                result_df = result_df.rename(columns=valid_rename)

        # 3. 保存處理後的數據（數值格式）供後續使用
        processed_data = result_df.to_dict('records')

        # 4. 格式化數值用於展示 (加上千分位)
        display_df = result_df.copy()
        
        # 數值格式化
        for col in display_df.select_dtypes(include=['number']).columns:
            col_lower = col.lower()
            # 針對比率/百分比欄位保留小數點
            if any(x in col_lower for x in ['ctr', 'vtr', 'er', 'rate', 'ratio', 'percent']):
                display_df[col] = display_df[col].apply(lambda x: f"{x:,.2f}")
            else:
                display_df[col] = display_df[col].apply(lambda x: f"{x:,.0f}")
            
        # 欄位名稱映射 (Column Mapping) - 只在沒有 explicit rename_map 時執行
        # 如果 LLM 已經提供了 rename_map，就不需要自動翻譯
        if not rename_map:
            column_mapping = {
                # Identifiers
                'Campaign Id': '活動編號',
                'Format Type Id': '格式ID',
                'Placement Id': '版位ID',
                'Execution Id': '執行單ID',

                # Names
                'Campaign Name': '活動名稱',
                'Client Name': '客戶名稱',
                'Agency Name': '代理商',
                'Brand': '品牌',
                'Contract Name': '合約名稱',
                'Format Name': '廣告格式',
                'Segment Name': '受眾標籤',
                'Ad Format Type': '廣告類型',

                # Dates
                'Start Date': '開始日期',
                'End Date': '結束日期',
                'Investment Start Date': '走期開始',
                'Investment End Date': '走期結束',

                # Money
                'Investment Amount': '投資金額',
                'Investment Gift': '贈送金額',
                'Execution Amount': '執行金額',
                'Budget': '預算',

                # Targeting
                'Targeting Segments': '數據鎖定',
                'Segment Category': '受眾分類',

                # Performance
                'Effective Impressions': '有效曝光',
                'Total Clicks': '總點擊',
                'Total Engagements': '總互動',
                'Total Q100 Views': '完整觀看數',
                'Ctr': '點擊率 (CTR%)',
                'Vtr': '觀看率 (VTR%)',
                'Er': '互動率 (ER%)'
            }

            # 欄位名稱格式化 (snake_case -> Title Case -> Mapping)
            new_columns = []
            for c in display_df.columns:
                title_case = c.replace('_', ' ').title()
                # 優先使用映射，若無則保留 Title Case
                new_columns.append(column_mapping.get(title_case, title_case))

            display_df.columns = new_columns

        # --- 新增：處理重複欄位 ---
        # 移除重複的欄位（保留第一個出現的）
        display_df = display_df.loc[:, ~display_df.columns.duplicated()]

        # --- 欄位過濾 (動態選擇 vs 白名單) ---
        
        target_columns = []

        if select_columns and len(select_columns) > 0:
            # 手動補充常見的 Key 對應 (English -> Chinese)
            EXTRA_MAPPING = {
                "format_name": "廣告格式",
                "format": "廣告格式",
                "ad_format": "廣告格式",
                "格式": "廣告格式",
                "廣告形式": "廣告格式",
                "campaign_name": "活動名稱",
                "campaign": "活動名稱",
                "client_name": "客戶名稱",
                "client": "客戶名稱",
                "agency_name": "代理商",
                "agency": "代理商",
                "investment_amount": "投資金額",
                "amount": "投資金額",
                "budget": "預算",
                "start_date": "開始日期",
                "end_date": "結束日期",
                "targeting_segments": "受眾標籤",
                "segments": "受眾標籤",
                "segment_name": "受眾標籤",
                "數據鎖定": "受眾標籤",
                "鎖定": "受眾標籤",
                "受眾": "受眾標籤",
                "ta": "受眾標籤",
                "targeting": "受眾標籤",
                "effective_impressions": "有效曝光",
                "impressions": "有效曝光",
                "clicks": "總點擊",
                "total_clicks": "總點擊",
                "ctr": "點擊率 (CTR%)",
                "vtr": "觀看率 (VTR%)",
                "er": "互動率 (ER%)",
                "engagements": "總互動",
                "total_engagements": "總互動",
                "total_q100_views": "完整觀看數",
                "q100": "完整觀看數"
            }

            # 策略 A: 使用者指定欄位 (Dynamic Selection)
            for req_col in select_columns:
                found = False
                req_lower = req_col.lower()

                # 1. 嘗試透過 EXTRA_MAPPING 找中文名
                if req_lower in EXTRA_MAPPING:
                    target_zh = EXTRA_MAPPING[req_lower]
                    if target_zh in display_df.columns:
                        target_columns.append(target_zh)
                        found = True
                
                # 2. 直接匹配 (中文或原本就存在的欄位)
                if not found and req_col in display_df.columns:
                    target_columns.append(req_col)
                    found = True

                # 3. 嘗試模糊匹配
                if not found:
                    # 針對 DataFrame 中的每個欄位
                    for df_col in display_df.columns:
                        # 檢查是否包含 (例如 "格式" in "廣告格式")
                        if req_col in df_col:
                            target_columns.append(df_col)
                            found = True
                            break # Match first candidate only to avoid duplicates from one request
            
            # Fallback: If absolutely no columns matched user request, default to safe list
            if not target_columns and select_columns:
                 print(f"DEBUG [PandasProcessor] User requested {select_columns} but no matches found. Showing default columns.")
                 target_columns = [c for c in ["廣告格式", "活動名稱", "日期", "投資金額", "有效曝光", "總點擊"] if c in display_df.columns]

        # 執行過濾 (Strict Filtering)
        if target_columns:
            # 去重並保持順序
            seen = set()
            final_cols = [x for x in target_columns if not (x in seen or seen.add(x))]
            
            # Ensure we only keep columns that actually exist in the dataframe
            final_cols = [c for c in final_cols if c in display_df.columns]
            
            display_df = display_df[final_cols]

        # --- 強制資料清洗 (防止 Markdown 表格壞掉) ---
        # 1. 清洗資料內容 (Data Cells)
        # 對「所有欄位」執行清洗，確保沒有任何換行符 (\n) 或管線符 (|) 殘留
        for col in display_df.columns:
            display_df[col] = (
                display_df[col]
                .astype(str)
                .str.replace(r'[\r\n]+', ' ', regex=True)
                .str.replace(r'\|', '/', regex=True)
                .str.strip()
            )

        # 2. 清洗表頭名稱 (Column Headers)
        # 避免表頭中有換行符導致分隔線錯位
        display_df.columns = [
            str(c).replace('\n', ' ').replace('\r', '').replace('|', '/').strip()
            for c in display_df.columns
        ]

        # 最終修飾：將 NaN 替換為空字串
        display_df = display_df.fillna("")

        # --- Custom Markdown Formatter (取代 to_markdown) ---
        # 避免使用 tabulate (pandas default)，因為它在處理中文字寬與換行時容易導致表格結構破裂。
        # 這裡採用「不對齊 (No Alignment Padding)」的純結構輸出，交由前端渲染器處理對齊。
        
        headers = list(display_df.columns)
        
        # 1. 建立表頭
        md_lines = ["| " + " | ".join(headers) + " |"]
        
        # 2. 建立分隔線 (全部靠左對齊 :---，這是最安全的寫法)
        md_lines.append("| " + " | ".join([":---"] * len(headers)) + " |")
        
        # 3. 建立資料列
        for _, row in display_df.iterrows():
            # 確保所有值都是字串，且已經過清洗
            row_vals = [str(val) for val in row]
            md_lines.append("| " + " | ".join(row_vals) + " |")
            
        markdown_table = "\n".join(md_lines)

        return {
            "status": "success",
            "markdown": markdown_table,
            "data": processed_data,  # 原始數值格式（供後續計算使用）
            "display_data": display_df.to_dict('records'),  # 格式化後的字串格式（供 UI 渲染使用）
            "count": len(result_df)
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "markdown": f"❌ Data Processing Error: {str(e)}",
            "data": [],
            "count": 0
        }