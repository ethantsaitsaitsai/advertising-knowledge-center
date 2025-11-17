from langgraph.graph import END, StateGraph
from schemas.state import GraphState
from nodes.query_analyzer import query_analyzer_node
from nodes.ambiguity_resolver import ambiguity_resolver_node
from nodes.query_executor import query_executor_node
from nodes.response_formatter import response_formatter_node
from nodes.general_responder import general_responder_node
from routers.routing_logic import route_query_analyzer


def build_graph():
    """
    Builds the LangGraph for the SQL agent.
    """
    builder = StateGraph(GraphState)

    # Add nodes
    builder.add_node("query_analyzer", query_analyzer_node)
    builder.add_node("ambiguity_resolver", ambiguity_resolver_node)
    builder.add_node("query_executor", query_executor_node)
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
            "query_executor": "query_executor",
            "general_responder": "general_responder",
        },
    )
    builder.add_edge("ambiguity_resolver", "query_executor")
    builder.add_edge("query_executor", "response_formatter")
    builder.add_edge("response_formatter", END)
    builder.add_edge("general_responder", END)

    graph = builder.compile()
    return graph


graph = build_graph()
