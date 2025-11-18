from langgraph.graph import StateGraph, END, START
from schemas.state import GraphState
from nodes.intent_analyzer import intent_analyzer_node
from nodes.general_responder import general_responder_node
from nodes.ambiguity_detector import ambiguity_detector_node
from nodes.ambiguity_resolver import ambiguity_resolver_node
from nodes.sql_generator import sql_generator_node
from nodes.sql_constraint_checker import sql_constraint_checker_node
from nodes.sql_executor import sql_executor_node
from nodes.response_formatter import response_formatter_node
from typing import Literal
from langchain_core.messages import ToolMessage

# --- Router Functions ---

def route_intent(state: GraphState) -> Literal["chitchat", "query"]:
    """Routes based on the user's intent."""
    if state.get("intent") == "chitchat":
        return "chitchat"
    return "query"

def route_ambiguity(state: GraphState) -> Literal["clarify", "generate_sql"]:
    """Routes based on whether ambiguity needs clarification."""
    last_message = state["messages"][-1]
    if "clarification_request" in last_message.additional_kwargs:
        return "clarify"
    return "generate_sql"

def route_sql_checker(state: GraphState) -> Literal["execute", "regenerate"]:
    """Routes based on the SQL constraint checker's output."""
    if state.get("sql_is_safe"):
        return "execute"
    return "regenerate"

def route_sql_result(state: GraphState) -> Literal["format_response", "recheck_ambiguity", "regenerate_sql"]:
    """
    Routes based on the SQL execution result.
    If data is found, format the response.
    If the result is empty, loop back to re-check for ambiguity.
    If there was an execution error, loop back to regenerate the SQL.
    """
    sql_result = state.get("sql_result", "")
    
    if "Execution Error:" in sql_result:
        # Add error message to history and loop back to SQL generator
        error_message = ToolMessage(content=f"System Note: The last query failed with a database error: {sql_result}. Please regenerate the query, paying close attention to syntax and column names.", tool_call_id="sql_executor")
        state["messages"].append(error_message)
        return "regenerate_sql"
        
    # Check for empty result (e.g., '[]', '()', or just whitespace)
    if not sql_result or sql_result.strip() in ["[]", "()"]:
        # Add system note to history and loop back to ambiguity detector
        system_note = ToolMessage(content="System Note: The last query returned no results. The search terms may be too specific or incorrect. Please re-evaluate the user's query for ambiguity.", tool_call_id="sql_executor")
        state["messages"].append(system_note)
        return "recheck_ambiguity"
        
    # If we have a valid, non-empty result
    return "format_response"

# --- Build the Graph ---

builder = StateGraph(GraphState)

# Add nodes
builder.add_node("intent_analyzer", intent_analyzer_node)
builder.add_node("general_responder", general_responder_node)
builder.add_node("ambiguity_detector", ambiguity_detector_node)
builder.add_node("ambiguity_resolver", ambiguity_resolver_node)
builder.add_node("sql_generator", sql_generator_node)
builder.add_node("sql_constraint_checker", sql_constraint_checker_node)
builder.add_node("sql_executor", sql_executor_node)
builder.add_node("response_formatter", response_formatter_node)

# Set entry point
builder.set_entry_point("intent_analyzer")

# Define edges
builder.add_conditional_edges(
    "intent_analyzer",
    route_intent,
    {"chitchat": "general_responder", "query": "ambiguity_detector"},
)
builder.add_edge("general_responder", END)

builder.add_edge("ambiguity_detector", "ambiguity_resolver")

builder.add_conditional_edges(
    "ambiguity_resolver",
    route_ambiguity,
    {"clarify": END, "generate_sql": "sql_generator"},
)

builder.add_edge("sql_generator", "sql_constraint_checker")

builder.add_conditional_edges(
    "sql_constraint_checker",
    route_sql_checker,
    {"execute": "sql_executor", "regenerate": "sql_generator"},
)

# New conditional edge after SQL execution
builder.add_conditional_edges(
    "sql_executor",
    route_sql_result,
    {
        "format_response": "response_formatter",
        "recheck_ambiguity": "ambiguity_detector",
        "regenerate_sql": "sql_generator",
    },
)

builder.add_edge("response_formatter", END)

# Compile the graph
graph = builder.compile()
