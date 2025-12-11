from typing import Literal, Union
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from config.llm import llm
from nodes.campaign_subgraph.state import CampaignSubState
from schemas.agent_tasks import CampaignTask

# Decision Options
class CampaignDecision(BaseModel):
    """Decide the next step for the Campaign Agent."""
    next_action: Literal["search_entity", "inspect_schema", "generate_sql", "finish", "finish_no_data"] = Field(
        ..., description="The next action."
    )
    thought_process: str = Field(
        ..., description="Reasoning."
    )

ROUTER_SYSTEM_PROMPT = """你是一個 MySQL 查詢專家的「大腦」。
**決策邏輯**:
1. **search_entity**: 覺得實體名稱模糊。
2. **inspect_schema**: 覺得 Prompt 提供的 Schema 不夠用，且 Memory 中還沒有 Schema 資訊。
3. **generate_sql**: 準備好寫 SQL 了。
4. **finish**: 任務完成。
5. **finish_no_data**: 放棄。
"""

ROUTER_USER_MESSAGE = """
**目前任務**:
{task_context}

**記憶 (Memory)**:
{internal_memory}

**執行結果**:
{sql_result_context}

**步數**: {step_count} / {max_steps}

請決策。注意：如果記憶中已經有 Schema Inspection Result，請不要再次 inspect_schema，請嘗試生成 SQL。
"""

prompt = ChatPromptTemplate.from_messages([
    ("system", ROUTER_SYSTEM_PROMPT),
    ("user", ROUTER_USER_MESSAGE)
])

chain = prompt | llm.with_structured_output(CampaignDecision)

def router_node(state: CampaignSubState):
    """
    The Brain of the Campaign Agent.
    Uses strict Python logic priorities to avoid LLM loops.
    """
    MAX_STEPS = 8
    current_step = state.get("step_count", 0) + 1
    
    # Extract State
    task = state["task"]
    memory = state.get("internal_thoughts", [])
    campaign_data = state.get("campaign_data")
    sql_error = state.get("sql_error")
    
    # Helpers
    has_search_results = any("Search Result" in m for m in memory)
    has_schema_info = any("Schema Inspection Result" in m for m in memory)
    
    has_data = False
    if campaign_data and campaign_data.get("data") and len(campaign_data["data"]) > 0:
        has_data = True
        
    executed_but_empty = False
    if campaign_data and not sql_error and not has_data:
        if campaign_data.get("generated_sqls"):
            executed_but_empty = True

    print(f"DEBUG [CampaignRouter] Step {current_step} Check: Data={has_data}, Empty={executed_but_empty}, Search={has_search_results}, Schema={has_schema_info}")

    # --- Deterministic Logic (The "Fast Path") ---

    # 1. Success -> Finish
    if has_data:
        print("DEBUG [CampaignRouter] Logic: Data found -> FINISH")
        return {
            "next_action": "finish",
            "internal_thoughts": ["Brain (Rule): Data found. Job done."],
            "step_count": current_step
        }

    # 2. Post-Search -> Finish (Clarify)
    if has_search_results:
        print("DEBUG [CampaignRouter] Logic: Search results present -> FINISH (Clarify)")
        last_search = next((m for m in reversed(memory) if "Search Result" in m), "Search results available.")
        return {
            "next_action": "finish",
            "final_response": f"我無法精確找到該實體，但搜尋到了以下結果，請問您是指哪一個？\n(參考: {last_search[:200]}...)",
            "internal_thoughts": ["Brain (Rule): Candidates found. Asking user."],
            "step_count": current_step
        }

    # 3. SQL Error (Column/Table) -> Inspect Schema
    # Only if we haven't inspected yet!
    if sql_error:
        error_lower = sql_error.lower()
        if ("unknown column" in error_lower or "doesn't exist" in error_lower) and not has_schema_info:
             print("DEBUG [CampaignRouter] Logic: SQL Schema Error -> INSPECT_SCHEMA")
             return {
                 "next_action": "inspect_schema",
                 "internal_thoughts": ["Brain (Rule): Schema error detected. Checking schema."],
                 "step_count": current_step
             }

    # 4. Zero Rows + No Search -> Search
    if executed_but_empty and not has_search_results:
        print("DEBUG [CampaignRouter] Logic: 0 Rows & No Search -> SEARCH_ENTITY")
        return {
            "next_action": "search_entity",
            "internal_thoughts": ["Brain (Rule): SQL returned 0 rows. Searching entity."],
            "step_count": current_step
        }
        
    # 5. Safety Brake
    if current_step > MAX_STEPS:
        print("DEBUG [CampaignRouter] Logic: Max steps -> FINISH_NO_DATA")
        return {
            "next_action": "finish_no_data",
            "internal_thoughts": ["Brain: Max steps reached."],
            "step_count": current_step
        }

    # 6. First Step Optimization (Trust the Prompt)
    # If it's the first step, and we have no errors or ambiguity, just TRY to generate SQL.
    # We trust the System Prompt has enough schema info.
    if current_step == 1 and not has_search_results and not sql_error:
        print("DEBUG [CampaignRouter] Logic: First Step -> GENERATE_SQL (Trust Prompt)")
        return {
            "next_action": "generate_sql",
            "internal_thoughts": ["Brain (Rule): First step, skipping schema check. Attempting SQL."],
            "step_count": current_step
        }

    # --- LLM Decision (The "Slow Path") ---
    
    memory_str = "\n".join([f"- {m}" for m in memory]) if memory else "None"
    task_str = task.model_dump_json(indent=2)
    sql_result_context = f"Error: {sql_error}" if sql_error else "None"

    try:
        result = chain.invoke({
            "task_context": task_str, 
            "internal_memory": memory_str,
            "sql_result_context": sql_result_context,
            "step_count": current_step,
            "max_steps": MAX_STEPS
        })
        decision = result.next_action
        thought = result.thought_process
        
        # Anti-Loop: If LLM chooses inspect_schema BUT we already have schema info, force generate_sql
        if decision == "inspect_schema" and has_schema_info:
            print("DEBUG [CampaignRouter] Override: LLM wanted schema again, but we have it. Forcing generate_sql.")
            decision = "generate_sql"
            thought += " (Override: Schema already present)"
            
    except Exception as e:
        print(f"DEBUG [CampaignRouter] LLM Error: {e}. Fallback to generate_sql.")
        decision = "generate_sql" 
        thought = "LLM Error Fallback"
    
    print(f"DEBUG [CampaignRouter] LLM Decision: {decision} | Thought: {thought}")
    
    return {
        "next_action": decision,
        "internal_thoughts": [f"Brain: {thought} -> {decision}"],
        "step_count": current_step
    }
