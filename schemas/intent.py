from typing import List, Optional, Literal, Dict
from pydantic import BaseModel, Field

class DateRange(BaseModel):
    """Explicit date range with start and end."""
    start: Optional[str] = Field(None, description="Start date (YYYY-MM-DD).")
    end: Optional[str] = Field(None, description="End date (YYYY-MM-DD).")
    raw: Optional[str] = Field(None, description="The raw string user mentioned (e.g. '2025年').")

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
    
    date_range: Optional[DateRange] = Field(
        None, description="Time range mentioned."
    )
    
    needs_performance: bool = Field(
        False, description="Whether the user explicitly asks for performance metrics (Impressions, Clicks, CTR)."
    )
    
    is_ambiguous: bool = Field(
        False, description="True if the entity name seems ambiguous or needs clarification."
    )
    
    ambiguous_options: List[str] = Field(
        default_factory=list,
        description="List of ambiguous entity options found by the resolver (e.g., ['悠遊卡', '悠遊卡公司'])."
    )
    
    missing_info: List[str] = Field(
        default_factory=list,
        description="List of missing information that needs to be clarified (e.g. ['date_range'])."
    )
    
    analysis_needs: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Extracted metrics (e.g., 'Budget_Sum') and dimensions (e.g., 'Campaign_Name')."
    )