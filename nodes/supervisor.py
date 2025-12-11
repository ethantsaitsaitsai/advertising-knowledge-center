from typing import Literal, Dict, Any, Union, Optional
from langchain_core.messages import SystemMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from pydantic import BaseModel, Field, model_validator
from config.llm import llm
from schemas.state import AgentState
from schemas.agent_tasks import CampaignTask, PerformanceTask, FinishTask, SynthesizeTask
from prompts.supervisor_prompt import SUPERVISOR_SYSTEM_PROMPT

# Supervisor Decision Wrapper
class SupervisorDecision(BaseModel):
    campaign_task: Optional[CampaignTask] = Field(None)
    performance_task: Optional[PerformanceTask] = Field(None)
    synthesize_task: Optional[SynthesizeTask] = Field(None)
    finish_task: Optional[FinishTask] = Field(None)

    # Removed check_only_one_task to allow parallel tasks

prompt = ChatPromptTemplate.from_messages(
    [
        ("system", SUPERVISOR_SYSTEM_PROMPT),
        MessagesPlaceholder(variable_name="messages"),
        (
            "system",
            "Based on the conversation and user intent, invoke the appropriate tool (Task).",
        ),
    ]
)

def supervisor_node(state: AgentState):
    messages = list(state.get("messages", []))
    user_intent = state.get("user_intent")
    
    # Check for IDs from Resolver
    # Resolver now puts them in 'campaign_ids' directly
    campaign_ids = state.get("campaign_ids", [])
    has_campaign_ids = bool(campaign_ids)
    
    # Check existing results
    has_perf_result = state.get("final_dataframe") is not None
    # Fix: CampaignAgent output is stored in 'campaign_data', not just 'sql_result'
    has_campaign_result = (state.get("sql_result") is not None) or (state.get("campaign_data") is not None)
    
    # --- 0. Fan-In Logic (Check if Parallel Tasks are Done) ---
    if has_campaign_ids and user_intent and user_intent.needs_performance:
        # If we have BOTH results, we are ready to synthesize
        if has_perf_result and has_campaign_result:
             print(f"DEBUG [Supervisor] Parallel Execution Complete (Both Data Sources). Scheduling Synthesizer.")
             return {
                 "next": "ResponseSynthesizer",
                 "supervisor_payload": {
                     "task_type": "synthesize",
                     "instruction_text": "Both data sources are ready. Please synthesize the report."
                 }
             }
        # What if one failed? Or we only needed one?
        # If we have perf result but no campaign result... maybe CampaignAgent failed?
        # For now, if we have Perf result, we usually want to show it.
        if has_perf_result and not has_campaign_result:
             # Check if we just tried to run them. 
             # If last sender was CampaignAgent (and it returned empty), we might be here.
             pass

    def get_msg_type(msg):
        if isinstance(msg, dict): return msg.get("type", "")
        return getattr(msg, "type", "")

    # --- 1. Result Review (Legacy / Single Path) ---
    if messages:
        last_msg = messages[-1]
        if isinstance(last_msg, dict):
            content = last_msg.get("content", "")
            msg_type = last_msg.get("type", "")
        else:
            content = getattr(last_msg, "content", "")
            msg_type = getattr(last_msg, "type", "")
        
        clarification_keywords = ["請問您是想查詢哪一個", "找到了幾個相關項目", "請提供", "請確認", "請問您是指", "請告訴我", "請選擇", "missing information"]
        if msg_type == 'ai' and any(keyword in content for keyword in clarification_keywords):
             print(f"DEBUG [Supervisor] Detected Clarification Question. Forcing FINISH.")
             return {
                 "next": "FINISH",
                 "supervisor_payload": {
                     "task_type": "finish",
                     "reason": "Clarification needed",
                     "final_instruction": "Wait for user clarification."
                 }
             }
             
        # Review Insight Injection ... (Simplified for Parallel Flow)
        # In Parallel flow, we rely less on "Review" and more on State Checks.

    # --- 2. Ambiguity Check ---
    if user_intent and user_intent.is_ambiguous:
        print(f"DEBUG [Supervisor] Ambiguity Detected (is_ambiguous=True).")
        # IntentAnalyzer should have already generated a question with options in the last message.
        # We just need to stop and let the user answer.
        
        return {
            "next": "FINISH",
            # We don't generate a new message here, assuming IntentAnalyzer added one.
            # If not, we might need a fallback, but let's trust the new prompt.
            "supervisor_payload": {
                "task_type": "finish", 
                "reason": "Ambiguity - Waiting for user selection",
                "final_instruction": "User needs to select an option."
            }
        }

    # --- 3. Missing Info Check ---
    if user_intent and user_intent.missing_info:
        missing = ", ".join(user_intent.missing_info)
        question = f"為了提供精確的數據，請問您想查詢哪個時間範圍的資料？(缺少: {missing})"
        
        # Check if we already asked this
        last_content = getattr(messages[-1], "content", "") if messages else ""
        if question not in last_content:
             print(f"DEBUG [Supervisor] Missing Info Detected: {missing}. Asking User Directly.")
             response_msg = AIMessage(content=question)
             return {
                 "next": "FINISH",
                 "messages": [response_msg],
                 "supervisor_payload": {
                     "task_type": "finish",
                     "reason": "Missing Info",
                     "final_instruction": question 
                 }
             }

    # --- 4. Parallel Launch (The New Logic) ---
    # Condition: Valid Intent, Has IDs, Needs Performance, No Results Yet
    if user_intent and not user_intent.missing_info and not user_intent.is_ambiguous:
        if has_campaign_ids and user_intent.needs_performance:
            if not has_perf_result and not has_campaign_result:
                print(f"DEBUG [Supervisor] Launching PARALLEL Tasks: CampaignAgent + PerformanceAgent")
                
                # Construct Payloads
                filters = {}
                if user_intent.entities: filters["brands"] = user_intent.entities
                if user_intent.date_range:
                    if hasattr(user_intent.date_range, "model_dump"):
                        filters["date_range"] = user_intent.date_range.model_dump()
                    else:
                        filters["date_range"] = user_intent.date_range

                # Return Next Node -> ParallelExecutor
                return {
                    "next": "ParallelExecutor",
                    "supervisor_payload": {
                        # We can pass specific payloads if the agents support reading from a specific key
                        # Or we just pass a merged payload. 
                        # Agents read from 'supervisor_payload' key.
                        # Since they read the SAME key, we must ensure the payload is compatible with both.
                        "task_type": "parallel_query", # Generic type
                        "campaign_ids": campaign_ids,
                        "query_level": user_intent.query_level,
                        "filters": filters,
                        "analysis_needs": user_intent.analysis_needs,
                        "instruction_text": "Parallel Execution: Query Metadata and Metrics."
                    }
                }

    # --- 5. Prepare Context for LLM (Fallback) ---
    # Construct Explicit Input for the Chain to avoid State filtering issues
    
    payload_context = {}
    if user_intent:
        payload_context["query_level"] = user_intent.query_level
        payload_context["entities"] = user_intent.entities
        payload_context["date_range"] = user_intent.date_range
        payload_context["analysis_needs"] = user_intent.analysis_needs
        payload_context["needs_performance"] = user_intent.needs_performance
        payload_context["is_ambiguous"] = user_intent.is_ambiguous
        payload_context["missing_info"] = user_intent.missing_info

        if has_campaign_ids:
             ids = [row.get("cmpid") for row in campaign_data["data"] if row.get("cmpid")]
             payload_context["available_campaign_ids"] = ids[:50]
             payload_context["campaign_data_summary"] = f"Campaign Data available ({len(ids)} IDs)."
        else:
             payload_context["campaign_data_summary"] = "No Campaign Data (IDs) yet."
    
    user_intent_str = f"User Intent Analysis:\n{user_intent.model_dump_json(indent=2)}" if user_intent else "User Intent: Not available."
    
    chain_input = {
        "messages": messages,
        "user_intent_context": user_intent_str,
        "payload_context": str(payload_context) # Convert to string to be safe
    }
    
    try:
        supervisor_chain = prompt | llm.with_structured_output(SupervisorDecision)
        result = supervisor_chain.invoke(chain_input)
    except Exception as e:
        print(f"DEBUG [Supervisor] LLM Error: {e}")
        return {"next": "FINISH", "supervisor_payload": {"reason": "Error"}}
    
    next_node = "FINISH"
    decision_payload = {}
    
    if result.campaign_task:
        next_node = "CampaignAgent"
        decision_payload = result.campaign_task.model_dump()
    elif result.performance_task:
        next_node = "PerformanceAgent"
        decision_payload = result.performance_task.model_dump()
    elif result.synthesize_task:
        next_node = "ResponseSynthesizer"
        decision_payload = result.synthesize_task.model_dump()
    elif result.finish_task:
        next_node = "FINISH"
        decision_payload = result.finish_task.model_dump()
        
    # --- ID Injection & Filter Injection (Safety Net) ---
    # Even if LLM forgets, we MUST inject IDs and Filters if we have them.
    if next_node in ["CampaignAgent", "PerformanceAgent", "ParallelExecutor"]:
        # 1. ID Injection
        if has_campaign_ids:
            if "campaign_ids" not in decision_payload or not decision_payload["campaign_ids"]:
                print(f"DEBUG [Supervisor] Injecting {len(campaign_ids)} Campaign IDs into payload.")
                decision_payload["campaign_ids"] = campaign_ids
        
        # Inject Ad Format IDs
        ad_format_ids = state.get("ad_format_ids", [])
        if ad_format_ids:
            if "ad_format_ids" not in decision_payload:
                decision_payload["ad_format_ids"] = ad_format_ids
        
        # 2. Filter Injection (Entities & Date)
        if "filters" not in decision_payload:
            decision_payload["filters"] = {}
            
        # Inject Ad Format IDs into filters as well for consistency
        if ad_format_ids and "ad_format_ids" not in decision_payload["filters"]:
            decision_payload["filters"]["ad_format_ids"] = ad_format_ids
            
        # Inject Entities
        if user_intent and user_intent.entities:
            # We assume entities are 'brands' or 'campaign_names' mostly.
            # But let's put them in 'brands' as a catch-all for the SQL Generator prompt logic
            if "brands" not in decision_payload["filters"]:
                decision_payload["filters"]["brands"] = user_intent.entities
                
        # Inject Date Range
        if user_intent and user_intent.date_range:
            if "date_range" not in decision_payload["filters"]:
                # user_intent.date_range is now a Pydantic model
                if hasattr(user_intent.date_range, "model_dump"):
                    decision_payload["filters"]["date_range"] = user_intent.date_range.model_dump()
                else:
                    decision_payload["filters"]["date_range"] = user_intent.date_range

    print(f"DEBUG [Supervisor] Decision: {next_node} | Payload: {decision_payload}")
    
    return {
        "next": next_node,
        "supervisor_payload": decision_payload
    }