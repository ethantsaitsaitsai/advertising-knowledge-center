from langgraph.graph import StateGraph, END
from typing import Literal
from schemas.state import AgentState
from nodes.slot_manager import slot_manager_node
from nodes.sql_generator import sql_generator
from nodes.sql_executor import sql_executor
from nodes.ask_for_clarification import ask_for_clarification_node
from nodes.response_synthesizer import response_synthesizer
from nodes.error_handler import error_handler
from nodes.entity_search import entity_search_node
from nodes.state_updater import state_updater_node

def route_after_slot_manager(state: AgentState) -> Literal["entity_search", "ask_for_clarification", "sql_generator"]:
    """
    Determines the next node to visit after slot_manager based on missing slots and ambiguous terms.
    """
    if state.get("ambiguous_terms"):
        return "entity_search"
    if state.get("missing_slots"):
        return "ask_for_clarification"
    return "sql_generator"

def route_after_entity_search(state: AgentState) -> Literal["ask_for_clarification", "sql_generator"]:
    """
    Determines the next node to visit after entity_search based on whether candidate values were found.
    """
    if state.get("candidate_values"):
        return "ask_for_clarification"
    return "sql_generator" # If no candidates found, proceed as if no ambiguity

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
workflow.add_node("slot_manager", slot_manager_node)
workflow.add_node("entity_search", entity_search_node)
workflow.add_node("ask_for_clarification", ask_for_clarification_node)
workflow.add_node("state_updater", state_updater_node)
workflow.add_node("sql_generator", sql_generator)
workflow.add_node("sql_executor", sql_executor)
workflow.add_node("error_handler", error_handler)
workflow.add_node("response_synthesizer", response_synthesizer)


# Set the entry point
workflow.set_entry_point("slot_manager")

# Add the conditional edges
workflow.add_conditional_edges(
    "slot_manager",
    route_after_slot_manager,
    {
        "entity_search": "entity_search",
        "ask_for_clarification": "ask_for_clarification",
        "sql_generator": "sql_generator",
    },
)
workflow.add_conditional_edges(
    "entity_search",
    route_after_entity_search,
    {
        "ask_for_clarification": "ask_for_clarification",
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
workflow.add_edge("ask_for_clarification", END) # Awaiting user response
workflow.add_edge("state_updater", "sql_generator")
workflow.add_edge("sql_generator", "sql_executor")
workflow.add_edge("error_handler", "sql_generator") # Retry loop
workflow.add_edge("response_synthesizer", END)


# Compile the graph
app = workflow.compile()
