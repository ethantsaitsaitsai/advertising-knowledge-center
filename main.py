from langchain_core.messages import HumanMessage, AIMessage
from langgraph.types import Command
from graph.builder import graph
import os

def main():
    """
    Main entry point for the ReAct-based SQL agent with Human-in-the-Loop.
    """
    thread_id = "user_123"
    config = {"configurable": {"thread_id": thread_id}}

    while True:
        user_input = input("You: ")
        if user_input.lower() in ["exit", "quit"]:
            print("Exiting...")
            break

        inputs = {"messages": [HumanMessage(content=user_input)]}

        print("Agent: ", end="", flush=True)
        
        # Stream events from the graph
        for event in graph.stream(inputs, config, stream_mode="values"):
            if "__interrupt__" in event:
                # Handle the interruption for human approval
                interrupt = event["__interrupt__"][0]
                print("\nINTERRUPTED: SQL Query execution pending approval")
                for request in interrupt.value["action_requests"]:
                    print("Tool:", request["tool"])
                    print("Args:", request["args"])
                
                approval = input("Approve? (y/n): ").strip().lower()
                
                # Create a command to resume the graph
                resume_command = Command(resume={"decisions": [{"type": "approve" if approval == 'y' else "reject"}]})
                
                # Stream the resumed execution
                for resume_event in graph.stream(resume_command, config, stream_mode="values"):
                    if "messages" in resume_event:
                        new_message = resume_event["messages"][-1]
                        if isinstance(new_message, AIMessage) and new_message.content:
                            print(new_message.content, end="", flush=True)
                break # Exit the inner loop after handling the interrupt
            
            elif "messages" in event:
                new_message = event["messages"][-1]
                if isinstance(new_message, AIMessage) and new_message.content:
                    print(new_message.content, end="", flush=True)
        
        print() # Newline after agent's full response

if __name__ == "__main__":
    main()
