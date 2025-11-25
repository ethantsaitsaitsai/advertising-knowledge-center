from schemas.state import AgentState
from langchain_core.messages import AIMessage
from utils.formatter import format_sql_result_to_markdown
from typing import Dict, Any
import pandas as pd

def response_synthesizer(state: AgentState) -> Dict[str, Any]:
    """
    將查詢結果轉換為自然語言。
    優先使用 Data Fusion 的合併結果，若無則降級使用 MySQL 結果。
    """
    # 1. 嘗試獲取 Data Fusion 的結果 (包含成效數據)
    final_dataframe = state.get("final_dataframe")
    
    # 2. 獲取原始 MySQL 結果 (作為備案)
    sql_result = state.get("sql_result")
    sql_result_columns = state.get("sql_result_columns")
    
    # Handle cases where SQL execution failed or returned no data
    if state.get("error_message"):
        return {"messages": [AIMessage(content=f"抱歉，執行查詢時發生錯誤：{state['error_message']}")]}
    
    # 如果兩邊都沒資料
    is_final_data_empty = final_dataframe is None or len(final_dataframe) == 0
    is_sql_data_empty = not sql_result or not sql_result_columns

    if is_final_data_empty and is_sql_data_empty:
        return {"messages": [AIMessage(content="查無資料，請嘗試調整您的查詢條件。")]}
    
    response_text = ""
    current_row_count = 0

    # 3. 生成表格內容
    if not is_final_data_empty:
        # --- 路徑 A: 使用合併後的資料 (MySQL + ClickHouse) ---
        df = pd.DataFrame(final_dataframe)
        
        response_text = df.to_markdown(index=False, floatfmt=".2f")
        current_row_count = len(df)
        
        response_text = "### 📊 整合分析報表 (預算 & 成效)\n\n" + response_text

    else:
        # --- 路徑 B: 只有 MySQL 資料 ---
        response_text = format_sql_result_to_markdown(sql_result, sql_result_columns)
        current_row_count = len(sql_result)
    
    # 4. 【關鍵邏輯】動態添加 Limit 提示 (Smart Footer)
    DEFAULT_LIMIT = 20 
    if current_row_count == DEFAULT_LIMIT:
        footer_note = (
            f"\n\n---\n"
            f"💡 **顯示提示**：目前預設顯示前 **{DEFAULT_LIMIT}** 筆數據。\n"
            f"如果您需要更多資料（例如「看前 50 筆」或「全部」），請直接回覆告知，我會為您調整。"
        )
        response_text += footer_note
        
    # 5. 回傳最終訊息
    return {"messages": [AIMessage(content=response_text)]}
