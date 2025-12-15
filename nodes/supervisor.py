from nodes.supervisor_subgraph.graph import supervisor_subgraph
from schemas.state import AgentState

def supervisor_node(state: AgentState):
    """
    Main Supervisor Node (Wrapper).
    Invokes the Supervisor SubGraph which contains the Plan-Critique-Retry loop.
    """
    # Check if the last message is a clarification/final response from CampaignAgent
    # If so, stop the loop and go directly to ResponseSynthesizer
    messages = state.get("messages", [])
    if messages:
        last_message = messages[-1]
        # Check if the last message is from CampaignAgent (i.e., a clarification or final response)
        if hasattr(last_message, "name") and last_message.name == "CampaignAgent":
            print("DEBUG [SupervisorWrapper] CampaignAgent returned a message. Stopping Supervisor loop.")
            # Don't loop back through Supervisor; go directly to ResponseSynthesizer
            return {
                "next": "ResponseSynthesizer",
                "supervisor_payload": None,
                "supervisor_instructions": None
            }

    # Check if we're in a clarification waiting state
    # (last CampaignAgent message is clarification, and now we have a new HumanMessage following it)
    clarification_pending = state.get("clarification_pending", False)
    if clarification_pending and messages and len(messages) >= 2:
        last_message = messages[-1]
        # If last message is from user (HumanMessage), it's a clarification response
        from langchain_core.messages import HumanMessage
        if isinstance(last_message, HumanMessage):
            print("DEBUG [SupervisorWrapper] Clarification response detected. Routing to IntentAnalyzer for re-analysis.")
            # Update the flag and let IntentAnalyzer process the user's clarification response
            # This will update the entities and clear is_ambiguous
            return {
                "next": "IntentAnalyzer",
                "supervisor_payload": None,
                "supervisor_instructions": None,
                "clarification_pending": False  # Clear the flag
            }

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