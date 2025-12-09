
from typing import List, Optional, Literal
from pydantic import BaseModel, Field

class UserIntent(BaseModel):
    """
    Structured representation of the user's intent.
    This acts as a shared context for all agents.
    """
    query_level: Literal["contract", "strategy", "execution", "audience", "chitchat"] = Field(
        ..., description="The hierarchical level of the query."
    )
    
    entities: List[str] = Field(
        default_factory=list, 
        description="Extracted entity names (e.g. '悠遊卡', 'Nike')."
    )
    
    date_range: Optional[str] = Field(
        None, description="Time range mentioned (e.g. '2024', 'Last Month')."
    )
    
    needs_performance: bool = Field(
        False, description="Whether the user explicitly asks for performance metrics (Impressions, Clicks, CTR)."
    )
    
    is_ambiguous: bool = Field(
        False, description="True if the entity name seems ambiguous or needs clarification."
    )
    
    missing_info: List[str] = Field(
        default_factory=list,
        description="List of missing information that needs to be clarified (e.g. ['date_range'])."
    )
