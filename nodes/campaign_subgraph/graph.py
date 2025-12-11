from langgraph.graph import StateGraph, END, START
from nodes.campaign_subgraph.state import CampaignSubState
from nodes.campaign_subgraph.router import router_node
from nodes.campaign_subgraph.generator import generator_node
from nodes.campaign_subgraph.executor import executor_node
from nodes.campaign_subgraph.search_tool import search_node
from nodes.campaign_subgraph.schema_tool import schema_tool_node

workflow = StateGraph(CampaignSubState)

# Nodes
workflow.add_node("router", router_node)
workflow.add_node("search", search_node)
workflow.add_node("schema_tool", schema_tool_node) # New Node
workflow.add_node("generator", generator_node)
workflow.add_node("executor", executor_node)

# Edges
workflow.add_edge(START, "router")

# Router Logic
workflow.add_conditional_edges(
    "router",
    lambda state: state["next_action"],
    {
        "search_entity": "search",
        "inspect_schema": "schema_tool", # New Route
        "generate_sql": "generator",
        "finish": END,
        "finish_no_data": END
    }
)

# Tool/Worker Logic -> Back to Router
workflow.add_edge("search", "router")
workflow.add_edge("schema_tool", "router") # Schema tool reports back to Brain
workflow.add_edge("generator", "executor")
workflow.add_edge("executor", "router")

campaign_subgraph = workflow.compile()