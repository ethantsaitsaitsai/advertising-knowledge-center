from typing import List
from pydantic import BaseModel, Field
from schemas.state import GraphState
from config.llm import llm
from prompts.analyzer_prompts import query_analyzer_prompt_template


class QueryAnalysis(BaseModel):
    """Represents the analysis of a user query."""
    new_query: str = Field(description="The synthesized query after analyzing the conversation history.")
    intent: str = Field(description="The user's intent, either 'database_query' or 'general_question'.")
    ambiguous_terms: List[str] = Field(description="A list of terms in the query that are ambiguous.")


def query_analyzer_node(state: GraphState) -> GraphState:
    """
    Analyzes the user's query to identify intent and ambiguous terms.
    """
    print("---QUERY ANALYZER---")

    # Use LLM to analyze the query
    llm_chain = llm.with_structured_output(QueryAnalysis, method="function_calling")
    analysis_result_obj = llm_chain.invoke(
        [
            ("system", query_analyzer_prompt_template),
            *state["messages"],  # Pass the entire message history
        ]
    )

    # Convert the Pydantic object to a dict for the state
    analysis_result = analysis_result_obj.dict()

    # Determine the original query. If state['query'] is already set, keep it.
    # Otherwise, this is the first run, so we set it from the first message.
    original_query = state.get("query") or state["messages"][0].content

    # Update state
    return {
        "query": original_query,
        "clarified_query": analysis_result["new_query"],
        "analysis_result": analysis_result,
        "current_stage": "query_analyzer",
    }

