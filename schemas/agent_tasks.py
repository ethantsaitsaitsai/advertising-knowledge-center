from typing import List, Dict, Any, Literal, Optional
from pydantic import BaseModel, Field

class CampaignTask(BaseModel):
    """
    Task for the CampaignAgent (MySQL Expert).
    Use this when you need to query campaign metadata, contracts, budgets, or strategy details from MySQL.
    """
    task_type: str = "campaign_query"
    
    query_level: Literal["contract", "strategy", "execution", "audience"] = Field(
        ..., 
        description="The hierarchical level of the query (contract/strategy/execution/audience)."
    )
    
    campaign_ids: Optional[List[int]] = Field(
        None,
        description="Optional list of known Campaign IDs to filter by."
    )
    
    filters: Dict[str, Any] = Field(
        default_factory=dict, 
        description="Filtering conditions extracted from user intent (e.g., {'brands': ['Nike'], 'date_range': 'This Year'})."
    )
    
    analysis_needs: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Metrics (SELECT) and Dimensions (GROUP BY) required by the user."
    )
    
    instruction_text: str = Field(
        ..., 
        description="Clear, natural language instructions for the Campaign Agent."
    )

class PerformanceTask(BaseModel):
    """
    Task for the PerformanceAgent (ClickHouse Expert).
    Use this ONLY when you ALREADY have Campaign IDs and need to query performance metrics (Impressions, Clicks, CTR, etc.).
    """
    task_type: str = "performance_query"
    
    campaign_ids: List[int] = Field(
        ..., 
        description="A list of specific Campaign IDs (integers) to query performance for."
    )
    
    analysis_needs: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Performance metrics to calculate (e.g., {'metrics': ['CTR', 'VTR']})."
    )
    
    instruction_text: str = Field(
        ..., 
        description="Clear, natural language instructions for the Performance Agent."
    )

class SynthesizeTask(BaseModel):
    """
    Task to synthesize the final response.
    Use this when you have successfully retrieved data (Campaign or Performance) and want to present it to the user.
    """
    task_type: str = "synthesize"
    
    context: str = Field(
        ...,
        description="Brief context about what data was retrieved to help the synthesizer focus."
    )

class FinishTask(BaseModel):
    """
    Task to end the supervision process.
    Use this when:
    1. The user's request has been fully answered.
    2. You need to ask the user a clarification question.
    3. The system cannot proceed without further user input.
    """
    task_type: str = "finish"
    
    reason: str = Field(
        ..., 
        description="The reason for finishing (e.g., 'Clarification needed', 'Task completed')."
    )

    final_instruction: Optional[str] = Field(
        None,
        description="Optional instructions for the final response synthesizer (if needed)."
    )
