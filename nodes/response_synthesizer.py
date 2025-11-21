from schemas.state import AgentState
from langchain_core.messages import AIMessage
from langchain_core.prompts import PromptTemplate
from config.llm import llm
from langchain_core.output_parsers import StrOutputParser
from utils.formatter import format_sql_result_to_markdown
from typing import Dict, Any


RESPONSE_SYNTHESIZER_PROMPT = """
# 角色
你是一個專業的數據分析師。
我會給你一段 SQL 查詢的原始數據（已經被格式化為 Markdown 表格）。

請完成以下兩件事：
1. **直接呈現表格**：將 Markdown 表格完整呈現出來。
2. **數據洞察 (Insight)**，例如：
   - 指出**預算最高**的項目是什麼。
   - 指出**案件數最多**的項目是什麼。
   - 若有任何異常數值（極高或極低），請標註出來。
   - 使用列點 (Bullet points) 呈現洞察。

# 輸入數據
{formatted_table_string}
"""


def response_synthesizer(state: AgentState) -> Dict[str, Any]:
    """
    將 SQL 結果轉換為自然語言，並動態添加 Limit 提示。
    """
    sql_result = state.get("sql_result")
    sql_result_columns = state.get("sql_result_columns")
    
    # Handle cases where SQL execution failed or returned no data
    if state.get("error_message"):
        return {"messages": [AIMessage(content=f"抱歉，執行查詢時發生錯誤：{state['error_message']}")]}
    if not sql_result or not sql_result_columns:
        return {"messages": [AIMessage(content="查無資料，請嘗試調整您的查詢條件。")]}
    
    # 1. 基本的回答生成 (這裡呼叫 LLM 或 Formatter)
    response_text = format_sql_result_to_markdown(sql_result, sql_result_columns)
    
    # 2. 【關鍵邏輯】動態添加 Limit 提示 (Smart Footer)
    # 判斷條件：如果回傳筆數剛好等於我們設定的預設上限 (例如 20)
    # 這代表資料庫裡可能還有更多資料被截斷了
    DEFAULT_LIMIT = 20 # 與 SQLGenerator 的預設限制保持一致
    
    if len(sql_result) == DEFAULT_LIMIT:
        footer_note = (
            f"\n\n---\n"
            f"💡 **顯示提示**：目前預設顯示前 **{DEFAULT_LIMIT}** 筆數據。\n"
            f"如果您需要更多資料（例如「看前 50 筆」或「全部」），請直接回覆告知，我會為您調整。"
        )
        response_text += footer_note
        
    # 3. 回傳最終訊息
    return {"messages": [AIMessage(content=response_text)]}
