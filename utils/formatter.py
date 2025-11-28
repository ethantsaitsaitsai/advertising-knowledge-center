import pandas as pd
from decimal import Decimal
from typing import List, Tuple, Any
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta


def split_date_range(start_str: str, end_str: str) -> list[tuple[str, str]]:
    """
    Splits a date range into yearly intervals to avoid DB timeouts.
    Returns a list of (start_date, end_date) tuples.
    Handles boundaries correctly (e.g., [A, B], [B+1, C]).
    """
    try:
        start = datetime.strptime(start_str, "%Y-%m-%d")
        end = datetime.strptime(end_str, "%Y-%m-%d")
    except (ValueError, TypeError):
        # If date parsing fails, return original range as is
        return [(start_str, end_str)]

    if start > end:
        return [(start_str, end_str)]

    intervals = []
    current = start
    while current <= end:
        # Move forward by 1 year (or 365 days)
        # Using 365 days might be safer for 'BETWEEN' if we want strictly controlled chunks
        # But relativedelta(years=1) is more logical for "Yearly" split.
        next_hop = current + relativedelta(years=1) - timedelta(days=1)
        
        if next_hop >= end:
            intervals.append((current.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")))
            break
        else:
            intervals.append((current.strftime("%Y-%m-%d"), next_hop.strftime("%Y-%m-%d")))
            current = next_hop + timedelta(days=1)
            
    return intervals


def format_sql_result_to_markdown(data: List[Tuple[Any, ...]], columns: List[str]) -> str:
    """
    將 SQL 執行結果 (List of Tuples) 轉為美觀的 Markdown 表格

    Args:
        data: [('Post Ad...', 1, Decimal('400000')...), ...]
        columns: ['廣告格式', '案件數', '總預算', '平均預算', '備註']
    """
    if not data:
        return "查無資料。"

    # 1. 轉換為 DataFrame 方便處理
    df = pd.DataFrame(data, columns=columns)

    # 2. 數值格式化 (千分位 + 去除多餘小數)
    # 假設後三欄是金額，進行格式化處理
    # 為了避免硬編碼列名，我們嘗試根據名稱或數據類型判斷

    # 識別潛在的金額相關列
    # 通常金額列會包含 "預算", "金額", "費用", "TWD", "$" 等關鍵字
    # 或者其數據類型為 Decimal 或浮點數
    amount_cols = []
    for col in df.columns:
        if any(keyword in col for keyword in ["預算", "金額", "費用", "TWD", "$", "budget", "amount", "cost"]):
            amount_cols.append(col)
        # 也可以檢查數據類型，但DataFrame可能在創建時將Decimal轉為float
        elif len(df) > 0 and isinstance(df[col].iloc[0], (Decimal, float)):
            if col not in amount_cols:  # 避免重複添加
                amount_cols.append(col)

    for col in amount_cols:
        # 檢查是否為數字類型，避免報錯
        if pd.api.types.is_numeric_dtype(df[col]) or (len(df) > 0 and isinstance(df[col].iloc[0], Decimal)):
            df[col] = df[col].apply(lambda x: f"${int(x):,}" if pd.notna(x) else "$0")  # 使用 pd.notna 處理 NaN/None

    # 3. 輸出 Markdown
    return df.to_markdown(index=False)
