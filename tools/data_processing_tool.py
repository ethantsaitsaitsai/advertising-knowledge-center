import pandas as pd
from typing import List, Dict, Any, Optional
from langchain_core.tools import tool

@tool
def pandas_processor(
    data: List[Dict[str, Any]],
    operation: str,
    groupby_col: Optional[str] = None,
    sum_col: Optional[str] = None,
    sort_col: Optional[str] = None,
    top_n: Optional[int] = None,
    merge_data: Optional[List[Dict[str, Any]]] = None,
    merge_on: Optional[str] = None,
    merge_how: str = "inner",
    ascending: bool = False,
    date_col: Optional[str] = None,
    new_col: Optional[str] = None,
    period: Optional[str] = None
) -> Dict[str, Any]:
    """
    對資料進行 Pandas 處理與分析，並回傳 Markdown 表格。

    Args:
        data: 原始資料列表 (List of Dicts)。
        operation: 執行的操作 ('groupby_sum', 'top_n', 'merge', 'add_time_period')。
        groupby_col: 分組欄位名稱。
        sum_col: 需要加總的數值欄位。
        sort_col: 排序依據的欄位。
        top_n: 取得前幾筆。
        merge_data: (用於 merge 操作) 要合併的第二個數據集。
        merge_on: (用於 merge 操作) 合併的鍵值欄位 (如 'format_name')。
        merge_how: (用於 merge 操作) 合併方式 ('inner', 'left', 'right', 'outer')。
        ascending: 排序方向 (True=升序, False=降序)。
        date_col: (用於 add_time_period) 來源日期欄位。
        new_col: (用於 add_time_period) 新生成的欄位名稱 (預設 'period')。
        period: (用於 add_time_period) 提取週期 ('month', 'year', 'quarter')。

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

        # 2. 保存處理後的數據（數值格式）供後續使用
        processed_data = result_df.to_dict('records')

        # 3. 格式化數值用於展示 (加上千分位)
        display_df = result_df.copy()
        for col in display_df.select_dtypes(include=['number']).columns:
            display_df[col] = display_df[col].apply(lambda x: f"{x:,.0f}")

        markdown_table = display_df.to_markdown(index=False)

        return {
            "status": "success",
            "markdown": markdown_table,
            "data": processed_data,  # 原始數值格式（供後續合併使用）
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