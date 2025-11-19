from schemas.state import AgentState
from langchain.messages import AIMessage

def response_synthesizer(state: AgentState) -> dict:
    """
    Synthesizes a final response from the SQL result.
    """
    user_question = state["messages"][-1].content
    sql_result = state.get("sql_result")

    if not sql_result:
        return {"messages": [AIMessage(content="我無法從資料庫中獲取到結果。")]}

    # This is a placeholder. A real implementation would use an LLM to generate a natural language response.
    response = f"根據您的問題 '{user_question}', 查詢結果如下：\n\n{sql_result}"
    
    return {"messages": [AIMessage(content=response)]}

