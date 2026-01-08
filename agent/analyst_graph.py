"""
Analyst Subgraph for AKC Framework 3.0

Composes Retriever and Reporter into a cohesive workflow.
"""
from typing import Dict, Any
from langgraph.graph import StateGraph, END
from agent.state import AgentState
# from agent.retriever import data_retriever_node
from agent.analyst_v2 import data_retriever_v2_node, quality_check_node # [NEW] Import Quality Check
from agent.reporter import data_reporter_node

def create_analyst_graph():
    """
    Creates the subgraph: Retriever -> QualityCheck -> Reporter -> END
    """
    workflow = StateGraph(AgentState)

    # Add Nodes
    # workflow.add_node("DataRetriever", data_retriever_node)
    workflow.add_node("DataRetriever", data_retriever_v2_node) # [NEW]
    workflow.add_node("QualityCheck", quality_check_node)
    workflow.add_node("DataReporter", data_reporter_node)

    # Define Edges
    # Entry Point
    workflow.set_entry_point("DataRetriever")

    # Retriever -> QualityCheck
    workflow.add_edge("DataRetriever", "QualityCheck")

    # QualityCheck -> Conditional Routing
    workflow.add_conditional_edges(
        "QualityCheck",
        lambda x: x.get("next", "Reporter"), # Default to Reporter
        {
            "DataAnalyst": "DataRetriever", # Loop back for retry
            "Reporter": "DataReporter",
            "END": END # Early exit for ambiguity clarification
        }
    )

    # Reporter -> END
    workflow.add_edge("DataReporter", END)

    return workflow.compile()

# Singleton instance
analyst_graph = create_analyst_graph()
