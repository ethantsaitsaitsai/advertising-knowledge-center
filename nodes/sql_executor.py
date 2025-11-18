from schemas.state import GraphState
from langchain_core.messages import AIMessage
from tools.database_tools import sql_db_query_tool  # Import the specific tool


def sql_executor_node(state: GraphState) -> GraphState:
    """
    Executes the validated SQL query using the sql_db_query_tool and stores the result.
    """
    print("---SQL EXECUTOR---")
    safe_sql = state.get("safe_sql", "")
    messages = state["messages"]

    if not safe_sql:
        error_message = "No safe SQL query provided for execution."
        print(error_message)
        messages.append(AIMessage(content=f"Error: {error_message}"))
        return {"sql_result": f"Error: {error_message}", "messages": messages}

    try:
        print(f"Executing SQL: {safe_sql}")
        # Use the sql_db_query_tool to execute the safe SQL
        # The tool expects a dictionary with a 'query' key
        tool_result = sql_db_query_tool.invoke({"query": safe_sql})
        print(f"SQL Result: {tool_result}")
        return {"sql_result": str(tool_result), "messages": messages}
    except Exception as e:
        error_message = f"Error executing SQL query: {e}"
        print(error_message)
        messages.append(AIMessage(content=f"Error: {error_message}"))
        return {"sql_result": f"Error: {error_message}", "messages": messages}
