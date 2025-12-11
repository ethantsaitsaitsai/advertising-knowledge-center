
from langgraph.graph import StateGraph, END, START
from schemas.state import AgentState
from nodes.supervisor import supervisor_node
from nodes.campaign_node_wrapper import campaign_node
from nodes.performance_node_wrapper import performance_node
from nodes.intent_analyzer import intent_analyzer_node
from nodes.response_synthesizer import response_synthesizer_node
from nodes.parallel_executor import parallel_executor_node
from nodes.entity_resolver import entity_resolver_node

# Define the graph
workflow = StateGraph(AgentState)

# Add Nodes
workflow.add_node("IntentAnalyzer", intent_analyzer_node) # Upgraded to Agent
workflow.add_node("EntityResolver", entity_resolver_node) # ID Resolution
workflow.add_node("Supervisor", supervisor_node)          
workflow.add_node("CampaignAgent", campaign_node)         
workflow.add_node("PerformanceAgent", performance_node)   
workflow.add_node("ParallelExecutor", parallel_executor_node)
workflow.add_node("ResponseSynthesizer", response_synthesizer_node)

# Add Edges
# Flow: Start -> Intent -> Resolver -> Supervisor
workflow.add_edge(START, "IntentAnalyzer")
workflow.add_edge("IntentAnalyzer", "EntityResolver")
workflow.add_edge("EntityResolver", "Supervisor")

# Supervisor Routing
workflow.add_conditional_edges(
    "Supervisor",
    lambda x: x["next"],
    {
        "CampaignAgent": "CampaignAgent",
        "PerformanceAgent": "PerformanceAgent",
        "ParallelExecutor": "ParallelExecutor",
        "ResponseSynthesizer": "ResponseSynthesizer",
        "FINISH": END
    }
)

# Workers return to Supervisor
workflow.add_edge("CampaignAgent", "Supervisor")
workflow.add_edge("PerformanceAgent", "Supervisor")
workflow.add_edge("ParallelExecutor", "Supervisor")

# Synthesizer ends the flow
workflow.add_edge("ResponseSynthesizer", END)

# Compile
app = workflow.compile()
