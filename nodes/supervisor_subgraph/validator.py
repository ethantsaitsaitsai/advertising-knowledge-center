from typing import Optional, Dict, Any, List
from langchain_core.messages import HumanMessage
from nodes.supervisor_subgraph.state import SupervisorSubState

def validate_decision(draft: Dict[str, Any], state: SupervisorSubState) -> Optional[str]:
    """
    Guardrails to critique the Supervisor's plan.
    Returns an error message string if invalid, None if valid.
    """
    next_node = draft.get("next_node")
    ids = state.get("campaign_ids", [])
    user_intent = state.get("user_intent")
    
    print(f"DEBUG [SupervisorValidator] Validating plan: Go to '{next_node}'")

    if next_node == "PerformanceAgent" and not ids:
        return (
            "CRITICAL ERROR: You chose 'PerformanceAgent' but we do not have any 'campaign_ids' yet. "
            "PerformanceAgent cannot work without IDs. "
            "You MUST choose 'CampaignAgent' first to find the IDs (using search or query)."
        )
    
    if next_node == "ParallelExecutor" and not ids:
        return (
            "CRITICAL ERROR: You chose 'ParallelExecutor' but we do not have 'campaign_ids'. "
            "You cannot run performance queries in parallel without IDs. "
            "Please route to 'CampaignAgent' first."
        )

    if user_intent and user_intent.is_ambiguous:
        if next_node in ["PerformanceAgent", "ParallelExecutor", "ResponseSynthesizer"]:
             return (
                 "CRITICAL ERROR: The UserIntent is marked as 'is_ambiguous'. "
                 "We do not know which entity to query yet. "
                 "You MUST route to 'CampaignAgent' (to resolve ambiguity) or 'FINISH' (to ask the user)."
             )

    return None

def validator_node(state: SupervisorSubState):
    """
    Critique Node (Validator).
    Checks the Supervisor's draft decision against Python guardrails.
    """
    draft = state.get("draft_decision")
    
    if not draft:
        return {"sub_next": "FINISH"} # Should not happen

    # Run Validation
    error_msg = validate_decision(draft, state)
    
    if error_msg:
        print(f"DEBUG [SupervisorValidator] Validation Failed: {error_msg}")
        # Reject: Retry Loop
        feedback_msg = HumanMessage(content=f"PLAN REJECTED. Reason: {error_msg}")
        return {
            "internal_feedback": [feedback_msg],
            "sub_next": "retry" # Internal routing flag
        }
    
    # Accept: Prepare Global State updates and Exit
    print("DEBUG [SupervisorValidator] Plan Accepted.")
    
    next_node = draft.get("next_node")
    instructions = draft.get("instructions")
    
    decision_payload = {}
    
    if next_node == "CampaignAgent":
        decision_payload = draft.get("campaign_task_params") or {}
        decision_payload["task_type"] = "campaign_query" 
    elif next_node == "PerformanceAgent":
        decision_payload = draft.get("performance_task_params") or {}
        decision_payload["task_type"] = "performance_query" 
    elif next_node == "ParallelExecutor":
        decision_payload = {"task_type": "parallel_query"}
    
    decision_payload["instruction_text"] = instructions
    
    # --- ID & Filter Injection ---
    campaign_ids = state.get("campaign_ids", [])
    user_intent = state.get("user_intent")
    
    if next_node in ["CampaignAgent", "PerformanceAgent", "ParallelExecutor"]:
        if campaign_ids:
            if "campaign_ids" not in decision_payload or not decision_payload["campaign_ids"]:
                decision_payload["campaign_ids"] = campaign_ids
        
        if "filters" not in decision_payload:
            decision_payload["filters"] = {}
            
        if user_intent and user_intent.entities:
            if "brands" not in decision_payload["filters"]:
                decision_payload["filters"]["brands"] = user_intent.entities
                
        if user_intent and user_intent.date_range:
            if "date_range" not in decision_payload["filters"]:
                if hasattr(user_intent.date_range, "model_dump"):
                    decision_payload["filters"]["date_range"] = user_intent.date_range.model_dump()
                else:
                    decision_payload["filters"]["date_range"] = user_intent.date_range

        if user_intent:
            decision_payload["query_level"] = user_intent.query_level

        # 【CRITICAL】Pass is_ambiguous flag from user_intent to task
        # CampaignAgent Router needs to know if this is a clarification step
        if user_intent:
            decision_payload["is_ambiguous"] = user_intent.is_ambiguous

    return {
        "next": next_node, # Update Global 'next'
        "supervisor_payload": decision_payload, # Update Global payload
        "supervisor_instructions": instructions, # Update Global instructions
        "sub_next": "finish" # Internal routing flag
    }
