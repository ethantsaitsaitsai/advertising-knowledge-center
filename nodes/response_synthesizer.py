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
    Synthesizes a final response from the SQL result, formatting it into a Markdown table
    and adding data insights using an LLM.
    """
    sql_result = state.get("sql_result")
    sql_result_columns = state.get("sql_result_columns")

    # Handle cases where SQL execution failed or returned no data
    if state.get("error_message"):
        return {"messages": [AIMessage(content=f"抱歉，執行查詢時發生錯誤：{state['error_message']}")]}
    if not sql_result or not sql_result_columns:
        return {"messages": [AIMessage(content="查無資料，請嘗試調整您的查詢條件。")]}

    # Format the SQL result into a Markdown table
    formatted_table_string = format_sql_result_to_markdown(sql_result, sql_result_columns)

    # Use LLM to generate insights based on the formatted table
    prompt = PromptTemplate.from_template(RESPONSE_SYNTHESIZER_PROMPT)
    chain = prompt | llm | StrOutputParser()

    response_content = chain.invoke({"formatted_table_string": formatted_table_string})
    return {"messages": [AIMessage(content=response_content)]}
