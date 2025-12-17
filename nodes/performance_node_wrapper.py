from langchain_core.messages import AIMessage
from nodes.performance_subgraph.graph import performance_subgraph
from schemas.state import AgentState
from schemas.agent_tasks import PerformanceTask
import json
from decimal import Decimal

def convert_decimals(obj):
    if isinstance(obj, list):
        return [convert_decimals(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: convert_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, Decimal):
        return float(obj)
    return obj

def performance_node(state: AgentState):
    """
    Wrapper that adapts the global AgentState to the Performance Subgraph.
    """
    messages = list(state["messages"])
    payload = state.get("supervisor_payload") or {}
    instructions = state.get("supervisor_instructions") or "Execute performance query."
    
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
    print(f"DEBUG [PerformanceNode] Manager Instructions: {instructions}")

    # 2. Construct Task Object (for consistent instruction passing)
    task = None
    try:
        task = PerformanceTask(
            task_type="performance_query",
            campaign_ids=explicit_ids,
            analysis_needs=analysis_needs,
            instruction_text=instructions # Pass the explicit instructions
        )
    except Exception as e:
        print(f"DEBUG [PerformanceNode] Could not create PerformanceTask object: {e}. Proceeding with loose params.")

    # 3. Invoke Subgraph
    # We pass only necessary fields. 
    # Important: 'messages' should be passed so the LLM sees the chat history.
    sub_input = {
        "task": task, # Now passing the structured task
        "campaign_ids": explicit_ids,
        "format_ids": filters.get("ad_format_ids", []),
        "filters": filters,
        "analysis_needs": analysis_needs,
        "retry_count": 0,
        "step_count": 0,
        "was_default_metrics": False,
        "internal_thoughts": [],
        "messages": messages, # Keep for context
    }
    
    result = performance_subgraph.invoke(sub_input)
    
    # 4. Adapt Output back to Global State
    final_dataframe = result.get("final_dataframe", [])
    was_default = result.get("was_default_metrics", False)
    sql_error = result.get("sql_error")
    generated_sql = result.get("generated_sql")

    # CRITICAL: Only output message on ERROR, not on success
    # Success case will be handled by ResponseSynthesizer with proper analysis
    if sql_error:
        msg_content = f"成效查詢失敗: {sql_error}"
        response_msg = AIMessage(content=msg_content, name="PerformanceAgent")
    else:
        # Silent success - data will be processed by DataFusion and Synthesizer
        # No redundant "成效查詢成功，已找到 X 筆數據。" message
        response_msg = AIMessage(content="", name="PerformanceAgent")
    
    # Construct Performance Data Wrapper (similar to Campaign Data)
    performance_data_wrapper = {
        "data": final_dataframe,
        "generated_sqls": [generated_sql] if generated_sql else []
    }
    
    # Apply Decimal Conversion
    if final_dataframe:
        final_dataframe = convert_decimals(final_dataframe)
    if performance_data_wrapper:
        performance_data_wrapper = convert_decimals(performance_data_wrapper)

    return {
        "messages": [response_msg],
        "final_dataframe": final_dataframe,
        "was_default_metrics": was_default,
        "performance_data": performance_data_wrapper
    }
