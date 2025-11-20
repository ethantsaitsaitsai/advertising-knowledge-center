from pydantic import BaseModel, Field, ConfigDict
from langchain_core.prompts import PromptTemplate
from schemas.state import AgentState
from config.llm import llm
from typing import Dict, Any, List

class StateUpdate(BaseModel):
    """
    用於解析使用者澄清回覆並擷取所有狀態更新的資料模型，
    包含確認的實體和新提供的過濾條件值。
    """
    model_config = ConfigDict(extra="forbid")

    confirmed_entities: List[str] = Field(
        default=[],
        description="使用者從候選清單中確認的完整、正確的實體名稱列表。"
    )
    updated_filters: Dict[str, Any] = Field(
        default_factory=dict,
        description="一個字典，包含使用者在其回覆中提供的任何新的或更新的過濾器值，例如 'date_start'、'date_end' 或其他缺失的資訊。"
    )

from prompts.state_updater_prompt import STATE_UPDATER_PROMPT

def state_updater_node(state: AgentState) -> Dict[str, Any]:
    """
    處理使用者對澄清問題的回應，使用已確認的實體和任何新提供的過濾條件值來更新狀態，並清除臨時欄位。
    """
    # Bind the LLM to the new Pydantic model for structured output
    structured_llm = llm.with_structured_output(StateUpdate)
    
    prompt = PromptTemplate.from_template(STATE_UPDATER_PROMPT)
    
    chain = prompt | structured_llm

    # Gather context for the prompt
    candidate_values = state.get("candidate_values", [])
    current_filters = state.get("extracted_filters", {})
    user_input = state["messages"][-1]["content"] if state["messages"] else ""

    # Invoke the chain
    result: StateUpdate = chain.invoke({
        "candidate_values": candidate_values,
        "current_filters": current_filters,
        "user_input": user_input,
    })

    # Merge the updated filters into the existing filters
    # The new values from the user's clarification take precedence
    final_filters = current_filters.copy()
    if result.updated_filters:
        final_filters.update(result.updated_filters)

    # Return the complete state update
    return {
        "extracted_filters": final_filters,
        "confirmed_entities": result.confirmed_entities,
        "ambiguous_terms": [],  # Clear resolved ambiguous terms
        "candidate_values": [],   # Clear candidates
        "missing_slots": [], # Assume missing slots are now filled if provided
        "expecting_user_clarification": False, # Reset the flag
    }
