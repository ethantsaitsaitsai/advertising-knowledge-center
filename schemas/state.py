from typing import Annotated, List, Optional, Union, Sequence, Dict, Any
from typing_extensions import TypedDict
import operator
from langchain_core.messages import BaseMessage

class AgentState(TypedDict, total=False):
    """
    State for AKC Framework 3.0 - Intent-Centric Data Analyst Agent

    Simplified architecture:
    User → Intent Router → Data Analyst Agent → Output
    """
    # Conversation history
    messages: Annotated[Sequence[BaseMessage], operator.add]

    # Input field (for LangGraph Studio compatibility)
    input: Optional[str]

    # Routing decision ('DataAnalyst', 'Strategist', 'END')
    next: str

    # Context from Intent Router
    routing_context: Optional[Dict[str, Any]]
    # Contains: entity_keywords, time_keywords, analysis_hint, original_query

    # Data from Data Analyst Agent
    analyst_data: Optional[Dict[str, Any]]
    # Contains: status, data, generated_sql, count, etc.

    # Processed results (Markdown tables, reports)
    final_response: Optional[str]

    # Entity resolution results
    resolved_entities: Optional[List[Dict[str, Any]]]
    # Contains: id, name, type, table

    # Error handling
    error_message: Optional[str]