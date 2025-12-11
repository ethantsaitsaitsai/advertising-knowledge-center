
from typing import Dict, Any, List
from langchain_core.tools import tool
from config.database import get_clickhouse_db

def execute_clickhouse_query(sql: str) -> List[Dict[str, Any]]:
    """
    Executes a raw SQL query on ClickHouse and returns a list of dictionaries.
    """
    try:
        client = get_clickhouse_db()
        result = client.query(sql, settings={'max_execution_time': 30})
        
        column_names = result.column_names
        rows = result.result_rows
        
        if not rows:
            return []
            
        return [dict(zip(column_names, row)) for row in rows]
        
    except Exception as e:
        print(f"ClickHouse Execution Error: {e}")
        raise e

@tool
def query_performance_data(
    sql: str
) -> List[Dict[str, Any]]:
    """
    Executes a SQL query on ClickHouse.
    Args:
        sql: The SQL query string.
    """
    return execute_clickhouse_query(sql)
