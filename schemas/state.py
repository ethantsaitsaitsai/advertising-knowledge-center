from typing import Annotated, List, Optional, Union, Sequence, Dict, Any
from typing_extensions import TypedDict
import operator
from langchain_core.messages import BaseMessage
from schemas.intent import UserIntent

class AgentState(TypedDict):
    """
    The state for the hierarchical multi-agent graph.
    """
    messages: Annotated[Sequence[BaseMessage], operator.add]
    
    # The next agent to act. 'FINISH' means the task is done.
    next: str 
    
    # Structured payload from Supervisor to Workers
    supervisor_payload: Optional[Dict[str, Any]]
    
    # Explicit Instructions from Supervisor (The "Manager's Command")
    supervisor_instructions: Optional[str]
    
    # Structured Intent from Intent Analyzer
    user_intent: Optional[UserIntent]
    
    # Shared data storage for inter-agent communication
    # Campaign Agent writes to 'campaign_data', Performance Agent reads from it.
    campaign_data: Optional[Dict[str, Any]]
    performance_data: Optional[Dict[str, Any]]
    
    # Store resolved Campaign IDs
    campaign_ids: Optional[List[int]]
    
    # Store resolved Ad Format IDs (for Execution level precision)
    ad_format_ids: Optional[List[int]]
    
    # State for ResponseSynthesizer
    final_dataframe: Optional[List[Dict[str, Any]]] # Raw data from tools
    was_default_metrics: Optional[bool] # Flag to indicate if default metrics were used
    budget_note: Optional[str] # Special note about budget
    
    # For ClickHouse Generator
    sql_result: Optional[List[Dict[str, Any]]] # Result from MySQL for ID mapping
    sql_result_columns: Optional[List[str]]
    
    # Original fields for compatibility with tools (if needed)
    extracted_filters: Optional[dict]
    analysis_needs: Optional[dict]