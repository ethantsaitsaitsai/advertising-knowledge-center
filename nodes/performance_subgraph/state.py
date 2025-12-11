from typing import List, Optional, Dict, Any, Union
from typing_extensions import TypedDict, Annotated
import operator
from schemas.agent_tasks import PerformanceTask

class PerformanceSubState(TypedDict):
    """
    State specifically for the Performance Agent (SubGraph).
    """
    task: Optional[PerformanceTask] # Can be None if derived from context
    
    # Context Data (passed from wrapper)
    campaign_ids: List[int]
    format_ids: List[int]
    filters: Dict[str, Any]
    analysis_needs: Dict[str, Any]
    
    internal_thoughts: Annotated[List[str], operator.add] 
    
    generated_sql: Optional[str]
    sql_error: Optional[str]
    retry_count: int
    
    final_dataframe: Optional[List[Dict[str, Any]]] # The result data
    was_default_metrics: bool
    
    final_response: Optional[str]
    
    # Routing & Safety
    next_action: Optional[str]
    step_count: int