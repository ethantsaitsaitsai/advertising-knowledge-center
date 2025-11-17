from typing import Literal, List, Dict, Any
from pydantic import Field
from langgraph.graph import MessagesState


class GraphState(MessagesState):
    """
    Represents the state of our graph.
    Attributes:
        messages: Conversation history (inherited from MessagesState).
        query: The original user query.
        analysis_result: Result of query analysis.
        clarified_query: The query after ambiguity resolution.
        sql_query: The generated SQL query.
        sql_result: The result from executing the SQL query.
        formatted_response: The final natural language response.
        date_filter: An optional SQL condition string for date filtering.
        term_clarifications: A list of confirmed term clarifications.
        pending_clarification: Information about a term currently pending user clarification.
        current_stage: Tracks the current stage of processing.
    """
    query: str = ""
    analysis_result: Dict[str, Any] = Field(default_factory=dict)
    clarified_query: str = ""
    sql_query: str = ""
    sql_result: str = ""
    formatted_response: str = ""
    date_filter: str | None = None
    term_clarifications: List[Dict[str, str]] = Field(default_factory=list)
    pending_clarification: Dict[str, Any] = Field(default_factory=dict)
    current_stage: Literal[
        "query_analyzer",
        "ambiguity_resolver",
        "query_executor",
        "response_formatter",
        "human_in_the_loop",
        "end",
    ] = "query_analyzer"
