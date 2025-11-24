from schemas.state import AgentState
from dotenv import load_dotenv
from config.database import get_clickhouse_db

load_dotenv()


def clickhouse_executor_node(state: AgentState) -> dict:
    """
    Executes the SQL query on ClickHouse and returns the result.
    """
    clickhouse_sql = state.get("clickhouse_sql")
    if not clickhouse_sql:
        return {"clickhouse_result": [], "error_message": "No ClickHouse SQL to execute."}

    try:
        # 從 get_clickhouse_db 函數獲取 Client 實例
        client = get_clickhouse_db()

        # Execute the query and get column names and data
        data, columns = client.execute(clickhouse_sql, with_column_types=True)

        # Extract just the column names
        column_names = [col[0] for col in columns]

        # Convert list of tuples to list of dictionaries
        result_dicts = [dict(zip(column_names, row)) for row in data]

        return {"clickhouse_result": result_dicts, "error_message": None}

    except Exception as e:
        return {"error_message": str(e), "clickhouse_result": []}
