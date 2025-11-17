from langchain_core.messages import HumanMessage
from graph.builder import build_graph
from schemas.state import GraphState


def main():
    """
    Main entry point for the SQL agent.
    """
    # Build the graph
    graph = build_graph()

    # Initial query
    query = "查詢昨天統一的廣告數據"
    config = {"configurable": {"thread_id": "1"}}
    state = {
        "messages": [HumanMessage(content=query)],
        "query": query, # Ensure the original query is in the initial state
    }

    while True:
        # Stream events from the graph
        events = graph.stream(state, config)
        final_state = None
        for event in events:
            # Print node outputs
            for key, value in event.items():
                print(f"Node: {key}")
                print("---")
                print(value)
            print("\n---\n")
            # The last event is the final state of the graph run
            final_state = event

        # The final state is the output of the last node that ran
        # It's the value of the single key in the event dictionary
        last_node_name = list(final_state.keys())[0]
        final_state_data = final_state[last_node_name]

        # Check if the graph is waiting for human input
        if final_state_data.get("current_stage") == "human_in_the_loop":
            # Get the last message from the agent, which should be the question
            last_message = final_state_data["messages"][-1]
            print("Agent:", last_message.content)

            # Prompt user for input
            user_input = input("Your response: ")
            
            # Append user's response to the messages and carry over the original query
            current_messages = final_state_data["messages"]
            current_messages.append(HumanMessage(content=user_input))
            state = {
                "messages": current_messages,
                "query": state["query"], # Carry over the original query
            }

        else:
            # If not waiting for input, the graph has finished
            print("Graph execution finished.")
            break


if __name__ == "__main__":
    main()
