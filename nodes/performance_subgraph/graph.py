from langgraph.graph import StateGraph, END, START
from nodes.performance_subgraph.state import PerformanceSubState
from nodes.performance_subgraph.router import performance_router_node
from nodes.performance_subgraph.generator import performance_generator_node
from nodes.performance_subgraph.executor import performance_executor_node

# Define Graph
workflow = StateGraph(PerformanceSubState)

# Nodes
workflow.add_node("router", performance_router_node)
workflow.add_node("generator", performance_generator_node)
workflow.add_node("executor", performance_executor_node)

# Edges
workflow.add_edge(START, "router")

# Conditional Edges from Router
workflow.add_conditional_edges(
    "router",
    lambda x: x["next_action"],
    {
        "generate_sql": "generator",
        "finish": END,
        "finish_no_data": END
    }
)

# Generator -> Executor
workflow.add_edge("generator", "executor")

# Executor -> Router (Check for success/error)
workflow.add_edge("executor", "router")

# Compile
performance_subgraph = workflow.compile()