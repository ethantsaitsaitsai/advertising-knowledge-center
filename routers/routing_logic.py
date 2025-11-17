from typing import Literal
from schemas.state import GraphState


def route_query_analyzer(state: GraphState) -> Literal["ambiguity_resolver", "query_executor", "general_responder"]:
    """
    Routes the flow based on the analysis result from query_analyzer_node.
    """
    print("---ROUTE QUERY ANALYZER---")
    analysis_result = state["analysis_result"]

    if analysis_result.get("intent") == "general_question":
        return "general_responder"

    if analysis_result.get("ambiguous_terms"):
        return "ambiguity_resolver"
    else:
        return "query_executor"


def route_ambiguity_resolver(state: GraphState) -> Literal["__end__", "query_executor"]:
    """
    Routes the flow after the ambiguity_resolver_node.
    If human input is required, the graph ends to wait for input.
    Otherwise, it proceeds to the query_executor.
    """
    print("---ROUTE AMBIGUITY RESOLVER---")
    if state["current_stage"] == "human_in_the_loop":
        return "__end__"
    return "query_executor"