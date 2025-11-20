from schemas.state import AgentState
from config.database import db
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text  # Added this import


def sql_executor(state: AgentState) -> dict:
    """
    Executes the SQL query from the state, fetches the data and column names,
    and stores them in the state.
    """
    sql_query = state.get("generated_sql")

    if not sql_query:
        error_message = "SQL Executor: No SQL query to execute."
        print(error_message)
        return {"error_message": error_message, "sql_result": [], "sql_result_columns": []}

    try:
        print(f"Executing SQL: {sql_query}")
        # Use the engine's connect method to get both data and column names
        with db._engine.connect() as connection:
            result_proxy = connection.execute(text(sql_query))  # Wrapped sql_query with text()
            columns = list(result_proxy.keys())
            data = result_proxy.fetchall()

        return {
            "sql_result": data,
            "sql_result_columns": columns,
            "error_message": None
        }
    except SQLAlchemyError as e:
        # Catch specific database errors
        error_message = f"Error executing SQL query: {e}"
        print(error_message)
        # Return empty lists to prevent downstream errors
        return {"error_message": error_message, "sql_result": [], "sql_result_columns": []}
    except Exception as e:
        # Fallback for other unexpected errors
        error_message = f"An unexpected error occurred in SQL executor: {e}"
        print(error_message)
        return {"error_message": error_message, "sql_result": [], "sql_result_columns": []}
