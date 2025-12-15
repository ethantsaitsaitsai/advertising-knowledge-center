from langgraph.graph import StateGraph, END, START
from nodes.supervisor_subgraph.state import SupervisorSubState
from nodes.supervisor_subgraph.planner import planner_node
from nodes.supervisor_subgraph.validator import validator_node

workflow = StateGraph(SupervisorSubState)

# Nodes
workflow.add_node("planner", planner_node)
workflow.add_node("validator", validator_node)

# Edges
workflow.add_edge(START, "planner")
workflow.add_edge("planner", "validator")

# Conditional Edge from Validator
# If "retry" -> Back to Planner
# If "finish" -> END
workflow.add_conditional_edges(
    "validator",
    lambda x: x.get("sub_next", "finish"),
    {
        "retry": "planner",
        "finish": END
    }
)

supervisor_subgraph = workflow.compile()
