from langchain_core.messages import SystemMessage, AIMessage
from nodes.campaign_subgraph.graph import campaign_subgraph
from schemas.state import AgentState
from schemas.agent_tasks import CampaignTask
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

def campaign_node(state: AgentState):
    """
    Wrapper node that invokes the Campaign SubGraph.
    """
    # 1. Adapt Input
    payload = state.get("supervisor_payload")
    instructions = state.get("supervisor_instructions")
    
    # Validation
    if not payload:
        print("DEBUG [CampaignNode] Payload is empty for CampaignNode. Skipping.")
        return {}

    # LLM sometimes hallucinates the task_type as the class name. Correct it.
    if payload.get("task_type") == "CampaignTask":
        payload["task_type"] = "campaign_query"
        print("DEBUG [CampaignNode] Corrected 'CampaignTask' task_type to 'campaign_query'.")
        
    if payload.get("task_type") != "campaign_query":
        print(f"DEBUG [CampaignNode] Invalid task_type '{payload.get('task_type')}' for CampaignNode. Skipping.")
        return {}

    # Update payload with the explicit instruction text if present
    if instructions:
        payload["instruction_text"] = instructions

    try:
        task = CampaignTask(**payload)
    except Exception as e:
        print(f"DEBUG [CampaignNode] Payload validation failed: {e}")
        return {
            "messages": [AIMessage(content="系統錯誤：無法解析查詢指令 (Payload Error).")]
        }

    print(f"DEBUG [CampaignNode] Invoking SubGraph with Task Level: {task.query_level}")
    print(f"DEBUG [CampaignNode] is_ambiguous: {task.is_ambiguous}")
    print(f"DEBUG [CampaignNode] Manager Instructions: {task.instruction_text}")

    # 2. Invoke SubGraph with Initial State
    sub_state_input = {
        "task": task,
        "retry_count": 0,
        "step_count": 0, # Initialize step count
        "messages": [], # Start fresh for the subgraph, or pass filtered history
        "internal_thoughts": []
    }
    
    result_state = campaign_subgraph.invoke(sub_state_input)
    
    # 3. Adapt Output
    campaign_data = result_state.get("campaign_data")
    if campaign_data:
        campaign_data = convert_decimals(campaign_data)
    
    sql_error = result_state.get("sql_error")
    final_response_text = result_state.get("final_response")
    step_count = result_state.get("step_count", 0)

    print(f"DEBUG [CampaignNode] SubGraph finished in {step_count} steps.")

    # Only return user-facing messages (final_response).
    # Do NOT return internal status messages like "查詢成功" or "查詢失敗".
    # The supervisor/synthesizer should only see final user-facing content.
    result = {
        "campaign_data": campaign_data
    }
    
    # Extract IDs for Supervisor State
    if campaign_data and "data" in campaign_data:
        ids = []
        for row in campaign_data["data"]:
            # Check common ID keys
            cid = row.get("cmpid") or row.get("id") or row.get("one_campaign_id")
            if cid:
                ids.append(cid)
        if ids:
            result["campaign_ids"] = ids
            print(f"DEBUG [CampaignNode] Extracted {len(ids)} IDs: {ids}")

    # Only add a message if there's a user-facing response (e.g., clarification or final answer)
    if final_response_text:
        # This is a clarification message or final response from the router
        response_msg = AIMessage(content=final_response_text)
        response_msg.name = "CampaignAgent"
        result["messages"] = [response_msg]

        # If this is a clarification message (contains keywords), mark clarification_pending
        if any(keyword in final_response_text.lower() for keyword in ["澄清", "clarify", "選擇", "which", "哪一個"]):
            result["clarification_pending"] = True

    return result