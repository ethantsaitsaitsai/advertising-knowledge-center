"""
Analyst Subgraph for AKC Framework 3.0

Composes Retriever and Reporter into a cohesive workflow.
"""
from typing import Dict, Any
from langgraph.graph import StateGraph, END
from agent.state import AgentState
# from agent.retriever import data_retriever_node
from agent.analyst_v2 import data_retriever_v2_node # [NEW] Use V2 Agent
from agent.reporter import data_reporter_node

def create_analyst_graph():
    """
    Creates the subgraph: Retriever -> Reporter -> END
    """
    workflow = StateGraph(AgentState)

    # Add Nodes
    # workflow.add_node("DataRetriever", data_retriever_node)
    workflow.add_node("DataRetriever", data_retriever_v2_node) # [NEW]
    workflow.add_node("DataReporter", data_reporter_node)

    # Define Edges
    # Entry Point
    workflow.set_entry_point("DataRetriever")

    # Retriever -> Reporter (Always, mandatory flow)
    workflow.add_edge("DataRetriever", "DataReporter")

    # Reporter -> END
    workflow.add_edge("DataReporter", END)

    return workflow.compile()

# Singleton instance
analyst_graph = create_analyst_graph()
