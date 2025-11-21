from typing import List, Optional
from pydantic import BaseModel, Field
from schemas.state import AgentState
from config.llm import llm
from prompts.state_updater_prompt import STATE_UPDATER_PROMPT
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.runnables import RunnablePassthrough
from schemas.search_intent import DateRange


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


class StateUpdate(BaseModel):
    """
    The structured output from the StateUpdater node.
    """
    confirmed_filters: ConfirmedFilters = Field(
        ...,
        description="The filters that have been confirmed by the user."
    )
    date_range: Optional[DateRange] = Field(None, description="若使用者有補充日期，則填寫")
    ambiguous_terms: List[str] = Field(
        default_factory=list,
        description="The list of ambiguous terms should be cleared after confirmation."
    )


def state_updater_node(state: AgentState):
    """
    Updates the agent's state based on user's clarification.
    """
    # 1. Get the user's latest message and the candidate values from the state
    last_message = state['messages'][-1]
    # Check if last_message is a dict or a BaseMessage object
    user_input = last_message.get('content') if isinstance(last_message, dict) else last_message.content

    candidate_values = state.get('candidate_values', [])

    if not candidate_values:
        # If there are no candidates, there's nothing to confirm.
        # We can just clear the ambiguous terms and proceed.
        return {
            "ambiguous_terms": [],
            "candidate_values": [],
            "expecting_user_clarification": False
        }

    # 2. Setup PydanticOutputParser
    parser = PydanticOutputParser(pydantic_object=StateUpdate)

    # 3. Create the chain with the prompt, LLM, and parser
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

    # 5. Update the extracted_filters in the state
    # Create a copy to avoid modifying the original state directly
    updated_filters = state.get('extracted_filters', {}).copy()
    confirmed = result.confirmed_filters
    if confirmed.brands:
        # Use a set to avoid duplicates, then convert back to a list
        updated_brands = list(set(updated_filters.get('brands', []) + confirmed.brands))
        updated_filters['brands'] = updated_brands
    if confirmed.campaign_names:
        updated_campaigns = list(set(updated_filters.get('campaign_names', []) + confirmed.campaign_names))
        updated_filters['campaign_names'] = updated_campaigns

    if confirmed.advertisers:
        updated_advertisers = list(set(updated_filters.get('advertisers', []) + confirmed.advertisers))
        updated_filters['advertisers'] = updated_advertisers

    if confirmed.agencies:
        updated_agencies = list(set(updated_filters.get('agencies', []) + confirmed.agencies))
        updated_filters['agencies'] = updated_agencies
    # Update date_range if provided
    if result.date_range and (result.date_range.start or result.date_range.end):
        updated_filters['date_start'] = result.date_range.start
        updated_filters['date_end'] = result.date_range.end
    # 6. Return the updated state
    return {
        "extracted_filters": updated_filters,
        "ambiguous_terms": [],  # Clear ambiguous terms after confirmation
        "candidate_values": [],  # Clear candidates after confirmation
        "expecting_user_clarification": False  # No longer waiting for user
    }
