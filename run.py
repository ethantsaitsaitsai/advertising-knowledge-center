"""
AKC Framework 3.0 - Interactive CLI Entry Point
"""
from typing import Dict, Any, List
from langchain_core.messages import HumanMessage
from dotenv import load_dotenv
import uuid

# Load environment variables
load_dotenv()

from agent.graph import app
from agent.state import AgentState

def run_cli():

    # Initialize state with new simplified schema
    state: AgentState = {
        "messages": [],
    }

    thread_id = str(uuid.uuid4())  # Generate a thread ID for the conversation

    print("=== AKC Framework 3.0 - Data Analyst Agent ===")
    print("請輸入您的查詢，或輸入 'exit' 離開\n")

    while True:
        user_input = input("您: ")
        if user_input.lower() in ["exit", "quit"]:
            print("正在離開...")
            break

        # Add user message to state
        state["messages"].append(HumanMessage(content=user_input))

        # Invoke the graph (starts from IntentRouter via START edge)
        final_state = app.invoke(state, {"configurable": {"thread_id": thread_id}})

        # Update state for next iteration
        state = final_state

        # Display agent response
        print("\n--- Agent Response ---")
        if state.get("messages"):
            last_message = state["messages"][-1]
            content = last_message.content

            # Handle different content formats (string or list)
            if isinstance(content, list):
                full_text = ""
                for block in content:
                    if isinstance(block, dict):
                        full_text += block.get("text", "")
                    elif isinstance(block, str):
                        full_text += block
                    else:
                        full_text += str(block)
                print(full_text)
            else:
                print(content)
        else:
            print("沒有訊息回傳。")

        print()  # Empty line for readability


if __name__ == "__main__":
    main()
