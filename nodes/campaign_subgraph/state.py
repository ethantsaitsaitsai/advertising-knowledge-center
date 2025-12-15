from typing import List, Optional, Dict, Any, Union
from typing_extensions import TypedDict, Annotated
import operator
from schemas.agent_tasks import CampaignTask

class CampaignSubState(TypedDict):
    """
    State specifically for the Campaign Agent (SubGraph).
    """
    task: CampaignTask
    internal_thoughts: Annotated[List[str], operator.add] 
    
    generated_sql: Optional[str]
    sql_error: Optional[str]
    retry_count: int
    
    # Store structured search results for decision making
    search_results: Optional[List[str]]
    
    campaign_data: Optional[Dict[str, Any]]
    final_response: Optional[str]
    
    # Routing & Safety
    next_action: Optional[str]
    step_count: int # Track how many times the router has been called