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
    select_columns: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    對資料進行 Pandas 處理與分析，並回傳 Markdown 表格。

    Args:
        data: 原始資料列表 (List of Dicts)。
        operation: 執行的操作 ('groupby_sum', 'groupby_concat', 'top_n', 'merge', 'add_time_period')。
        groupby_col: 分組欄位名稱。
        sum_col: (用於 groupby_sum) 需要加總的數值欄位。
        concat_col: (用於 groupby_concat) 需要合併的字串欄位 (多欄位以逗號分隔)。
        sep: (用於 groupby_concat) 字串分隔符號 (預設為 ', ')。
        sort_col: 排序依據的欄位。
        top_n: 取得前幾筆。
        merge_data: (用於 merge 操作) 要合併的第二個數據集。
        merge_on: (用於 merge 操作) 合併的鍵值欄位 (如 'format_name')。
        merge_how: (用於 merge 操作) 合併方式 ('inner', 'left', 'right', 'outer')。
        ascending: 排序方向 (True=升序, False=降序)。
        date_col: (用於 add_time_period) 來源日期欄位。
        new_col: (用於 add_time_period) 新生成的欄位名稱 (預設 'period')。
        period: (用於 add_time_period) 提取週期 ('month', 'year', 'quarter')。
        select_columns: (選填) 指定要顯示的欄位列表 (支援中文或英文欄位名)，若提供將覆蓋預設白名單。

    Returns:
        {
            "status": "success",
            "markdown": "...",  # Markdown 表格
            "data": [...],      # 處理後的數據 (供後續使用)
            "count": 10
        }
    """
    if not data:
        return {
            "status": "error",
            "markdown": "⚠️ 無資料可供處理。",
            "data": [],
            "count": 0
        }

    df = pd.DataFrame(data)

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

            # Group by and sum
            # Check if all groupby cols exist
            valid_groupby_cols = [c for c in groupby_cols_list if c in df.columns]
            if not valid_groupby_cols:
                 return {
                    "status": "error",
                    "markdown": f"❌ Error: Groupby columns {groupby_cols_list} not found in data columns {list(df.columns)}.",
                    "data": [],
                    "count": 0
                }

            result_df = df.groupby(valid_groupby_cols)[sum_cols_list].sum().reset_index()
            
            # Determine sort column
            # If explicit sort_col is provided and exists, use it.
            # Otherwise, use the first column from sum_cols_list.
            effective_sort_col = sort_col if sort_col and sort_col in result_df.columns else sum_cols_list[0]
            
            result_df = result_df.sort_values(by=effective_sort_col, ascending=ascending)

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
            result_df = df.sort_values(by=sort_col, ascending=ascending)
            if top_n:
                result_df = result_df.head(top_n)

        # 通用排序和 Top N
        if sort_col and operation not in ['groupby_sum', 'top_n']:
            result_df = result_df.sort_values(by=sort_col, ascending=ascending)

        if top_n and operation != 'top_n':
            result_df = result_df.head(top_n)

        # --- [NEW] Automatic Rate Recalculation (自動重算成效指標) ---
        # 如果 groupby_sum 導致百分比指標遺失，但分子分母存在，則自動算回來
        # 欄位名稱可能是原始 snake_case 或帶有後綴
        
        def safe_div(n, d):
            return (n / d * 100) if d > 0 else 0

        # 標準化欄位查找 (處理 potential suffixes)
        def find_col(base_name):
            if base_name in result_df.columns: return base_name
            if f"{base_name}_1" in result_df.columns: return f"{base_name}_1"
            if f"{base_name}_x" in result_df.columns: return f"{base_name}_x"
            return None

        col_imps = find_col("effective_impressions")
        col_clicks = find_col("total_clicks")
        col_q100 = find_col("total_q100_views")
        col_eng = find_col("total_engagements")

        if col_imps:
            # CTR
            if col_clicks:
                result_df['ctr'] = result_df.apply(lambda row: safe_div(row[col_clicks], row[col_imps]), axis=1)
            # VTR
            if col_q100:
                result_df['vtr'] = result_df.apply(lambda row: safe_div(row[col_q100], row[col_imps]), axis=1)
            # ER
            if col_eng:
                result_df['er'] = result_df.apply(lambda row: safe_div(row[col_eng], row[col_imps]), axis=1)

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

        # 2. 保存處理後的數據（數值格式）供後續使用
        processed_data = result_df.to_dict('records')

        # 3. 格式化數值用於展示 (加上千分位)
        display_df = result_df.copy()
        
        # 數值格式化
        for col in display_df.select_dtypes(include=['number']).columns:
            col_lower = col.lower()
            # 針對比率/百分比欄位保留小數點
            if any(x in col_lower for x in ['ctr', 'vtr', 'er', 'rate', 'ratio', 'percent']):
                display_df[col] = display_df[col].apply(lambda x: f"{x:,.2f}")
            else:
                display_df[col] = display_df[col].apply(lambda x: f"{x:,.0f}")
            
        # 欄位名稱映射 (Column Mapping) - 自動翻譯常見欄位
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
            # 建立反向映射表 (English Key -> Chinese Column Name)
            # 幫助 Agent 用英文 Key 也能找到中文欄位
            REVERSE_MAPPING = {v: k for k, v in column_mapping.items()}  # Chinese -> Title Case
            
            # 手動補充常見的 Key 對應
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
                            
            # 如果匹配不到任何欄位，退回預設白名單，以免表格全空
            if not target_columns:
                print(f"DEBUG [PandasProcessor] select_columns provided {select_columns} but no match found. Falling back to whitelist.")
                # Fallthrough to default whitelist logic below
        
        # --- [NEW] Macro Expansion Logic (巨集展開) ---
        # 允許 Agent 傳入集合名詞 (如 "成效")，自動展開為多個具體欄位
        
        COLUMN_GROUPS = {
            "成效": ["有效曝光", "總點擊", "點擊率 (CTR%)", "觀看率 (VTR%)", "互動率 (ER%)", "總互動", "完整觀看數"],
            "performance": ["有效曝光", "總點擊", "點擊率 (CTR%)", "觀看率 (VTR%)", "互動率 (ER%)", "總互動", "完整觀看數"],
            "預算": ["投資金額", "執行金額", "贈送金額"],
            "budget": ["投資金額", "執行金額", "贈送金額"],
            "金額": ["投資金額", "執行金額", "贈送金額"],
            "基本資訊": ["客戶名稱", "活動名稱", "代理商", "品牌", "開始日期", "結束日期"],
            "info": ["客戶名稱", "活動名稱", "代理商", "品牌", "開始日期", "結束日期"],
            "數據鎖定": ["受眾標籤", "受眾分類"],
            "targeting": ["受眾標籤", "受眾分類"],
        }
        
        # 如果使用者有指定欄位，檢查是否包含這些關鍵字並展開
        if target_columns:
            expanded_columns = []
            for col in target_columns:
                # 檢查這個欄位是否是 Group Key (例如 "成效")
                matched_group = None
                for group_key, group_cols in COLUMN_GROUPS.items():
                    if group_key == col or group_key in col: 
                        matched_group = group_cols
                        break
                
                if matched_group:
                    # 如果是群組關鍵字，將其展開為實際欄位 (只加入 DataFrame 中存在的)
                    for expanded_col in matched_group:
                        if expanded_col in display_df.columns:
                            expanded_columns.append(expanded_col)
                else:
                    # 如果不是群組關鍵字，保留原欄位
                    expanded_columns.append(col)
            
            # 更新 target_columns 並去重
            if expanded_columns:
                seen = set()
                target_columns = [x for x in expanded_columns if not (x in seen or seen.add(x))]

        if not target_columns:
            # 策略 B: 預設白名單 (Default Whitelist)
            DEFAULT_WHITELIST = [
                "客戶名稱",
                "品牌",
                "代理商",
                "活動名稱",
                "廣告格式",
                "受眾標籤",
                "開始日期",
                "結束日期",
                "投資金額",
                "有效曝光",
                "總點擊",
                "點擊率 (CTR%)",
                "觀看率 (VTR%)",
                "完整觀看數",
                "總互動",
                "互動率 (ER%)",
            ]
            target_columns = [c for c in DEFAULT_WHITELIST if c in display_df.columns]

        # 執行過濾
        if target_columns:
            # 去重並保持順序
            seen = set()
            final_cols = [x for x in target_columns if not (x in seen or seen.add(x))]
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