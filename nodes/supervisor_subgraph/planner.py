from typing import Literal, Dict, Any, Union, Optional, List
from langchain_core.messages import SystemMessage, AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from pydantic import BaseModel, Field
from config.llm import llm
from nodes.supervisor_subgraph.state import SupervisorSubState
from prompts.supervisor_prompt import SUPERVISOR_SYSTEM_PROMPT

# Supervisor Decision Wrapper
class SupervisorDecision(BaseModel):
    next_node: Literal["CampaignAgent", "PerformanceAgent", "ResponseSynthesizer", "ParallelExecutor", "FINISH"] = Field(description="The next agent to act")
    instructions: str = Field(description="Specific instructions for the worker agent. Translate user intent into a clear task.")
    reasoning: str = Field(description="Your thought process (Chain of Thought) justifying this decision.")
    
    # Optional Task Payloads
    campaign_task_params: Optional[Dict[str, Any]] = Field(None, description="Parameters for CampaignTask if next_node is CampaignAgent")
    performance_task_params: Optional[Dict[str, Any]] = Field(None, description="Parameters for PerformanceTask if next_node is PerformanceAgent")

prompt = ChatPromptTemplate.from_messages(
    [
        ("system", SUPERVISOR_SYSTEM_PROMPT),
        MessagesPlaceholder(variable_name="messages"),
        MessagesPlaceholder(variable_name="internal_feedback"), 
        (
            "system",
            "Based on the conversation and user intent, invoke the appropriate tool (Task).",
        ),
    ]
)

def planner_node(state: SupervisorSubState):
    """
    Supervisor Agent (Planner).
    Generates a draft decision based on context and feedback.
    """
    messages = list(state.get("messages", []))
    user_intent = state.get("user_intent")
    campaign_ids = state.get("campaign_ids", [])
    has_campaign_ids = bool(campaign_ids)
    
    # Feedback from Validator Node (if any)
    internal_feedback = state.get("internal_feedback", [])

    # Check existing results (for Fan-In Logic - Fast Pass)
    has_perf_result = state.get("final_dataframe") is not None
    has_campaign_result = (state.get("sql_result") is not None) or (state.get("campaign_data") is not None)
    
    # --- 0. Fan-In Logic (Fast Pass) ---
    if has_campaign_ids and user_intent and user_intent.needs_performance:
        if has_perf_result and has_campaign_result:
             print(f"DEBUG [SupervisorPlanner] Parallel Execution Complete. Scheduling Synthesizer.")
             return {
                 "draft_decision": {
                     "next_node": "ResponseSynthesizer",
                     "instructions": "Data retrieval complete. Synthesize the final report.",
                     "reasoning": "Fast path: Parallel execution done."
                 }
             }

    # --- 1. Prepare Context for LLM (Enhanced Observation) ---
    payload_context = {}
    if user_intent:
        payload_context["query_level"] = user_intent.query_level
        payload_context["entities"] = user_intent.entities
        payload_context["date_range"] = user_intent.date_range
        payload_context["analysis_needs"] = user_intent.analysis_needs
        payload_context["needs_performance"] = user_intent.needs_performance
        payload_context["is_ambiguous"] = user_intent.is_ambiguous
        payload_context["missing_info"] = user_intent.missing_info

        # Enhanced Campaign Data Summary
        campaign_data_state = state.get("campaign_data")
        if campaign_data_state and campaign_data_state.get("data"):
             rows = campaign_data_state["data"]
             count = len(rows)
             # Extract first 3 names for context
             names = [r.get("Campaign_Name") or r.get("campaign_name") or r.get("name") for r in rows[:3]]
             names_str = ", ".join([str(n) for n in names if n])
             payload_context["campaign_data_summary"] = f"Available ({count} rows). Sample Names: {names_str}..."
        elif has_campaign_ids:
             ids = campaign_ids
             payload_context["campaign_data_summary"] = f"IDs Only ({len(ids)}): {ids}."
        else:
             payload_context["campaign_data_summary"] = "No Campaign Data (IDs) yet."

        # Enhanced Last Worker Result
        if messages:
            last_msg = messages[-1]
            if getattr(last_msg, "name", "") in ["CampaignAgent", "PerformanceAgent"]:
                payload_context["last_worker_report"] = f"{last_msg.name} reported: {last_msg.content}"
    
    user_intent_str = f"User Intent Analysis:\n{user_intent.model_dump_json(indent=2)}" if user_intent else "User Intent: Not available."

    # --- 2. Generate Decision (Draft) ---

    # Add current date context to prevent future date misunderstanding
    from datetime import datetime
    current_date = datetime.now().strftime("%Y-%m-%d")
    current_year = datetime.now().year

    chain_input = {
        "messages": messages,
        "internal_feedback": internal_feedback,
        "user_intent_context": user_intent_str,
        "payload_context": str(payload_context),
        "current_date": current_date,
        "current_year": current_year
    }
    
    try:
        supervisor_chain = prompt | llm.with_structured_output(SupervisorDecision)
        decision: SupervisorDecision = supervisor_chain.invoke(chain_input)
    except Exception as e:
        print(f"DEBUG [SupervisorPlanner] LLM Error: {e}")
        return {
            "draft_decision": {
                 "next_node": "FINISH",
                 "instructions": "System error in planning.",
                 "reasoning": f"LLM Exception: {e}"
            }
        }

    # Check if decision is None (LLM failed to return valid structured output)
    if decision is None:
        print(f"⚠️ WARNING [SupervisorPlanner] LLM returned None, using fallback")
        return {
            "draft_decision": {
                 "next_node": "FINISH",
                 "instructions": "LLM failed to return valid decision.",
                 "reasoning": "LLM returned None instead of SupervisorDecision"
            }
        }

    draft = decision.model_dump()
    print(f"DEBUG [SupervisorPlanner] Draft: {decision.next_node} | Reasoning: {decision.reasoning}")

    return {
        "draft_decision": draft
    }