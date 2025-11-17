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