from typing import List, Optional
from pydantic import BaseModel, Field
from schemas.state import AgentState
from config.llm import llm
from prompts.state_updater_prompt import STATE_UPDATER_PROMPT
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.runnables import RunnablePassthrough
from schemas.search_intent import DateRange, ScopedTerm


class ConfirmedFilters(BaseModel):
    """
    The filters that have been confirmed by the user.
    """
    brands: List[str] = Field(
        default_factory=list,
        description="List of confirmed brand names."
    )
    advertisers: List[str] = Field(
        default_factory=list,
        description="List of confirmed advertiser names."
    )
    agencies: List[str] = Field(
        default_factory=list,
        description="List of confirmed agency names."
    )
    campaign_names: List[str] = Field(
        default_factory=list,
        description="List of confirmed campaign names."
    )
    industries: List[str] = Field(
        default_factory=list,
        description="List of confirmed industry names."
    )


class StateUpdate(BaseModel):
    """
    The structured output from the StateUpdater node.
    """
    confirmed_filters: ConfirmedFilters = Field(
        ...,
        description="The filters that have been confirmed by the user."
    )
    date_range: Optional[DateRange] = Field(None, description="若使用者有補充日期，則填寫")
    ambiguous_terms: List[ScopedTerm] = Field(
        default_factory=list,
        description="若使用者提出新問題或反問，將關鍵字填入此處。否則為空。"
    )


def state_updater_node(state: AgentState):
    """
    Updates the agent's state based on user's clarification.
    """
    print(f"DEBUG [StateUpdater] Incoming Analysis Needs: {state.get('analysis_needs')}")

    # 1. Get the user's latest message and the candidate values from the state
    last_message = state['messages'][-1]
    user_input = last_message.get('content') if isinstance(last_message, dict) else last_message.content

    candidate_values = state.get('candidate_values', [])
    missing_slots = state.get('missing_slots', [])

    # If neither candidates nor missing info exists, we might be in a weird state, 
    # but let's try to parse user input anyway (e.g., they might be providing info unprompted).
    
    # 2. Setup PydanticOutputParser
    parser = PydanticOutputParser(pydantic_object=StateUpdate)

    # 3. Create the chain
    chain = RunnablePassthrough.assign(
        format_instructions=lambda _: parser.get_format_instructions(),
        candidate_values=lambda x: x['candidate_values'],
        user_input=lambda x: x['user_input']
    ) | STATE_UPDATER_PROMPT | llm | parser

    # 4. Invoke the chain
    result: StateUpdate = chain.invoke({
        "candidate_values": candidate_values,
        "user_input": user_input
    })

    # 5. Update logic
    updated_filters = state.get('extracted_filters', {}).copy()
    confirmed = result.confirmed_filters
    
    # Update confirmed filters (Replacing logic to support context switching)
    if confirmed.brands:
        updated_filters['brands'] = confirmed.brands
    if confirmed.campaign_names:
        updated_filters['campaign_names'] = confirmed.campaign_names
    if confirmed.advertisers:
        updated_filters['advertisers'] = confirmed.advertisers
    if confirmed.agencies:
        updated_filters['agencies'] = confirmed.agencies
    if confirmed.industries:
        updated_filters['industries'] = confirmed.industries

    # Update date_range and handle missing_slots
    updated_missing_slots = missing_slots.copy()
    if result.date_range and (result.date_range.start or result.date_range.end):
        updated_filters['date_start'] = result.date_range.start
        updated_filters['date_end'] = result.date_range.end
        
        # Remove 'date_range' from missing_slots if it was provided
        if "date_range" in updated_missing_slots:
            updated_missing_slots.remove("date_range")

    # Handle ambiguous terms (Exploration Mode)
    # If there are new ambiguous terms, we should clear extracted_filters (or not? Prompt says clear)
    # Prompt says: "若進入探索模式，extracted_filters 應為空（或保留舊有）"
    # Let's keep it simple: pass ambiguous_terms. If ambiguous_terms is present, Graph routing will send to EntitySearch.
    
    return {
        "extracted_filters": updated_filters,
        "analysis_needs": state.get('analysis_needs', {}),
        "ambiguous_terms": result.ambiguous_terms, # Pass new search terms
        "candidate_values": [], # Clear candidates as we are moving forward or restarting search
        "missing_slots": updated_missing_slots, # Update missing slots status
        "expecting_user_clarification": False 
    }