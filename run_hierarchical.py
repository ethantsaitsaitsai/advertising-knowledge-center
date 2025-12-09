from langchain_core.messages import HumanMessage
from graph.hierarchical_graph import hierarchical_app
from dotenv import load_dotenv
from schemas.hierarchical_state import AgentState as HierarchicalAgentState
import uuid

def main():
    """
    Main entry point for the hierarchical multi-agent data retrieval system.
    """
    load_dotenv()

    # Initial state for the hierarchical graph
    state: HierarchicalAgentState = {
        "messages": [],
        "next": "", # Supervisor will set this
        "campaign_data": None,
        "performance_data": None,
        # Default empty dicts for filters and analysis_needs,
        # as these are now primarily passed via tool calls but might be useful for Supervisor context
        "extracted_filters": {},
        "analysis_needs": {}
    }

    thread_id = str(uuid.uuid4()) # Generate a single thread_id for the conversation

    while True:
        user_input = input("您: ")
        if user_input.lower() in ["exit", "quit"]:
            print("正在離開...")
            break

        state["messages"].append(HumanMessage(content=user_input))

        # Invoke the hierarchical graph
        final_state = hierarchical_app.invoke(state, {"configurable": {"thread_id": thread_id}})

        state = final_state
        
        print(f"DEBUG [Main] Next Action was: {state.get('next')}")

        print("--- Agent Response ---")
        # Print the last message from the updated state
        if state["messages"]:
            last_message = state["messages"][-1]
            print(last_message.content)
        else:
            print("沒有訊息回傳。")

        # Optionally print the full state for debugging
        # print("\n--- Current State ---")
        # print(state)
        # print("---------------------\n")


if __name__ == "__main__":
    main()
