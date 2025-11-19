from pydantic import BaseModel, Field
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import Runnable
from langchain_core.output_parsers import PydanticOutputParser
from schemas.state import AgentState
from config.llm import llm
from typing import Dict, Any, List

class ConfirmedEntities(BaseModel):
    """Data model for the confirmed entities from the user's selection."""
    confirmed_list: List[str] = Field(description="The final list of entities confirmed by the user.")

# Create a parser for the ConfirmedEntities model
parser = PydanticOutputParser(pydantic_object=ConfirmedEntities)

# Define the prompt for updating the state
state_updater_prompt_template = PromptTemplate(
    template="""
# 角色
你是一個狀態更新器。你的任務是理解使用者從候選清單中做出的選擇，並輸出最終、已確認的實體清單。

# 背景
- 系統向使用者展示了這個候選清單: {candidate_values}
- 使用者的回覆是: "{user_response}"

# 指示
1.  分析使用者的回覆，確定他們選擇了哪些候選項目。
2.  使用者可能透過編號、名稱選擇，或者說「全部」或「除了...之外」。
3.  你唯一的輸出應該是符合以下格式的 JSON 物件。請勿添加任何其他文字。

{format_instructions}
""",
    input_variables=["candidate_values", "user_response"],
    partial_variables={"format_instructions": parser.get_format_instructions()},
)

def get_state_updater_chain() -> Runnable:
    """
    Get the chain for updating the state with confirmed entities.
    """
    return state_updater_prompt_template | llm | parser

def state_updater_node(state: AgentState) -> Dict[str, Any]:
    """
    Processes the user's response to a clarification question, updates the state with
    confirmed entities, and clears temporary fields.
    """
    state_updater_chain = get_state_updater_chain()
    
    candidate_values = state.get("candidate_values", [])
    user_response = state["messages"][-1].content if state["messages"] else ""
    
    if not candidate_values or not user_response:
        return {}

    # Invoke the chain to get the confirmed entities
    result: ConfirmedEntities = state_updater_chain.invoke({
        "candidate_values": candidate_values,
        "user_response": user_response,
    })
    
    # Update state: set confirmed_entities and clear temporary fields
    return {
        "confirmed_entities": result.confirmed_list,
        "ambiguous_terms": [], # Clear the ambiguous term that has been resolved
        "candidate_values": [],  # Clear the candidates list
        "expecting_user_clarification": False, # No longer expecting clarification
    }
