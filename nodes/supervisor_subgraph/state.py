from typing import Annotated, List, Optional, Dict, Any
from typing_extensions import TypedDict
import operator
from langchain_core.messages import BaseMessage
from schemas.state import AgentState

class SupervisorSubState(AgentState):
    """
    State specifically for the Supervisor SubGraph.
    Inherits everything from global AgentState, adds internal loop variables.
    """
    # Internal variables for the Plan-and-Execute loop
    # These are NOT returned to the main graph unless explicitly mapped
    
    draft_decision: Optional[Dict[str, Any]] 
    internal_feedback: Annotated[List[BaseMessage], operator.add]
