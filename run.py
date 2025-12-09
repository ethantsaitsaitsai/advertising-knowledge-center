from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from graph.graph import app  # Rename to app
from dotenv import load_dotenv
from schemas.state import AgentState as HierarchicalAgentState # Fixed import
from langsmith import uuid7  # Import uuid7
import uuid # For uuid4

def main():
    """
    Main entry point for the data retrieval agent.
    """
    load_dotenv()

    state: HierarchicalAgentState = {
        "messages": [],
        "next": "IntentAnalyzer", # Explicitly set initial next step, though START edge handles it
        "supervisor_instructions": "",
        "user_intent": None,
        "campaign_data": None,
        "performance_data": None,
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

        # The hierarchical graph always starts at "Supervisor"
        final_state = app.invoke(state, {"configurable": {"thread_id": thread_id}})

        state = final_state

        print("--- Agent Response ---")
        if state["messages"]:
            last_message = state["messages"][-1]
            content = last_message.content
            
            # Debug: Print raw structure to understand why part is missing
            # print(f"DEBUG [Run] Content Type: {type(content)}")
            # if isinstance(content, list):
            #     print(f"DEBUG [Run] List Length: {len(content)}")
            #     for i, item in enumerate(content):
            #         print(f"DEBUG [Run] Item {i} type: {type(item)}")

            if isinstance(content, list):
                full_text = ""
                for i, block in enumerate(content):
                    # Debug:
                    # print(f"DEBUG [Run] Block {i} Type: {type(block)}")
                    # print(f"DEBUG [Run] Block {i} Content: {block}")
                    
                    if isinstance(block, dict):
                        if "text" in block:
                            full_text += block["text"]
                    elif isinstance(block, str):
                        full_text += block
                    else:
                        full_text += str(block)
                print(full_text)
            else:
                print(content)
        else:
            print("沒有訊息回傳。")

if __name__ == "__main__":
    main()
