from nodes.supervisor_subgraph.graph import supervisor_subgraph
from schemas.state import AgentState

def supervisor_node(state: AgentState):
    """
    Main Supervisor Node (Wrapper).
    Invokes the Supervisor SubGraph which contains the Plan-Critique-Retry loop.
    """
    # Initialize SubState variables not present in Global State
    sub_input = state.copy()
    sub_input["draft_decision"] = None
    sub_input["internal_feedback"] = []
    
    # Invoke SubGraph
    print("DEBUG [SupervisorWrapper] Invoking SubGraph...")
    result = supervisor_subgraph.invoke(sub_input)
    print("DEBUG [SupervisorWrapper] SubGraph Finished.")
    
    # Return updates to global state
    return {
        "next": result["next"],
        "supervisor_payload": result.get("supervisor_payload"),
        "supervisor_instructions": result.get("supervisor_instructions")
    }