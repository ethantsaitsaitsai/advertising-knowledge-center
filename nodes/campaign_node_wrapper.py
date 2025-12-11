from langchain_core.messages import SystemMessage, AIMessage
from nodes.campaign_subgraph.graph import campaign_subgraph
from schemas.state import AgentState
from schemas.agent_tasks import CampaignTask
import json

def campaign_node(state: AgentState):
    """
    Wrapper node that invokes the Campaign SubGraph.
    """
    # 1. Adapt Input
    payload = state.get("supervisor_payload")
    
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

    try:
        task = CampaignTask(**payload)
    except Exception as e:
        print(f"DEBUG [CampaignNode] Payload validation failed: {e}")
        return {
            "messages": [AIMessage(content="系統錯誤：無法解析查詢指令 (Payload Error).")]
        }

    print(f"DEBUG [CampaignNode] Invoking SubGraph with Task: {task.query_level}")

    # 2. Invoke SubGraph with Initial State
    sub_state_input = {
        "task": task,
        "retry_count": 0,
        "step_count": 0, # Initialize step count
        "messages": [],
        "internal_thoughts": []
    }
    
    result_state = campaign_subgraph.invoke(sub_state_input)
    
    # 3. Adapt Output
    campaign_data = result_state.get("campaign_data")
    sql_error = result_state.get("sql_error")
    final_response_text = result_state.get("final_response")
    step_count = result_state.get("step_count", 0)
    
    print(f"DEBUG [CampaignNode] SubGraph finished in {step_count} steps.")
    
    # Construct a response message for the Supervisor
    if sql_error:
        response_msg = AIMessage(content=f"查詢失敗 (經過 {step_count} 步嘗試)。錯誤訊息: {sql_error}")
    elif campaign_data and campaign_data.get("data"):
        count = len(campaign_data["data"])
        response_msg = AIMessage(content=f"查詢成功，已找到 {count} 筆資料。請檢查 state['campaign_data']。")
    else:
        # No data case
        # Check if final_response was set by fallback logic or router
        msg_content = final_response_text or "查無資料 (No Data Found)."
        response_msg = AIMessage(content=msg_content)

    response_msg.name = "CampaignAgent"

    return {
        "messages": [response_msg],
        "campaign_data": campaign_data
    }
