from typing import Literal
from schemas.state import GraphState


def route_query_analyzer(state: GraphState) -> Literal["ambiguity_resolver", "sql_generator", "general_responder"]:
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
        return "sql_generator"


def route_ambiguity_resolver(state: GraphState) -> Literal["__end__", "sql_generator"]:


    """


    Routes the flow after the ambiguity_resolver_node.


    If human input is required, the graph ends to wait for input.


    Otherwise, it proceeds to the sql_generator.


    """


    print("---ROUTE AMBIGUITY RESOLVER---")


    if state["current_stage"] == "human_in_the_loop":


        return "__end__"


    return "sql_generator"








def route_sql_checker(state: GraphState) -> Literal["sql_executor", "__end__"]:


    """


    Routes the flow based on the SQL validation result.


    """


    print("---ROUTE SQL CHECKER---")


    if state["sql_is_correct"]:


        return "sql_executor"


    else:


        # If SQL is incorrect, end the flow for now.


        # Future improvement: loop back to sql_generator with feedback.


        return "__end__"

