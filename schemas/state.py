from typing import TypedDict, List, Union, Optional
from langgraph.graph import MessagesState
from langchain_core.messages import BaseMessage

class GraphState(MessagesState):
    """
    Represents the state of our graph.
    The primary attribute is `messages`, which is a list of messages in the conversation.
    This state is managed by inheriting from MessagesState.
    """
    # Inherits 'messages: List[BaseMessage]' from MessagesState
    sql_is_safe: Optional[bool]
    safe_sql: Optional[str]
    error_message: Optional[str]
    sql_result: Optional[str]
