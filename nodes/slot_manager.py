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

    current_limit = state.get("limit")  # 可能為 None

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

    # --- [BEGIN] Hard-coded Post-processing Block ---
    # 解決 LLM 在複雜 Prompt 下行為不穩定的問題 (例如：漏加維度, 重複維度)

    # 1. 強制規則：如果 LLM 判斷使用者想看受眾分類 (display_segment_category == True)
    #    則強制將 "Segment_Category_Name" 加入 dimensions 列表
    if result.analysis_needs.display_segment_category:
        if "Segment_Category_Name" not in result.analysis_needs.dimensions:
            result.analysis_needs.dimensions.append("Segment_Category_Name")

    # 2. [Dependency Rule] 受眾 (Segment) 必須依附於 活動 (Campaign)
    #    如果維度中有受眾，強制加入 Campaign_Name，否則數據會因聚合而無法區分
    if "Segment_Category_Name" in result.analysis_needs.dimensions:
        if "Campaign_Name" not in result.analysis_needs.dimensions:
            print("DEBUG [SlotManager] Auto-adding 'Campaign_Name' due to Segment dependency.")
            # 插入到最前面，這樣在 GroupBy 時通常會排在前面，閱讀上較直觀
            result.analysis_needs.dimensions.insert(0, "Campaign_Name")

    # 3. 維度去重：移除 LLM 可能產生的重複維度
    if result.analysis_needs.dimensions:
        # Using dict.fromkeys to preserve order and remove duplicates
        unique_dimensions = list(dict.fromkeys(result.analysis_needs.dimensions))
        result.analysis_needs.dimensions = unique_dimensions
    # --- [END] Hard-coded Post-processing Block ---

    print(f"DEBUG [SlotManager] Extracted Analysis Needs: {result.analysis_needs.model_dump()}")

    # 4. 回傳更新後的狀態
    return {
        "intent_type": result.intent_type,
        "extracted_filters": {
            "brands": result.brands,
            "advertisers": result.advertisers,
            "agencies": result.agencies,
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
