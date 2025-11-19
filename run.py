from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from graph.graph import app
from dotenv import load_dotenv
from schemas.state import AgentState

def main():
    """
    Main entry point for the data retrieval agent.
    """
    load_dotenv()
    
    state: AgentState = {
        "messages": [],
        "extracted_filters": {},
        "analysis_needs": {},
        "missing_slots": [],
        "ambiguous_terms": [],
        "candidate_values": [],
        "confirmed_entities": [],
        "generated_sql": None,
        "sql_result": None,
        "error_message": None,
        "expecting_user_clarification": False, # Initialize the flag
    }
    
    while True:
        user_input = input("您: ")
        if user_input.lower() in ["exit", "quit"]:
            print("正在離開...")
            break

        state["messages"].append(HumanMessage(content=user_input))
        
        # Determine the entry point dynamically
        entry_point = "slot_manager"
        if state.get("expecting_user_clarification"):
            entry_point = "state_updater"

        # Invoke the graph with the determined entry point
        final_state = app.invoke(state, {"configurable": {"thread_id": "1"}, "recursion_limit": 50, "start": entry_point})
        
        state = final_state

        print("--- Agent Response ---")
        last_message = state["messages"][-1]
        
        # Check if it's a dict or an object
        if isinstance(last_message, dict):
            print(last_message.get("content", ""))
        elif isinstance(last_message, (AIMessage, HumanMessage, BaseMessage)):
            print(last_message.content)

if __name__ == "__main__":
    main()

