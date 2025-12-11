from langchain_core.messages import AIMessage
from nodes.performance_subgraph.graph import performance_subgraph
from schemas.state import AgentState
import json

def performance_node(state: AgentState):
    """
    Wrapper that adapts the global AgentState to the Performance Subgraph.
    """
    messages = list(state["messages"])
    payload = state.get("supervisor_payload") or {}
    
    # 1. Extract Context (IDs, Filters, Needs)
    explicit_ids = payload.get("campaign_ids", [])
    analysis_needs = payload.get("analysis_needs", {}) or {}
    
    # Fallback ID Extraction
    if not explicit_ids:
        campaign_data = state.get("campaign_data")
        if campaign_data and "data" in campaign_data:
            rows = campaign_data["data"]
            if rows:
                first_row = rows[0]
                id_key = next((k for k in first_row.keys() if k.lower() in ['cmpid', 'id']), None)
                if id_key:
                    explicit_ids = [row[id_key] for row in rows if row.get(id_key)]
    
    # Extract Filters (Merge payload > extracted_filters > user_intent)
    filters = state.get("extracted_filters", {}).copy()
    if "filters" in payload:
        filters.update(payload["filters"])
        
    user_intent = state.get("user_intent")
    if user_intent and user_intent.date_range and "date_range" not in filters:
        filters["date_range"] = user_intent.date_range

    if not explicit_ids:
        return {
            "messages": [AIMessage(content="無法執行成效查詢：缺少 Campaign ID。", name="PerformanceAgent")]
        }

    print(f"DEBUG [PerformanceNode] Invoking Subgraph. IDs={len(explicit_ids)}, Filters={filters}")

    # 2. Invoke Subgraph
    # We pass only necessary fields. 
    # Important: 'messages' should be passed so the LLM sees the chat history.
    sub_input = {
        "task": None,
        "campaign_ids": explicit_ids,
        "format_ids": filters.get("ad_format_ids", []),
        "filters": filters,
        "analysis_needs": analysis_needs,
        "retry_count": 0,
        "step_count": 0,
        "was_default_metrics": False,
        "internal_thoughts": [],
        "messages": messages, # Keep for context if needed, though PerformanceAgent uses structured prompt
    }
    
    result = performance_subgraph.invoke(sub_input)
    
    # 3. Adapt Output back to Global State
    final_dataframe = result.get("final_dataframe", [])
    was_default = result.get("was_default_metrics", False)
    sql_error = result.get("sql_error")
    
    if sql_error:
        msg_content = f"成效查詢失敗: {sql_error}"
    elif final_dataframe:
        count = len(final_dataframe)
        msg_content = f"成效查詢成功，已找到 {count} 筆數據。"
    else:
        msg_content = "成效查詢無資料。"
        
    response_msg = AIMessage(content=msg_content, name="PerformanceAgent")

    return {
        "messages": [response_msg],
        "final_dataframe": final_dataframe,
        "was_default_metrics": was_default
    }