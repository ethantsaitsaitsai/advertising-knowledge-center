from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from graph.graph import hierarchical_app as app # Rename to app
from dotenv import load_dotenv
from schemas.hierarchical_state import AgentState as HierarchicalAgentState # Use hierarchical state
from langsmith import uuid7  # Import uuid7
import uuid # For uuid4

def main():
    """
    Main entry point for the data retrieval agent.
    """
    load_dotenv()

    state: HierarchicalAgentState = {
        "messages": [],
        "next": "", # Supervisor will set this
        "supervisor_instructions": "", # Supervisor will set this
        "user_intent": None, # Intent Analyzer will set this
        "campaign_data": None,
        "performance_data": None,
        "extracted_filters": {}, # For Supervisor context
        "analysis_needs": {}     # For Supervisor context
    }

    thread_id = str(uuid.uuid4()) # Generate a single thread_id for the conversation

    while True:
        user_input = input("您: ")
        if user_input.lower() in ["exit", "quit"]:
            print("正在離開...")
            break

        state["messages"].append(HumanMessage(content=user_input))

        # The hierarchical graph always starts at "Supervisor"
        final_state = app.invoke(state, {"configurable": {"thread_id": thread_id}})

        state = final_state

        print("--- Agent Response ---")
        # Print the last message from the updated state
        if state["messages"]:
            last_message = state["messages"][-1]
            print(last_message.content)
        else:
            print("沒有訊息回傳。")

if __name__ == "__main__":
    main()
