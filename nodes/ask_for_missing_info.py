from langchain.messages import AIMessage
from schemas.state import AgentState
from typing import Literal

def ask_for_missing_info(state: AgentState) -> dict:
    """
    When SlotManager finds that information is insufficient, this node is responsible for generating follow-up questions.
    """
    missing = state.get("missing_slots", [])
    
    # Simple rule judgment (can also be changed to use LLM to generate more natural conversation)
    if "date_range" in missing:
        response = "為了提供準確的數據，請問您想查詢的『時間範圍』是？（例如：2024年全年度、上個月、或是具體日期）"
    elif "industry" in missing:
        response = "請問您想查詢哪個『產業』或『品牌』的數據呢？"
    else:
        response = f"我還需要以下資訊才能開始查詢：{', '.join(missing)}。請補充說明。"
    
    # Return the generated message, which will become what the Agent says to the User
    return {"messages": [AIMessage(content=response)]}
