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
1. **search_entity**: 覺得實體名稱模糊，或者 SQL 查無資料覺得可能是名字錯了。
2. **inspect_schema**: 覺得 Prompt 提供的 Schema 不夠用，且 Memory 中還沒有 Schema 資訊。
3. **generate_sql**: 準備好寫 SQL 了 (例如：已經搜尋到明確的單一實體，或不需要搜尋)。
4. **finish**: 任務完成 (已拿到資料 或 需要回報給上級)。
5. **finish_no_data**: 放棄 (試過所有方法都沒用)。
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
    search_results = state.get("search_results") # This is a list or None

    # Check if this is a clarification/disambiguation request from Supervisor
    # NEW: Also check for is_ambiguous flag OR intent mismatch indicators
    is_clarification_request = False

    if task.instruction_text:
        instruction_lower = task.instruction_text.lower()
        # Original keyword detection
        if any(keyword in instruction_lower
               for keyword in ["澄清", "clarify", "clarification", "選擇", "choose", "哪一個", "which one"]):
            is_clarification_request = True
        # NEW: Strong indicators that Supervisor wants clarification, not SQL execution
        elif any(keyword in instruction_lower
                 for keyword in ["詢問", "ask", "問", "list", "列出", "options", "哪一個", "which", "具體"]):
            is_clarification_request = True

    # CRITICAL: If IntentAnalyzer says it's ambiguous, this should be clarification step
    if hasattr(task, 'is_ambiguous') and task.is_ambiguous:
        print("DEBUG [CampaignRouter] is_ambiguous=True in task -> treating as clarification request")
        is_clarification_request = True

    # Helpers
    has_schema_info = any("Schema Inspection Result" in m for m in memory)
    
    has_data = False
    if campaign_data and campaign_data.get("data") and len(campaign_data["data"]) > 0:
        has_data = True
        
    executed_but_empty = False
    if campaign_data and not sql_error and not has_data:
        if campaign_data.get("generated_sqls"):
            executed_but_empty = True

    print(f"DEBUG [CampaignRouter] Step {current_step} Check: Data={has_data}, Empty={executed_but_empty}, SearchResults={len(search_results) if search_results is not None else 'None'}, Clarification={is_clarification_request}")

    # --- Deterministic Logic (The "Fast Path") ---

    # 0. Clarification Request -> Pass through to final user (HIGHEST PRIORITY)
    if is_clarification_request:
        print("DEBUG [CampaignRouter] Logic: Clarification request detected -> FINISH (with clarification message)")
        # CRITICAL FIX: Do NOT use task.instruction_text (Supervisor's internal instructions)
        # Instead, generate a proper user-facing clarification message
        # The Supervisor's instruction_text like "使用者想查詢悠遊卡相關的活動，但意圖不明確..."
        # is internal routing logic, NOT a user-facing message!

        # Generate a proper clarification message based on context
        # If we have search results, show them to the user
        if search_results and len(search_results) > 0:
            options_str = "\n".join([f"- {opt}" for opt in search_results[:10]])
            clarification_msg = (
                f"我找到了多個相關項目。請問您是指以下哪一個？\n\n"
                f"{options_str}\n\n"
                f"如果上述選項都不符合，請提供更多細節，我會為您重新搜尋。"
            )
        else:
            clarification_msg = (
                "我需要您提供更多信息，以便更精確地查詢數據。\n\n"
                "請確認或提供：\n"
                "- 您要查詢的具體實體/活動名稱\n"
                "- 具體想查詢的指標（例如：成效、投資金額、格式等）\n"
                "- 查詢的時間範圍（如適用）\n\n"
                "請提供更多細節，我會為您檢索相應的數據。"
            )

        return {
            "next_action": "finish",
            "final_response": clarification_msg,
            "internal_thoughts": ["Brain (Rule): is_ambiguous=True or clarification keyword detected. Generating user-facing clarification instead of internal instruction."],
            "step_count": current_step
        }

    # 1. Success -> Finish
    if has_data:
        print("DEBUG [CampaignRouter] Logic: Data found -> FINISH")
        return {
            "next_action": "finish",
            "internal_thoughts": ["Brain (Rule): Data found. Job done."],
            "step_count": current_step
        }

    # 2. Post-Search Logic
    # If search_results is NOT None, it means we JUST ran a search.
    if search_results is not None:
        count = len(search_results)
        print(f"DEBUG [CampaignRouter] Logic: Handling Search Results ({count} matches)")

        # Extract the search keyword from task (try multiple possible sources)
        search_keyword = None
        if task.filters.get("brands"):
            search_keyword = task.filters["brands"][0]
        elif task.filters.get("entities"):
            search_keyword = task.filters["entities"][0]

        # Filter for exact matches (entity name must match keyword exactly)
        exact_matches = []
        if search_keyword:
            exact_matches = [r for r in search_results if r.split(" (")[0] == search_keyword]
            print(f"DEBUG [CampaignRouter] Keyword: '{search_keyword}' | Exact matches: {len(exact_matches)} | Total: {count}")

        # Decision logic: ONLY pass if exactly 1 exact match AND it's the only result (no other matches)
        if len(exact_matches) == 1 and count == 1:
            # Exactly 1 exact match and no other results -> Generate SQL immediately
            return {
                "next_action": "generate_sql",
                "internal_thoughts": [f"Brain (Rule): Unique exact match found: {exact_matches[0]}. Proceeding to SQL."],
                "step_count": current_step
            }
        elif count == 0:
            # No results found - ask for clarification instead of just giving up
            # This handles cases where the entity name might be spelled differently or doesn't exist
            clarification_msg = (
                "我無法找到符合您描述的項目。\n\n"
                "這可能是因為：\n"
                "- 實體名稱拼寫不同\n"
                "- 項目名稱可能已更改\n"
                "- 該項目不存在於目前的數據庫中\n\n"
                "請嘗試：\n"
                "- 提供完整的項目名稱\n"
                "- 使用部分關鍵字進行搜尋\n"
                "- 確認時間範圍是否正確\n\n"
                "您可以重新描述想查詢的內容嗎？"
            )
            return {
                "next_action": "finish",
                "final_response": clarification_msg,
                "internal_thoughts": ["Brain (Rule): Search returned no results. Asking for clarification instead of giving up."],
                "step_count": current_step
            }
        else:
            # Any other case: multiple results, or exact match but with other results -> Ask user
            options_str = "\n".join([f"* {opt}" for opt in search_results[:5]])
            return {
                "next_action": "finish",
                "final_response": f"我找到了多個相關項目，請問您是指哪一個？\n{options_str}",
                "internal_thoughts": [f"Brain (Rule): Need clarification. Found {len(exact_matches)} exact match(es) out of {count} total results."],
                "step_count": current_step
            }

    # 3. SQL Error (Column/Table) -> Inspect Schema
    if sql_error:
        error_lower = sql_error.lower()
        if ("unknown column" in error_lower or "doesn't exist" in error_lower) and not has_schema_info:
             print("DEBUG [CampaignRouter] Logic: SQL Schema Error -> INSPECT_SCHEMA")
             return {
                 "next_action": "inspect_schema",
                 "internal_thoughts": ["Brain (Rule): Schema error detected. Checking schema."],
                 "step_count": current_step
             }

    # 4. Zero Rows + No Search History -> Search
    # Check if we ever searched. 'search_results' is None if we haven't searched yet (initially).
    # But wait, search_results stays in state? 
    # Actually, in LangGraph, state persists. So if we searched step 1, step 2 search_results is still there.
    # So we need to be careful. 
    # My logic above: "if search_results is not None". This implies we check it every step.
    # This might cause a loop if we went Search -> Unique -> SQL -> Error/Empty -> Router.
    # If SQL failed, we come back here. 'search_results' is still not None (1 match).
    # We would hit logic #2 again and go back to SQL. Loop!
    
    # FIX: We should only handle search results if we *Just* came from search.
    # Or, we consume 'search_results' (set to None)? No, immutable state usually.
    # Better: Check if we successfully generated SQL *after* search.
    # If 'executed_but_empty' is True, it means we tried SQL.
    
    if executed_but_empty:
        # We tried SQL and failed to get data.
        # If we ALREADY searched (search_results is not None), then searching again won't help unless we change term.
        # So if searched -> Ask for clarification about filters (date, etc.)
        if search_results is not None:
             print("DEBUG [CampaignRouter] Logic: SQL Empty + Already Searched -> Ask for clarification on filters")
             # Entity found but no data - likely a date range or filter issue
             clarification_msg = (
                 "我找到了相關的項目，但根據您提供的條件（例如時間範圍）查無數據。\n\n"
                 "請檢查：\n"
                 "- 時間範圍是否正確？(例如：該活動是否在您指定的時間範圍內執行)\n"
                 "- 是否需要調整其他篩選條件？\n\n"
                 "請確認或修改查詢條件，我會為您重新檢索。"
             )
             return {
                "next_action": "finish",
                "final_response": clarification_msg,
                "internal_thoughts": ["Brain: SQL returned empty. Asking for filter clarification (date, etc.)."],
                "step_count": current_step
             }
        else:
             print("DEBUG [CampaignRouter] Logic: SQL Empty + Never Searched -> SEARCH_ENTITY")
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

    # 6. First Step Optimization
    if current_step == 1 and not sql_error:
        print("DEBUG [CampaignRouter] Logic: First Step -> GENERATE_SQL")
        return {
            "next_action": "generate_sql",
            "internal_thoughts": ["Brain (Rule): First step. Attempting SQL."],
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
        
        # Override Loop protections
        if decision == "inspect_schema" and has_schema_info:
            decision = "generate_sql"
        if decision == "search_entity" and search_results is not None:
             # Already searched
             decision = "finish_no_data"
            
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