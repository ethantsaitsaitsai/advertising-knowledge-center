
from langgraph.graph import StateGraph, END, START
from schemas.state import AgentState
from nodes.supervisor import supervisor_node
from nodes.campaign_node_wrapper import campaign_node
from nodes.performance_node_wrapper import performance_node
from nodes.intent_analyzer import intent_analyzer_node

# Define the graph
workflow = StateGraph(AgentState)

# Add Nodes
workflow.add_node("IntentAnalyzer", intent_analyzer_node) # The Brain
workflow.add_node("Supervisor", supervisor_node)          # The Manager
workflow.add_node("CampaignAgent", campaign_node)         # Worker A
workflow.add_node("PerformanceAgent", performance_node)   # Worker B

# Add Edges
# Entry point
workflow.add_edge(START, "IntentAnalyzer")
workflow.add_edge("IntentAnalyzer", "Supervisor")

# Supervisor Routing
workflow.add_conditional_edges(
    "Supervisor",
    lambda x: x["next"],
    {
        "CampaignAgent": "CampaignAgent",
        "PerformanceAgent": "PerformanceAgent",
        "FINISH": END
    }
)

# Workers return to Supervisor
workflow.add_edge("CampaignAgent", "Supervisor")
workflow.add_edge("PerformanceAgent", "Supervisor")

# Compile
app = workflow.compile()
