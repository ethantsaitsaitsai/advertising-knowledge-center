from schemas.state import AgentState
from config.llm import llm
from schemas.search_intent import SearchIntent
from prompts.slot_manager_prompt import SLOT_MANAGER_PROMPT


def slot_manager_node(state: AgentState):
    """
    Fills slots from the user's query and updates the state with a more structured format.
    """
    last_message = state['messages'][-1]
    user_input = last_message.content if hasattr(last_message, 'content') else last_message['content']

    # 綁定新的 Schema
    structured_llm = llm.with_structured_output(SearchIntent)

    # 執行提取
    result: SearchIntent = structured_llm.invoke(
        SLOT_MANAGER_PROMPT.format(user_input=user_input)
    )

    # 提取出的 Brand 必須被視為 "潛在模糊詞" 去做搜尋驗證。

    # 1. 合併 LLM 認為模糊的詞 + LLM 提取出的實體
    potential_search_terms = set(result.ambiguous_terms)

    # 將提取到的 brands 也加入待搜尋清單 (假設這是您要驗證的核心實體)
    if result.brands:
        potential_search_terms.update(result.brands)

    # 轉換回 list
    final_ambiguous_terms = list(potential_search_terms)

    return {
        "intent_type": result.intent_type,
        "extracted_filters": {
            "brands": result.brands,
            "industries": result.industries,
            "ad_formats": result.ad_formats,
            "target_segments": result.target_segments,
            "date_start": result.date_range.start,
            "date_end": result.date_range.end
        },
        "analysis_needs": {
            "metrics": result.metrics
        },
        "ambiguous_terms": final_ambiguous_terms,
        "missing_slots": result.missing_info
    }
