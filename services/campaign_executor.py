from schemas.state import AgentState
from config.database import get_mysql_db
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text


def sql_executor(state: AgentState) -> dict:
    """
    Executes SQL query(s) from the state. Supports batch execution for large datasets.
    Fetches data and column names, merging results from multiple queries if present.
    """
    # Prioritize the list of SQLs (batch mode), fallback to single SQL
    sql_queries = state.get("generated_sqls")
    if not sql_queries:
        single_sql = state.get("generated_sql")
        if single_sql:
            sql_queries = [single_sql]
        else:
            error_message = "SQL Executor: No SQL query to execute."
            print(error_message)
            return {"error_message": error_message, "sql_result": [], "sql_result_columns": []}

    all_data = []
    columns = []
    error_message = None

    try:
        db = get_mysql_db()
        # Use a single connection context for all queries
        with db._engine.connect() as connection:
            total_batches = len(sql_queries)
            for i, query in enumerate(sql_queries):
                print(f"🚀 Executing SQL Batch {i+1}/{total_batches}...")
                # Execute
                result_proxy = connection.execute(text(query))
                
                # Capture columns from the first successful query
                if not columns:
                    columns = list(result_proxy.keys())
                
                # Fetch and extend data
                batch_data = result_proxy.fetchall()
                all_data.extend(batch_data)
                result_proxy.close() # Explicitly close to prevent "Commands out of sync"
                print(f"   Batch {i+1} returned {len(batch_data)} rows.")

        print(f"✅ All batches completed. Total rows fetched: {len(all_data)}")
        
        return {
            "sql_result": all_data,
            "sql_result_columns": columns,
            "error_message": None
        }

    except SQLAlchemyError as e:
        error_message = f"Error executing SQL query: {e}"
        print(f"❌ {error_message}")
        return {"error_message": error_message, "sql_result": [], "sql_result_columns": []}
    except Exception as e:
        error_message = f"An unexpected error occurred in SQL executor: {e}"
        print(f"❌ {error_message}")
        return {"error_message": error_message, "sql_result": [], "sql_result_columns": []}