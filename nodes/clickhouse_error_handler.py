from schemas.state import AgentState


def clickhouse_error_handler_node(state: AgentState) -> dict:
    """
    Handles errors specifically from the ClickHouseExecutor node.
    It prepares the state for the ClickHouseGenerator to attempt a rewrite.
    """
    error_message = state.get("error_message")

    print(f"ClickHouse Error caught: {error_message}")

    # 這裡回傳的值會更新 State，讓下一個節點 (CH Generator) 讀取
    return {
        "error_message": f"Previous ClickHouse Query Failed. Error: {error_message}. Please fix the SQL."
    }
