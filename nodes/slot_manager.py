from schemas.state import AgentState
from config.llm import llm
from schemas.search_intent import SearchIntent
from prompts.slot_manager_prompt import SLOT_MANAGER_PROMPT


def slot_manager_node(state: AgentState):
    """
    Fills slots from the user's query, inheriting previous context, and updates the state.
    """
    # 1. 取得使用者輸入
    last_message = state['messages'][-1]
    user_input = last_message.get('content') if isinstance(last_message, dict) else last_message.content
    
    # 2. 【關鍵】取得舊狀態 (Context)
    # 從 state 中提取 current_filters, 如果是空的就給一個空 dict
    current_filters = state.get("extracted_filters", {})
    if not isinstance(current_filters, dict):
        current_filters = {}

    current_limit = state.get("limit") # 可能為 None

    # 3. 呼叫 LLM (注入 Context)
    structured_llm = llm.with_structured_output(SearchIntent)
    
    # 建構傳給 LLM 的 context 字串
    context_string = f"Filters: {current_filters}, Limit: {current_limit}"
    
    result: SearchIntent = structured_llm.invoke(
        SLOT_MANAGER_PROMPT.format(
            user_input=user_input,
            current_filters=context_string
        )
    )

    # 提取出的 Brand 必須被視為 "潛在模糊詞" 去做搜尋驗證。
    potential_search_terms = set(result.ambiguous_terms)
    if result.brands:
        potential_search_terms.update(result.brands)
    final_ambiguous_terms = list(potential_search_terms)

    # 4. 回傳更新後的狀態
    return {
        "intent_type": result.intent_type,
        "extracted_filters": {
            "brands": result.brands,
            "campaign_names": result.campaign_names,
            "industries": result.industries,
            "ad_formats": result.ad_formats,
            "target_segments": result.target_segments,
            "date_start": result.date_range.start,
            "date_end": result.date_range.end
        },
        "analysis_needs": result.analysis_needs.model_dump(),
        "ambiguous_terms": final_ambiguous_terms,
        "missing_slots": result.missing_info,
        "limit": result.limit
    }
