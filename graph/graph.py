from langgraph.graph import StateGraph, END
from typing import Literal
from schemas.state import AgentState
from nodes.slot_manager import slot_manager
from nodes.sql_generator import sql_generator
from nodes.sql_executor import sql_executor
from nodes.ask_for_missing_info import ask_for_missing_info
from nodes.response_synthesizer import response_synthesizer
from nodes.error_handler import error_handler

def check_slots_status(state: AgentState) -> Literal["ask_for_missing_info", "sql_generator"]:
    """
    Determines the next node to visit based on whether there are missing slots.
    """
    if state.get("missing_slots"):
        return "ask_for_missing_info"
    return "sql_generator"

def check_sql_error(state: AgentState) -> Literal["error_handler", "response_synthesizer"]:
    """
    Determines the next node to visit based on whether a SQL execution error occurred.
    """
    if state.get("error_message"):
        return "error_handler"
    return "response_synthesizer"

# Create a new state graph
workflow = StateGraph(AgentState)

# Add the nodes to the graph
workflow.add_node("slot_manager", slot_manager)
workflow.add_node("ask_for_missing_info", ask_for_missing_info)
workflow.add_node("sql_generator", sql_generator)
workflow.add_node("sql_executor", sql_executor)
workflow.add_node("error_handler", error_handler)
workflow.add_node("response_synthesizer", response_synthesizer)


# Set the entry point
workflow.set_entry_point("slot_manager")

# Add the conditional edges
workflow.add_conditional_edges(
    "slot_manager",
    check_slots_status,
    {
        "ask_for_missing_info": "ask_for_missing_info",
        "sql_generator": "sql_generator",
    },
)
workflow.add_conditional_edges(
    "sql_executor",
    check_sql_error,
    {
        "error_handler": "error_handler",
        "response_synthesizer": "response_synthesizer",
    },
)

# Add the regular edges
workflow.add_edge("ask_for_missing_info", END)
workflow.add_edge("sql_generator", "sql_executor")
workflow.add_edge("error_handler", "sql_generator") # Retry loop
workflow.add_edge("response_synthesizer", END)


# Compile the graph
app = workflow.compile()
