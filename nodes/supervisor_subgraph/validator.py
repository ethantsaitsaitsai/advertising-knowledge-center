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
    campaign_data = state.get("campaign_data")
    user_intent = state.get("user_intent")
    messages = state.get("messages", [])

    print(f"DEBUG [SupervisorValidator] Validating plan: Go to '{next_node}'")
    print(f"DEBUG [SupervisorValidator] is_ambiguous={user_intent.is_ambiguous if user_intent else None}, "
          f"entities={user_intent.entities if user_intent else None}, "
          f"date_range={user_intent.date_range if user_intent else None}")

    # Check if we have campaign data (either campaign_ids or campaign_data)
    has_campaign_data = (
        bool(ids) or
        (campaign_data and campaign_data.get("data") and len(campaign_data["data"]) > 0)
    )

    print(f"DEBUG [SupervisorValidator] has_campaign_data={has_campaign_data}, "
          f"campaign_ids={len(ids) if ids else 0}, "
          f"campaign_data={'Available (' + str(len(campaign_data['data'])) + ' rows)' if campaign_data and campaign_data.get('data') else 'None'}")

    # RULE 0a: FINISH Decision Validation
    # If routing to FINISH, ensure it's a valid termination point
    if next_node == "FINISH":
        error_msg = draft.get("error_message")

        # Allow FINISH if there's an error_message (system error or clarification request)
        if error_msg:
            print(f"DEBUG [SupervisorValidator] FINISH with error_message allowed: {error_msg[:100]}...")
            return None

        # Allow FINISH for chitchat
        if user_intent and user_intent.query_level == "chitchat":
            print(f"DEBUG [SupervisorValidator] FINISH for chitchat allowed.")
            return None

        # Block FINISH if this is a data query without any results
        if user_intent and user_intent.query_level in ["contract", "strategy", "execution", "audience"]:
            # Check if we have any data to show
            has_any_data = (
                has_campaign_data or
                state.get("final_dataframe") is not None or
                state.get("sql_result") is not None
            )

            if not has_any_data:
                return (
                    "CRITICAL ERROR: Cannot FINISH without retrieving any data. "
                    f"User asked for '{user_intent.query_level}' level query but we have no results yet. "
                    "You MUST route to 'CampaignAgent' to retrieve data first."
                )

    # RULE 0: Loop Detection - Prevent consecutive calls to the same agent
    if messages and len(messages) > 0:
        # Check last message from worker agent
        last_worker_msg = None
        for msg in reversed(messages):
            if hasattr(msg, "name") and msg.name in ["CampaignAgent", "PerformanceAgent"]:
                last_worker_msg = msg
                break

        if last_worker_msg and last_worker_msg.name == next_node:
            print(f"⚠️ WARNING [SupervisorValidator] Loop detected: Last worker was '{last_worker_msg.name}', trying to go to '{next_node}' again")
            # Only block if it's a true infinite loop scenario
            # (i.e., going to CampaignAgent when we should go to PerformanceAgent)
            if next_node == "CampaignAgent" and has_campaign_data and user_intent and user_intent.needs_performance:
                return (
                    f"LOOP DETECTED: You are trying to send task to '{next_node}' again, "
                    f"but the last worker was already '{last_worker_msg.name}'. "
                    "This creates an infinite loop. "
                    "Since we have campaign_data and needs_performance=True, "
                    "you MUST go to 'PerformanceAgent' instead."
                )

    # RULE 1: Cannot go to PerformanceAgent without campaign data
    if next_node == "PerformanceAgent" and not has_campaign_data:
        return (
            "CRITICAL ERROR: You chose 'PerformanceAgent' but we do not have any campaign data yet. "
            "PerformanceAgent cannot work without campaign IDs or data. "
            "You MUST choose 'CampaignAgent' first to find the campaigns (using search or query)."
        )

    # RULE 2: MUST go to PerformanceAgent if we have campaign_data and needs_performance=True
    # This prevents infinite loops where Supervisor repeatedly sends tasks to CampaignAgent
    if (next_node == "CampaignAgent" and has_campaign_data and
        user_intent and user_intent.needs_performance):
        # Check if we already have performance data
        has_perf_result = state.get("final_dataframe") is not None
        if not has_perf_result:
            return (
                "CRITICAL ERROR: You chose 'CampaignAgent' but we ALREADY have campaign data "
                f"({len(campaign_data['data']) if campaign_data and campaign_data.get('data') else len(ids)} rows/IDs) "
                "and user needs performance metrics (needs_performance=True). "
                "You MUST NOT repeat CampaignAgent query. "
                "You MUST choose 'PerformanceAgent' to query ClickHouse for performance metrics (CTR, VTR, ER)."
            )

    # CRITICAL RULE: If user has provided specific entities AND date_range,
    # we should query even if is_ambiguous=True (ambiguity is resolved by user clarification)
    has_entities = user_intent and user_intent.entities and len(user_intent.entities) > 0
    has_date_range = user_intent and user_intent.date_range

    # If user provided both entity and date, treat as resolved (not ambiguous)
    if has_entities and has_date_range and user_intent.is_ambiguous:
        print(f"DEBUG [SupervisorValidator] OVERRIDE: User provided entities + date_range. Treating as resolved ambiguity.")
        # Allow CampaignAgent to query (don't force clarification)
        # is_ambiguous will still be passed but Router will execute if it gets a query instruction

    if user_intent and user_intent.is_ambiguous:
        # Only prevent PerformanceAgent/Synthesizer if ambiguous (need CampaignAgent to resolve first)
        if next_node in ["PerformanceAgent", "ResponseSynthesizer"]:
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
    
    decision_payload["instruction_text"] = instructions
    
    # --- ID & Filter Injection ---
    campaign_ids = state.get("campaign_ids", [])
    user_intent = state.get("user_intent")
    
    if next_node in ["CampaignAgent", "PerformanceAgent"]:
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

        # ============================================================
        # CRITICAL FIX: Pass analysis_needs from user_intent to task
        # ============================================================
        # CampaignGenerator and PerformanceGenerator need dimensions/metrics to generate correct SQL
        # Without this, CampaignAgent only queries basic cmpid, missing Budget_Sum, Segment_Category, etc.
        if user_intent and user_intent.analysis_needs:
            # Get analysis_needs as dict
            if hasattr(user_intent.analysis_needs, "model_dump"):
                full_analysis_needs = user_intent.analysis_needs.model_dump()
            elif hasattr(user_intent.analysis_needs, "dict"):
                full_analysis_needs = user_intent.analysis_needs.dict()
            elif isinstance(user_intent.analysis_needs, dict):
                full_analysis_needs = user_intent.analysis_needs
            else:
                # Fallback: try to convert to dict
                full_analysis_needs = dict(user_intent.analysis_needs)

            # ============================================================
            # FIELD RESPONSIBILITY SEPARATION
            # ============================================================
            # Based on metrics.yaml and column_mappings.yaml
            # MySQL-only fields (CampaignAgent): Agency, Advertiser, Brand, Ad_Format,
            #   Segment_Category, Industry, Pricing_Unit, Budget_Sum
            # ClickHouse-only fields (PerformanceAgent): Impression, Click, CTR, VTR, ER,
            #   View3s, Q100, Date_Month, Date_Year
            # Shared fields: Campaign_Name (both databases have it)

            if next_node == "PerformanceAgent":
                # Filter to ClickHouse-only fields
                # [MODIFIED] Added 'Ad_Format' and 'Format' to allow granular performance query
                clickhouse_dimensions = {
                    "Date_Month", "Date_Year", "Campaign_Name",
                    "Ad_Format", "Format", "投遞格式"
                }
                clickhouse_metrics = {"Impression", "Click", "CTR", "VTR", "ER", "View3s", "Q100"}

                filtered_analysis_needs = {}
                if "dimensions" in full_analysis_needs:
                    filtered_dims = [d for d in full_analysis_needs["dimensions"]
                                   if d in clickhouse_dimensions]
                    if filtered_dims:
                        filtered_analysis_needs["dimensions"] = filtered_dims

                if "metrics" in full_analysis_needs:
                    filtered_metrics = [m for m in full_analysis_needs["metrics"]
                                      if m in clickhouse_metrics]
                    if filtered_metrics:
                        filtered_analysis_needs["metrics"] = filtered_metrics

                decision_payload["analysis_needs"] = filtered_analysis_needs
                print(f"DEBUG [SupervisorValidator] Filtered analysis_needs for PerformanceAgent: {filtered_analysis_needs}")

            elif next_node == "CampaignAgent":
                # CampaignAgent gets all MySQL fields (no filtering needed for now)
                # But we could filter out ClickHouse-only time dimensions if needed
                decision_payload["analysis_needs"] = full_analysis_needs

            else:
                # For other routing targets, pass full analysis_needs
                decision_payload["analysis_needs"] = full_analysis_needs

    return {
        "next": next_node, # Update Global 'next'
        "supervisor_payload": decision_payload, # Update Global payload
        "supervisor_instructions": instructions, # Update Global instructions
        "sub_next": "finish" # Internal routing flag
    }
