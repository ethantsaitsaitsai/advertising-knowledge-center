from typing import TypedDict, List, Optional, Dict
from langgraph.graph import MessagesState

class GraphState(MessagesState):
    """
    Represents the state of our graph.
    
    Attributes:
        messages: The list of messages in the conversation.
        intent: The user's intent ('query' or 'chitchat').
        terms_to_check: A list of potentially ambiguous terms extracted from the query.
        clarified_terms: A dictionary mapping original terms to their clarified values.
        sql_is_safe: A boolean indicating if the generated SQL passed safety checks.
        safe_sql: The validated and potentially modified SQL query.
        error_message: Any error message generated during the process.
        sql_result: The result from the executed SQL query.
    """
    intent: Optional[str]
    terms_to_check: Optional[List[str]]
    clarified_terms: Optional[Dict[str, str]]
    sql_is_safe: Optional[bool]
    safe_sql: Optional[str]
    error_message: Optional[str]
    sql_result: Optional[str]
