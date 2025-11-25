from typing_extensions import TypedDict, List, Optional, Annotated, Any
import operator
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    """
    Represents the state of our graph for the data retrieval subgraph.
    Attributes:
        messages: The list of messages in the conversation.
        extracted_filters: Clean filtering conditions for the SQL WHERE clause.
        analysis_needs: Metrics for the SQL SELECT clause.
        missing_slots: e.g., ['date_range']
        ambiguous_terms: e.g., ['悠遊卡']
        candidate_values: e.g., ['悠遊卡Q1', '悠遊卡Q2']
        confirmed_entities: e.g., ['悠遊卡Q1']
        generated_sql: LLM 產生的 SQL
        sql_result: DB 回傳的 Raw Data (List of tuples)
        error_message: 如果執行失敗的報錯
        expecting_user_clarification: Whether the agent is currently expecting a clarification response from the user.
    """
    messages: Annotated[List[BaseMessage], operator.add]
    # Improved structure
    extracted_filters: dict  # Stores clean filtering conditions
    analysis_needs: dict     # Stores metrics
    missing_slots: List[str]
    ambiguous_terms: List[str]
    candidate_values: List[dict]
    confirmed_entities: List[str]
    generated_sql: Optional[str]
    clickhouse_sql: Optional[str]
    clickhouse_result: Optional[List[dict]]
    final_result_text: Optional[str]
    sql_result: Optional[List[Any]]
    sql_result_columns: Optional[List[str]]
    error_message: Optional[str]
    is_valid_sql: bool
    expecting_user_clarification: Optional[bool]
    intent_type: Optional[str]
    final_dataframe: Optional[List[dict]]
