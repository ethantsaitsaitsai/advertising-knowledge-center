from langchain_core.messages import HumanMessage
from graph.graph import app
from dotenv import load_dotenv
import operator
from schemas.state import AgentState

def main():
    """
    Main entry point for the data retrieval agent.
    """
    load_dotenv()
    
    messages = []
    
    while True:
        user_input = input("您: ")
        if user_input.lower() in ["exit", "quit"]:
            print("正在離開...")
            break

        messages.append(HumanMessage(content=user_input))
        
        inputs: AgentState = {
            "messages": messages,
            "extracted_slots": {},
            "missing_slots": [],
            "generated_sql": None,
            "sql_result": None,
            "error_message": None,
        }
        
        final_state = app.invoke(inputs)

        print("--- Agent Response ---")
        # The final response is always the last message added to the state
        print(final_state["messages"][-1].content)

if __name__ == "__main__":
    main()
