from typing import Optional, Dict, Any, List
from datetime import date
from pydantic import BaseModel, Field
from schemas.state import AgentState
from config.llm import llm

# Pydantic model for slot filling
class Slots(BaseModel):
    """
    Represents the slots to be filled from the user's query.
    """
    industry: Optional[str] = Field(None, description="客戶產業類別")
    brand: Optional[str] = Field(None, description="品牌")
    date_range: Optional[Dict[str, Optional[date]]] = Field(None, description="一個包含 'start_date' 和 'end_date' 的字典")

def slot_manager(state: AgentState) -> dict:
    """
    Fills slots from the user's query and updates the state.

    Args:
        state (AgentState): The current state of the agent.

    Returns:
        dict: A dictionary containing the updated state fields.
    """
    # Create a structured LLM from the Pydantic model
    structured_llm = llm.with_structured_output(Slots)

    # Get the whole conversation
    messages = state["messages"]

    # Extract slots from the user message
    slots = structured_llm.invoke(messages)

    # Update the extracted_slots in the state
    extracted_slots = {
        "industry": slots.industry,
        "brand": slots.brand,
        "date_range": slots.date_range,
    }
    
    # Remove None values from extracted_slots
    extracted_slots = {k: v for k, v in extracted_slots.items() if v is not None}

    # Check for critical missing information
    missing_slots = []
    if not extracted_slots.get("date_range") or not extracted_slots.get("date_range", {}).get("start_date") or not extracted_slots.get("date_range", {}).get("end_date"):
        missing_slots.append("date_range")

    return {
        "extracted_slots": extracted_slots,
        "missing_slots": missing_slots,
    }


