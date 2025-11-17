from typing import Literal
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
        current_stage: Tracks the current stage of processing.
    """
    query: str = ""  # 提供預設值
    analysis_result: dict = {}  # 提供預設值
    clarified_query: str = ""
    sql_query: str = ""
    sql_result: str = ""
    formatted_response: str = ""
    date_filter: str | None = None
    current_stage: Literal[
        "query_analyzer",
        "ambiguity_resolver",
        "query_executor",
        "response_formatter",
        "human_in_the_loop",
        "end",
    ] = "query_analyzer"  # 提供預設值
