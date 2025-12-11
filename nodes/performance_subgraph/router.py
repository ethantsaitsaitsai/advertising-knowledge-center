from typing import Literal, Union
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from config.llm import llm
from nodes.performance_subgraph.state import PerformanceSubState

# Decision Options
class PerformanceDecision(BaseModel):
    """Decide the next step for the Performance Agent."""
    next_action: Literal["generate_sql", "finish", "finish_no_data"] = Field(
        ..., description="The next action."
    )
    thought_process: str = Field(
        ..., description="Reasoning."
    )

ROUTER_SYSTEM_PROMPT = """你是一個 ClickHouse 查詢專家的「大腦」。
**決策邏輯**:
1. **generate_sql**: 還沒執行過，或執行失敗需要重試。
2. **finish**: 成功獲取數據。
3. **finish_no_data**: 嘗試多次後仍失敗，或確定無數據。
"""

ROUTER_USER_MESSAGE = """
**目前狀態**:
- IDs: {ids_count}
- Data Rows: {data_count}
- SQL Error: {sql_error}

**步數**: {step_count} / {max_steps}

請決策。
"""

prompt = ChatPromptTemplate.from_messages([
    ("system", ROUTER_SYSTEM_PROMPT),
    ("user", ROUTER_USER_MESSAGE)
])

chain = prompt | llm.with_structured_output(PerformanceDecision)

def performance_router_node(state: PerformanceSubState):
    """
    The Brain of the Performance Agent.
    """
    MAX_STEPS = 5
    current_step = state.get("step_count", 0) + 1
    
    # Extract State
    sql_error = state.get("sql_error")
    data = state.get("final_dataframe")
    ids = state.get("campaign_ids", [])
    
    has_data = bool(data)
    
    print(f"DEBUG [PerfRouter] Step {current_step} Check: Data={has_data}, Error={bool(sql_error)}")

    # --- Deterministic Logic ---

    # 1. Success -> Finish
    if has_data:
        print("DEBUG [PerfRouter] Logic: Data found -> FINISH")
        return {
            "next_action": "finish",
            "internal_thoughts": ["Brain (Rule): Data found. Job done."],
            "step_count": current_step
        }

    # 2. First Step -> Generate
    if current_step == 1:
        return {
            "next_action": "generate_sql",
            "internal_thoughts": ["Brain (Rule): First step. Generating SQL."],
            "step_count": current_step
        }

    # 3. SQL Error -> Retry (Generate)
    if sql_error and current_step < MAX_STEPS:
        print("DEBUG [PerfRouter] Logic: SQL Error -> RETRY")
        return {
            "next_action": "generate_sql",
            "internal_thoughts": [f"Brain (Rule): Error detected ({sql_error}). Retrying."],
            "step_count": current_step
        }
        
    # 4. Max Steps -> Give up
    if current_step >= MAX_STEPS:
        return {
            "next_action": "finish_no_data",
            "internal_thoughts": ["Brain: Max steps reached."],
            "step_count": current_step
        }

    # Fallback to LLM (Rarely needed for this simple flow, but good for edge cases)
    # Actually, for Performance Agent, the logic is quite linear. We can skip LLM router to save time.
    # Let's keep it deterministic.
    
    return {
        "next_action": "finish_no_data",
        "internal_thoughts": ["Brain: No data and no error loop. Finishing."],
        "step_count": current_step
    }
