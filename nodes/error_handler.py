from schemas.state import AgentState
from langchain_core.messages import AIMessage

def error_handler(state: AgentState) -> dict:
    """
    Handles errors from the SQLExecutor node.
    """
    error_message = state.get("error_message")
    
    # This is a placeholder. A real implementation could involve more sophisticated retry logic
    # or providing suggestions to the user on how to fix their query.
    response = f"執行查詢時發生錯誤，無法完成您的請求。\n錯誤詳情: {error_message}"

    return {"messages": [AIMessage(content=response)]}

