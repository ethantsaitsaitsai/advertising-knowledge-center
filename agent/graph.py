"""
AKC Framework 3.0 - Main Graph

Simplified architecture:
User Input → Intent Router → Data Analyst Agent → Output

No more Supervisor-Worker pattern, no SubGraphs.
All business logic is in Python SQL Templates and Pandas processing.
"""
from langgraph.graph import StateGraph, END, START
from agent.state import AgentState
from agent.router import intent_router_node
from agent.analyst import data_analyst_node
from langchain_core.messages import HumanMessage, BaseMessage
from typing import Dict, Any


def input_adapter_node(state: AgentState) -> Dict[str, Any]:
    """
    Input Adapter: Ensures messages are in correct format for LangGraph Studio.

    Handles both CLI and Studio inputs:
    - CLI: messages already in HumanMessage format
    - Studio: may need conversion from dict or string format
    """
    messages = state.get("messages", [])

    print(f"DEBUG [InputAdapter] Received {len(messages)} messages")

    # If messages is empty, check for 'input' field (LangGraph Studio format)
    if not messages and "input" in state:
        user_input = state["input"]
        print(f"DEBUG [InputAdapter] Converting 'input' field to HumanMessage: {user_input}")
        return {"messages": [HumanMessage(content=str(user_input))]}

    # Convert dict messages to proper Message objects if needed
    converted_messages = []
    for msg in messages:
        if isinstance(msg, BaseMessage):
            converted_messages.append(msg)
        elif isinstance(msg, dict):
            msg_type = msg.get("type", "human")
            content = msg.get("content", "")
            if msg_type == "human":
                converted_messages.append(HumanMessage(content=content))
                print(f"DEBUG [InputAdapter] Converted dict to HumanMessage: {content[:50]}...")
            else:
                # Keep other message types as-is (shouldn't happen at input)
                converted_messages.append(msg)
        else:
            # If it's a string, treat as human message
            converted_messages.append(HumanMessage(content=str(msg)))
            print(f"DEBUG [InputAdapter] Converted string to HumanMessage: {str(msg)[:50]}...")

    if converted_messages != messages:
        return {"messages": converted_messages}
    else:
        return {}


# Define the workflow
workflow = StateGraph(AgentState)

# Add Nodes
workflow.add_node("InputAdapter", input_adapter_node)
workflow.add_node("IntentRouter", intent_router_node)
workflow.add_node("DataAnalyst", data_analyst_node)

# Add Edges
# User input → Input Adapter → Intent Router
workflow.add_edge(START, "InputAdapter")
workflow.add_edge("InputAdapter", "IntentRouter")

# Intent Router → Conditional routing
workflow.add_conditional_edges(
    "IntentRouter",
    lambda x: x.get("next", "END"),
    {
        "DataAnalyst": "DataAnalyst",
        "END": END
    }
)

# Data Analyst → END (always terminates after analysis)
workflow.add_edge("DataAnalyst", END)

# Compile the graph
app = workflow.compile()