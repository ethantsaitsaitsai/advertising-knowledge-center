from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict
from langchain_core.prompts import PromptTemplate
from schemas.state import AgentState
from config.llm import llm
from prompts.state_updater_prompt import STATE_UPDATER_PROMPT


# --- 1. 新增：定義明確的 Filter 結構 ---
class UpdatedFilters(BaseModel):
    """
    定義使用者可能想要更新的具體欄位。
    必須與 SlotManager 的 extracted_filters 結構保持一致。
    所有欄位皆為 Optional，因為使用者可能只更新其中一項。
    """
    model_config = ConfigDict(extra="forbid")  # 關鍵：禁止額外屬性

    brands: Optional[List[str]] = Field(default=None, description="品牌列表")
    industries: Optional[List[str]] = Field(default=None, description="產業列表")
    ad_formats: Optional[List[str]] = Field(default=None, description="廣告格式列表")
    target_segments: Optional[List[str]] = Field(default=None, description="受眾/鎖定條件列表")
    date_start: Optional[str] = Field(default=None, description="開始日期 (YYYY-MM-DD)")
    date_end: Optional[str] = Field(default=None, description="結束日期 (YYYY-MM-DD)")
    # 若有其他 metric 相關過濾條件也可加在此


# --- 2. 修改：主 Update 模型 ---
class StateUpdate(BaseModel):
    """
    用於解析使用者澄清回覆並擷取所有狀態更新的資料模型。
    """
    model_config = ConfigDict(extra="forbid")  # 關鍵：禁止額外屬性

    confirmed_entities: List[str] = Field(
        default_factory=list,  # 修正：list 預設應為 list
        description="使用者從候選清單中確認的完整、正確的實體名稱列表。"
    )
    # 修正：不再使用 Dict，改用強型別物件
    updated_filters: Optional[UpdatedFilters] = Field(
        default=None,
        description="包含使用者在其回覆中提供的任何新的或更新的過濾器值。"
    )


def state_updater_node(state: AgentState) -> Dict[str, Any]:
    """
    處理使用者對澄清問題的回應，使用已確認的實體和任何新提供的過濾條件值來更新狀態。
    """
    # Bind the LLM to the new Pydantic model
    structured_llm = llm.with_structured_output(StateUpdate)
    prompt = PromptTemplate.from_template(STATE_UPDATER_PROMPT)
    chain = prompt | structured_llm

    # Gather context
    candidate_values = state.get("candidate_values", [])
    current_filters = state.get("extracted_filters", {})
    # 防禦性編程：確保 messages 存在
    if state.get("messages"):
        last_message = state["messages"][-1]
        user_input = last_message.content if hasattr(last_message, 'content') else last_message['content']
    else:
        user_input = ""

    # Invoke the chain
    result: StateUpdate = chain.invoke({
        "candidate_values": candidate_values,
        "current_filters": current_filters,
        "user_input": user_input,
    })

    # Merge logic
    final_filters = current_filters.copy()
    # --- 3. 修改：Pydantic Merge 邏輯 ---
    if result.updated_filters:
        # 只取出非 None 的值進行更新 (exclude_none=True)
        updates = result.updated_filters.model_dump(exclude_none=True)
        final_filters.update(updates)

    return {
        "extracted_filters": final_filters,
        "confirmed_entities": result.confirmed_entities,
        "ambiguous_terms": [],   # Clear resolved terms
        "candidate_values": [],  # Clear candidates
        "missing_slots": [],     # Assume filled
        "expecting_user_clarification": False,  # Reset flag
    }
