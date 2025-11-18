from schemas.state import GraphState
from config.database import db
from langchain_core.messages import ToolMessage

def sql_executor_node(state: GraphState) -> GraphState:
    """
    Executes the validated SQL query and stores the result.
    """
    print("---SQL EXECUTOR---")
    safe_sql = state.get("safe_sql", "")

    if not safe_sql:
        error_message = "No safe SQL query provided for execution."
        print(error_message)
        return {"sql_result": f"Error: {error_message}"}

    try:
        print(f"Executing SQL: {safe_sql}")
        result = db.run(safe_sql)
        print(f"SQL Result: {result}")
        return {"sql_result": str(result)}
    except Exception as e:
        error_message = f"Error executing SQL query: {e}"
        print(error_message)
        # We return the raw error here for the formatter node to handle
        return {"sql_result": f"Execution Error: {error_message}"}