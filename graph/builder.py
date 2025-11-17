from langgraph.graph import END, StateGraph
from schemas.state import GraphState
from nodes.query_analyzer import query_analyzer_node
from nodes.ambiguity_resolver import ambiguity_resolver_node
from nodes.sql_generator import sql_generator_node
from nodes.sql_checker import sql_checker_node
from nodes.sql_executor import sql_executor_node
from nodes.response_formatter import response_formatter_node
from nodes.general_responder import general_responder_node
from routers.routing_logic import (
    route_query_analyzer,
    route_ambiguity_resolver,
    route_sql_checker,
)


def build_graph():
    """
    Builds the LangGraph for the SQL agent.
    """
    builder = StateGraph(GraphState)

    # Add nodes
    builder.add_node("query_analyzer", query_analyzer_node)
    builder.add_node("ambiguity_resolver", ambiguity_resolver_node)
    builder.add_node("sql_generator", sql_generator_node)
    builder.add_node("sql_checker", sql_checker_node)
    builder.add_node("sql_executor", sql_executor_node)
    builder.add_node("response_formatter", response_formatter_node)
    builder.add_node("general_responder", general_responder_node)

    # Set entry point
    builder.set_entry_point("query_analyzer")

    # Add edges
    builder.add_conditional_edges(
        "query_analyzer",
        route_query_analyzer,
        {
            "ambiguity_resolver": "ambiguity_resolver",
            "sql_generator": "sql_generator",
            "general_responder": "general_responder",
        },
    )
    builder.add_conditional_edges(
        "ambiguity_resolver",
        route_ambiguity_resolver,
        {
            "sql_generator": "sql_generator",
            "__end__": END,
        },
    )
    builder.add_edge("sql_generator", "sql_checker")
    builder.add_conditional_edges(
        "sql_checker",
        route_sql_checker,
        {
            "sql_executor": "sql_executor",
            "__end__": END,
        },
    )
    builder.add_edge("sql_executor", "response_formatter")
    builder.add_edge("response_formatter", END)
    builder.add_edge("general_responder", END)

    graph = builder.compile()
    return graph


graph = build_graph()
