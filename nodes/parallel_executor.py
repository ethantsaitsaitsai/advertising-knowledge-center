import concurrent.futures
from langchain_core.messages import AIMessage
from schemas.state import AgentState
from schemas.agent_tasks import CampaignTask
from nodes.campaign_node_wrapper import campaign_node
from nodes.performance_node_wrapper import performance_node

def parallel_executor_node(state: AgentState):
    """
    Simultaneously executes CampaignAgent and PerformanceAgent.
    Waits for both to complete and merges their outputs into the global state.
    """
    print("DEBUG [ParallelExecutor] Starting parallel execution...")
    
    # We reuse the logic inside the wrapper nodes, but we need to ensure they don't depend on 
    # mutating the shared 'state' object in a way that causes race conditions.
    # Fortunately, LangGraph nodes usually return a dict of updates, which is safe.
    # However, wrapper nodes take 'state' as input. We pass the SAME state to both.
    
    # Using ThreadPoolExecutor for I/O bound tasks (LLM calls)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        # Prepare specific states
        campaign_state = state.copy()
        if campaign_state.get("supervisor_payload"):
            campaign_state["supervisor_payload"] = campaign_state["supervisor_payload"].copy()
            campaign_state["supervisor_payload"]["task_type"] = "campaign_query"
            
        performance_state = state.copy()
        if performance_state.get("supervisor_payload"):
            performance_state["supervisor_payload"] = performance_state["supervisor_payload"].copy()
            performance_state["supervisor_payload"]["task_type"] = "performance_query"

        future_campaign = executor.submit(campaign_node, campaign_state)
        future_performance = executor.submit(performance_node, performance_state)
        
        try:
            campaign_result = future_campaign.result()
            print("DEBUG [ParallelExecutor] Campaign Task Completed.")
        except Exception as e:
            print(f"DEBUG [ParallelExecutor] Campaign Task Failed: {e}")
            campaign_result = {"messages": [AIMessage(content=f"Campaign Task Failed: {e}")]}

        try:
            performance_result = future_performance.result()
            print("DEBUG [ParallelExecutor] Performance Task Completed.")
        except Exception as e:
            print(f"DEBUG [ParallelExecutor] Performance Task Failed: {e}")
            performance_result = {"messages": [AIMessage(content=f"Performance Task Failed: {e}")]}

    # --- Merge Results ---
    # We combine the updates from both agents.
    
    merged_update = {}
    
    # 1. Campaign Data
    if "campaign_data" in campaign_result:
        c_data = campaign_result["campaign_data"]
        print(f"DEBUG [ParallelExecutor] Campaign Data Keys: {c_data.keys() if c_data else 'None'}")
        
        merged_update["campaign_data"] = c_data
        # Also sync to sql_result for legacy compatibility if needed
        if c_data:
            merged_update["sql_result"] = c_data.get("data")
            merged_update["sql_result_columns"] = c_data.get("columns")
        else:
            merged_update["sql_result"] = None
            merged_update["sql_result_columns"] = None
        
    # 2. Performance Data
    if "final_dataframe" in performance_result:
        merged_update["final_dataframe"] = performance_result["final_dataframe"]
        merged_update["was_default_metrics"] = performance_result.get("was_default_metrics", False)
        
    # 3. Messages
    # We collect messages from both. 
    # Note: campaign_node returns {"messages": [msg]}. We append them.
    msgs = []
    if "messages" in campaign_result:
        msgs.extend(campaign_result["messages"])
    if "messages" in performance_result:
        msgs.extend(performance_result["messages"])
        
    merged_update["messages"] = msgs
    
    print("DEBUG [ParallelExecutor] Parallel Execution Finished. State Updated.")
    return merged_update
