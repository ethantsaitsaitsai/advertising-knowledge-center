from typing import List
from pydantic import BaseModel, Field
from schemas.state import GraphState
from config.llm import llm
from prompts.analyzer_prompts import query_analyzer_prompt


class QueryAnalysis(BaseModel):
    """Represents the analysis of a user query."""
    intent: str = Field(description="The user's intent, either 'database_query' or 'general_question'.")
    ambiguous_terms: List[str] = Field(description="A list of terms in the query that are ambiguous.")


def query_analyzer_node(state: GraphState) -> GraphState:
    """
    Analyzes the user's query to identify intent and ambiguous terms.
    """
    print("---QUERY ANALYZER---")
    # The user's query is the last message in the list.
    # It can be a string or a list of content blocks.
    raw_content = state["messages"][-1].content
    if isinstance(raw_content, list) and raw_content and "text" in raw_content[0]:
        query = raw_content[0]["text"]
    else:
        query = raw_content

    # Use LLM to analyze the query
    llm_chain = llm.with_structured_output(QueryAnalysis, method="function_calling")
    analysis_result_obj = llm_chain.invoke(
        [
            ("system", query_analyzer_prompt),
            ("human", query),
        ]
    )

    # Convert the Pydantic object to a dict for the state
    analysis_result = analysis_result_obj.dict()

    # Update state
    return {
        "query": query,
        "clarified_query": query,
        "analysis_result": analysis_result,
        "current_stage": "query_analyzer",
    }
