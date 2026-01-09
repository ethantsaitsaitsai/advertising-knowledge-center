"""
AKC Framework 3.0 - Main Graph

Simplified architecture:
User Input → Intent Router → Data Analyst Subgraph (Retriever -> Reporter) → Output
"""
from langgraph.graph import StateGraph, END, START
from langgraph.checkpoint.memory import MemorySaver # [NEW]
from agent.state import AgentState
from agent.router import intent_router_node
from agent.analyst_graph import analyst_graph # [NEW] Import Subgraph
from langchain_core.messages import HumanMessage, BaseMessage
from typing import Dict, Any


def input_adapter_node(state: AgentState) -> Dict[str, Any]:
    """
    Input Adapter: Ensures messages are in correct format for LangGraph Studio.
    """
    messages = state.get("messages", [])
    
    # 1. Handle "input" key (LangGraph Studio / Direct Input)
    if "input" in state and state["input"]:
        user_input = state["input"]
        # Check if this input is already the last message to avoid duplication
        if not messages or (hasattr(messages[-1], "content") and messages[-1].content != user_input):
             print(f"DEBUG [InputAdapter] Converting 'input' field to HumanMessage: {user_input}")
             return {"messages": [HumanMessage(content=str(user_input))]}
        elif isinstance(messages[-1], dict) and messages[-1].get("content") != user_input:
             return {"messages": [HumanMessage(content=str(user_input))]}

    # 2. Handle Dict to Object conversion
    # Removed to avoid duplication (operator.add appends).
    # Downstream nodes (IntentRouter) should handle dicts or LangChain should accept them.
    
    return {}

def data_analyst_wrapper_node(state: AgentState) -> Dict[str, Any]:
    """
    Wraps the Analyst Subgraph to prevent message duplication.
    Calculates the DIFF between input state and output state.
    """
    # 1. Capture initial state counts
    initial_messages_count = len(state.get("messages", []))
    initial_logs_count = len(state.get("debug_logs", []))
    
    # 2. Invoke Subgraph
    # We must pass the full state to the subgraph
    result = analyst_graph.invoke(state)
    
    # 3. Calculate Diff (New Items Only)
    final_messages = result.get("messages", [])
    new_messages = final_messages[initial_messages_count:]
    
    final_logs = result.get("debug_logs", [])
    new_logs = final_logs[initial_logs_count:]
    
    print(f"DEBUG [AnalystWrapper] Input msgs: {initial_messages_count}, Output msgs: {len(final_messages)}, New: {len(new_messages)}")
    
    # 4. Return update (Parent graph will append these)
    return {
        "messages": new_messages,
        "debug_logs": new_logs,
        "data_store": result.get("data_store"),
        "resolved_entities": result.get("resolved_entities"),
        "analyst_data": result.get("analyst_data"),
        "final_response": result.get("final_response")
    }

# Define the workflow
workflow = StateGraph(AgentState)

# Add Nodes
workflow.add_node("InputAdapter", input_adapter_node)
workflow.add_node("IntentRouter", intent_router_node)
workflow.add_node("DataAnalyst", data_analyst_wrapper_node) # [UPDATED] Use Wrapper

# Add Edges
# User input → Input Adapter → Intent Router
workflow.add_edge(START, "InputAdapter")
workflow.add_edge("InputAdapter", "IntentRouter")

# Intent Router → Conditional routing
workflow.add_conditional_edges(
    "IntentRouter",
    lambda x: x.get("next", "END"),
    {
        "DataAnalyst": "DataAnalyst", # Points to Subgraph
        "END": END
    }
)

# Data Analyst Subgraph → END
workflow.add_edge("DataAnalyst", END)

# Compile the graph
# Note: Checkpointer is handled automatically by LangGraph API/Studio.
# If running locally in a script, you can compile with a checkpointer there.
app = workflow.compile()