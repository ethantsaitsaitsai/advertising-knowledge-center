from schemas.state import AgentState
from config.database import db

def sql_executor(state: AgentState) -> dict:
    """
    Executes the SQL query from the state and stores the result or an error.
    """
    sql_query = state.get("generated_sql")

    if not sql_query:
        error_message = "No SQL query to execute."
        print(error_message)
        return {"error_message": error_message}

    try:
        print(f"Executing SQL: {sql_query}")
        result = db.run(sql_query)
        print(f"SQL result: {result}")
        return {"sql_result": str(result), "error_message": None}
    except Exception as e:
        error_message = f"Error executing SQL query: {e}"
        print(error_message)
        return {"error_message": error_message, "sql_result": None}