from graph.builder import build_graph


def main():
    """
    Main entry point for the SQL agent.
    """
    # Build the graph
    graph = build_graph()

    # Example of how to run the graph
    query = "查詢昨天綠的國際企業股份有限公司的廣告數據"
    config = {"configurable": {"thread_id": "1"}}
    # The initial state must be provided as a dictionary with the "messages" key
    initial_state = {"messages": [("human", query)]}
    for event in graph.stream(initial_state, config):
        for key, value in event.items():
            print(f"Node: {key}")
            print("---")
            print(value)
        print("\n---\n")


if __name__ == "__main__":
    main()
