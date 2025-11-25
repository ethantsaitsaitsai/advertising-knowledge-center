from langgraph.graph import StateGraph, END, START
from typing import Literal
from schemas.state import AgentState

# --- 原有節點 Imports ---
from nodes.slot_manager import slot_manager_node
from nodes.sql_generator import sql_generator
from nodes.sql_executor import sql_executor
from nodes.ask_for_clarification import ask_for_clarification_node
from nodes.response_synthesizer import response_synthesizer
from nodes.error_handler import error_handler
from nodes.entity_search import entity_search_node
from nodes.state_updater import state_updater_node
from nodes.chitchat import chitchat_node
from nodes.sql_validator import sql_validator_node
from nodes.clickhouse_generator import clickhouse_generator_node
from nodes.clickhouse_executor import clickhouse_executor_node
from nodes.data_fusion import data_fusion_node
from nodes.clickhouse_validator import clickhouse_validator_node
from nodes.clickhouse_error_handler import clickhouse_error_handler_node


# --- 既有路由函數 ---
def route_user_input(state: AgentState) -> Literal["state_updater", "slot_manager"]:
    if state.get("expecting_user_clarification", False):
        return "state_updater"
    return "slot_manager"


def route_after_slot_manager(state: AgentState) -> Literal["entity_search", "ask_for_clarification",
                                                           "sql_generator", "chitchat"]:
    intent = state.get("intent_type", "data_query")
    if intent in ["greeting", "other"]:
        return "chitchat"
    if state.get("ambiguous_terms"):
        return "entity_search"
    if state.get("missing_slots"):
        return "ask_for_clarification"
    return "sql_generator"


def route_after_entity_search(state: AgentState) -> Literal["ask_for_clarification", "sql_generator"]:
    if state.get("candidate_values"):
        return "ask_for_clarification"
    return "sql_generator"


def route_after_validation(state: AgentState) -> Literal["sql_executor", "sql_generator"]:
    if state.get("is_valid_sql"):
        return "sql_executor"
    else:
        return "sql_generator"


def route_after_mysql_execution(state: AgentState) -> Literal["error_handler",
                                                              "clickhouse_generator",
                                                              "response_synthesizer"]:
    """
    Determines the next path after MySQL execution.
    """
    if state.get("error_message"):
        return "error_handler"

    analysis_needs = state.get("analysis_needs", {})
    metrics = analysis_needs.get("metrics", [])

    ch_metrics = [
        "Impression_Sum", "Click_Sum", "View3s_Sum",
        "Q100_Sum", "CTR_Calc", "CPC_Calc"
    ]

    if any(m in ch_metrics for m in metrics):
        return "clickhouse_generator"

    return "response_synthesizer"


def route_after_ch_validation(state: AgentState) -> Literal["clickhouse_executor", "clickhouse_generator"]:
    """
    Routes to the executor if ClickHouse SQL is valid, otherwise returns to the generator.
    """
    if state.get("is_valid_sql"):
        return "clickhouse_executor"
    else:
        return "clickhouse_generator"


def check_clickhouse_error(state: AgentState) -> Literal["clickhouse_error_handler", "data_fusion"]:
    """
    Checks for errors after ClickHouse execution.
    """
    if state.get("error_message"):
        return "clickhouse_error_handler"
    return "data_fusion"


# Create a new state graph
workflow = StateGraph(AgentState)

# --- Add Nodes ---
workflow.add_node("slot_manager", slot_manager_node)
workflow.add_node("entity_search", entity_search_node)
workflow.add_node("ask_for_clarification", ask_for_clarification_node)
workflow.add_node("state_updater", state_updater_node)
workflow.add_node("sql_generator", sql_generator)
workflow.add_node("sql_validator", sql_validator_node)
workflow.add_node("sql_executor", sql_executor)
workflow.add_node("error_handler", error_handler)
workflow.add_node("response_synthesizer", response_synthesizer)
workflow.add_node("chitchat", chitchat_node)
workflow.add_node("clickhouse_generator", clickhouse_generator_node)
workflow.add_node("clickhouse_validator", clickhouse_validator_node)
workflow.add_node("clickhouse_executor", clickhouse_executor_node)
workflow.add_node("clickhouse_error_handler", clickhouse_error_handler_node)
workflow.add_node("data_fusion", data_fusion_node)


# --- Set Edges ---

# Entry Point
workflow.add_conditional_edges(
    START,
    route_user_input,
    {
        "slot_manager": "slot_manager",
        "state_updater": "state_updater",
    },
)

# SlotManager Routing
workflow.add_conditional_edges(
    "slot_manager",
    route_after_slot_manager,
    {
        "entity_search": "entity_search",
        "ask_for_clarification": "ask_for_clarification",
        "sql_generator": "sql_generator",
        "chitchat": "chitchat",
    },
)

# Entity Search Routing
workflow.add_conditional_edges(
    "entity_search",
    route_after_entity_search,
    {
        "ask_for_clarification": "ask_for_clarification",
        "sql_generator": "sql_generator",
    },
)

# MySQL Validator Routing
workflow.add_conditional_edges(
    "sql_validator",
    route_after_validation,
    {
        "sql_executor": "sql_executor",
        "sql_generator": "sql_generator",
    },
)

# MySQL Executor Routing
workflow.add_conditional_edges(
    "sql_executor",
    route_after_mysql_execution,
    {
        "error_handler": "error_handler",
        "clickhouse_generator": "clickhouse_generator",
        "response_synthesizer": "response_synthesizer",
    },
)

# ClickHouse Validation Flow
workflow.add_edge("clickhouse_generator", "clickhouse_validator")
workflow.add_conditional_edges(
    "clickhouse_validator",
    route_after_ch_validation,
    {
        "clickhouse_executor": "clickhouse_executor",
        "clickhouse_generator": "clickhouse_generator"
    }
)

# ClickHouse Executor Flow
workflow.add_conditional_edges(
    "clickhouse_executor",
    check_clickhouse_error,
    {
        "clickhouse_error_handler": "clickhouse_error_handler",
        "data_fusion": "data_fusion"
    }
)
workflow.add_edge("clickhouse_error_handler", "clickhouse_generator")  # Retry loop
workflow.add_edge("data_fusion", "response_synthesizer")


# Standard Edges
workflow.add_edge("ask_for_clarification", END)
workflow.add_edge("state_updater", "sql_generator")
workflow.add_edge("sql_generator", "sql_validator")
workflow.add_edge("error_handler", "sql_generator")
workflow.add_edge("response_synthesizer", END)
workflow.add_edge("chitchat", END)


# Compile the graph
app = workflow.compile()
