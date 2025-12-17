from typing import Literal, Dict, Any, Union, Optional, List
from langchain_core.messages import SystemMessage, AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from pydantic import BaseModel, Field
from config.llm import llm
from nodes.supervisor_subgraph.state import SupervisorSubState
from prompts.supervisor_prompt import SUPERVISOR_SYSTEM_PROMPT

# Supervisor Decision Wrapper
class SupervisorDecision(BaseModel):
    next_node: Literal["CampaignAgent", "PerformanceAgent", "ResponseSynthesizer", "FINISH"] = Field(description="The next agent to act")
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
    # --- FIX: Ensure messages are proper types (ChatGoogleGenerativeAI strictness) ---
    def fix_messages(msgs):
        fixed = []
        for m in msgs:
            if type(m).__name__ == 'BaseMessage': 
                # print(f"DEBUG [SupervisorPlanner] Converting BaseMessage(type={m.type}) to concrete class.")
                if m.type == 'human':
                    fixed.append(HumanMessage(content=m.content))
                elif m.type == 'ai':
                    fixed.append(AIMessage(content=m.content))
                elif m.type == 'system':
                    fixed.append(SystemMessage(content=m.content))
                else:
                    fixed.append(HumanMessage(content=m.content))
            else:
                fixed.append(m)
        return fixed

    messages = fix_messages(list(state.get("messages", [])))
    internal_feedback = fix_messages(list(state.get("internal_feedback", [])))
    # -----------------------------------------------------------------------------

    user_intent = state.get("user_intent")
    campaign_ids = state.get("campaign_ids", [])
    has_campaign_ids = bool(campaign_ids)
    
    # Check existing results (for Fan-In Logic - Fast Pass)
    has_perf_result = state.get("final_dataframe") is not None
    has_campaign_result = (state.get("sql_result") is not None) or (state.get("campaign_data") is not None)
    
    # --- 0. Fan-In Logic (Fast Pass) ---
    if has_campaign_ids and user_intent and user_intent.needs_performance:
        if has_perf_result and has_campaign_result:
             print(f"DEBUG [SupervisorPlanner] Sequential Execution Complete (Campaign + Performance). Scheduling Synthesizer.")
             return {
                 "draft_decision": {
                     "next_node": "ResponseSynthesizer",
                     "instructions": "Data retrieval complete. Synthesize the final report.",
                     "reasoning": "Fast path: Both MySQL and ClickHouse data retrieved."
                 }
             }

        # CRITICAL RULE: If we have campaign_data but no performance data yet, FORCE PerformanceAgent
        # This prevents infinite loops where Supervisor keeps sending tasks to CampaignAgent
        if has_campaign_result and not has_perf_result:
            print(f"DEBUG [SupervisorPlanner] HARD RULE: has_campaign_data=True + needs_performance=True + no_perf_data → FORCE PerformanceAgent")
            return {
                "draft_decision": {
                    "next_node": "PerformanceAgent",
                    "instructions": f"Query performance metrics (CTR, VTR, ER) for Campaign IDs: {campaign_ids}.",
                    "reasoning": "Hard rule: Campaign data exists and user needs performance metrics. Must query ClickHouse next."
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
        print(f"⚠️ WARNING [SupervisorPlanner] LLM Error: {e}")
        print(f"DEBUG [SupervisorPlanner] Using Python fallback rules...")

        # Fallback: Use Python rules to determine next step
        has_campaign_result = (state.get("sql_result") is not None) or (state.get("campaign_data") is not None)
        has_perf_result = state.get("final_dataframe") is not None

        # Rule 1: If no campaign data, must go to CampaignAgent first
        if not has_campaign_ids and not has_campaign_result:
            print(f"DEBUG [SupervisorPlanner] Fallback Rule 1: No campaign data → CampaignAgent")
            return {
                "draft_decision": {
                    "next_node": "CampaignAgent",
                    "instructions": f"Query campaigns for entity: {user_intent.entities if user_intent else 'unknown'}",
                    "reasoning": "Fallback rule: No campaign data, must query CampaignAgent first."
                }
            }

        # Rule 2: If have campaign data but need performance data
        if has_campaign_ids and user_intent and user_intent.needs_performance and not has_perf_result:
            print(f"DEBUG [SupervisorPlanner] Fallback Rule 2: Have campaign_ids + needs_performance → PerformanceAgent")
            return {
                "draft_decision": {
                    "next_node": "PerformanceAgent",
                    "instructions": f"Query performance metrics for Campaign IDs: {campaign_ids}",
                    "reasoning": "Fallback rule: Have campaign data + needs_performance=True, must query PerformanceAgent."
                }
            }

        # Rule 3: If have both results, go to Synthesizer
        if has_campaign_result and (not user_intent or not user_intent.needs_performance or has_perf_result):
            print(f"DEBUG [SupervisorPlanner] Fallback Rule 3: All data available → ResponseSynthesizer")
            return {
                "draft_decision": {
                    "next_node": "ResponseSynthesizer",
                    "instructions": "Synthesize the final report from available data.",
                    "reasoning": "Fallback rule: All required data available, go to Synthesizer."
                }
            }

        # Default: Return error to user
        print(f"DEBUG [SupervisorPlanner] Fallback: No rule matched, returning error")
        return {
            "draft_decision": {
                 "next_node": "FINISH",
                 "instructions": "System error: Unable to determine next step.",
                 "reasoning": f"LLM Exception: {e}. Fallback rules did not match any scenario.",
                 "error_message": f"抱歉，系統遇到暫時性錯誤 (Gemini API 500)。請稍後再試或簡化您的查詢。"
            }
        }

    # Check if decision is None (LLM failed to return valid structured output)
    if decision is None:
        print(f"⚠️ WARNING [SupervisorPlanner] LLM returned None, using fallback")

        # Use same fallback logic as exception handler
        has_campaign_result = (state.get("sql_result") is not None) or (state.get("campaign_data") is not None)
        has_perf_result = state.get("final_dataframe") is not None

        if not has_campaign_ids and not has_campaign_result:
            return {
                "draft_decision": {
                    "next_node": "CampaignAgent",
                    "instructions": f"Query campaigns for entity: {user_intent.entities if user_intent else 'unknown'}",
                    "reasoning": "Fallback rule (None result): No campaign data, must query CampaignAgent first."
                }
            }

        if has_campaign_ids and user_intent and user_intent.needs_performance and not has_perf_result:
            return {
                "draft_decision": {
                    "next_node": "PerformanceAgent",
                    "instructions": f"Query performance metrics for Campaign IDs: {campaign_ids}",
                    "reasoning": "Fallback rule (None result): Have campaign data + needs_performance=True, must query PerformanceAgent."
                }
            }

        return {
            "draft_decision": {
                 "next_node": "FINISH",
                 "instructions": "LLM failed to return valid decision.",
                 "reasoning": "LLM returned None instead of SupervisorDecision",
                 "error_message": "抱歉，系統無法理解您的查詢。請提供更清晰的描述。"
            }
        }

    draft = decision.model_dump()
    print(f"DEBUG [SupervisorPlanner] Draft: {decision.next_node} | Reasoning: {decision.reasoning}")

    return {
        "draft_decision": draft
    }