from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from graph.builder import graph
import uuid

def handle_clarification_request(clarification_request, messages):
    """Handles the user interaction for a clarification request."""
    print("\nI need some clarification on the following terms:")
    
    user_choices = {}
    questions = clarification_request["questions"]
    
    for q in questions:
        term = q['term']
        options_str = "\n".join([f"{i+1}. {opt['label']} (Column: {opt['column']}, Value: {opt['value']})" for i, opt in enumerate(q['options'])])
        
        while True:
            try:
                choice_idx = int(input(f"\nFor the term '{term}', please choose one of the following options:\n{options_str}\nEnter number: ")) - 1
                if 0 <= choice_idx < len(q['options']):
                    chosen_option = q['options'][choice_idx]
                    user_choices[term] = chosen_option['value']
                    break
                else:
                    print("Invalid choice. Please enter a number from the list.")
            except ValueError:
                print("Invalid input. Please enter a number.")

    # Create a ToolMessage with the user's choices to feed back into the graph
    tool_message = ToolMessage(
        content=f"User has clarified the terms: {user_choices}",
        tool_call_id=clarification_request["id"]
    )
    
    # The new state for resuming the graph
    new_state = {
        "messages": messages + [tool_message],
        "clarified_terms": user_choices
    }
    return new_state

def main():
    """
    Main entry point for the state machine-based SQL agent.
    """
    thread_id = str(uuid.uuid4())
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
            last_message = event["messages"][-1]

            # Check for our custom clarification request
            if "clarification_request" in last_message.additional_kwargs:
                new_state = handle_clarification_request(last_message.additional_kwargs["clarification_request"], event["messages"])
                
                # Resume the graph from the new state
                for resume_event in graph.stream(new_state, config, stream_mode="values"):
                    final_message = resume_event["messages"][-1]
                    if isinstance(final_message, AIMessage) and final_message.content:
                        print(final_message.content, end="", flush=True)
                break # Exit the outer loop after handling clarification and getting final answer
            
            # If it's the final answer from the graph
            elif isinstance(last_message, AIMessage) and last_message.content:
                 print(last_message.content, end="", flush=True)
        
        print() # Newline after agent's full response

if __name__ == "__main__":
    main()
