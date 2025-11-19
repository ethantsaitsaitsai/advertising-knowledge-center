from typing import TypedDict, List, Optional, Annotated, Any, Dict
import operator
from langchain_core.messages import BaseMessage

class AgentState(TypedDict):
    """
    Represents the state of our graph for the data retrieval subgraph.
    
    Attributes:
        messages: The list of messages in the conversation.
        extracted_slots: e.g., {'industry': '金融', 'start_date': '2024-01-01'}
        missing_slots: e.g., ['start_date']
        generated_sql: LLM 產生的 SQL
        sql_result: DB 回傳的 Raw Data (List of tuples)
        error_message: 如果執行失敗的報錯
    """
    messages: Annotated[List[BaseMessage], operator.add]
    extracted_slots: Dict[str, Any]
    missing_slots: List[str]
    generated_sql: Optional[str]
    sql_result: Optional[str]
    error_message: Optional[str]
