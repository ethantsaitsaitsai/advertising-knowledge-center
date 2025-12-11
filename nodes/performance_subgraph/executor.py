from nodes.performance_subgraph.state import PerformanceSubState
from tools.performance_tool import execute_clickhouse_query
import re

def performance_executor_node(state: PerformanceSubState):
    """
    Executes the generated ClickHouse SQL.
    """
    sql = state.get("generated_sql")
    if not sql:
        return {"sql_error": "No SQL generated."}
        
    # Clean Markdown
    clean_sql = re.sub(r"```sql\s*(.*?)\s*```", r"\1", sql, flags=re.DOTALL | re.IGNORECASE).strip()
    if clean_sql == sql: # Try generic block if sql specific one failed
        clean_sql = re.sub(r"```\s*(.*?)\s*```", r"\1", sql, flags=re.DOTALL).strip()
        
    print(f"DEBUG [PerfExecutor] Executing: {clean_sql[:100]}...")
    
    try:
        results = execute_clickhouse_query(clean_sql)
        count = len(results)
        print(f"DEBUG [PerfExecutor] Result: {count} rows.")
        
        return {
            "final_dataframe": results,
            "sql_error": None # Clear error on success
        }
    except Exception as e:
        error_msg = str(e)
        print(f"DEBUG [PerfExecutor] SQL Error: {error_msg}")
        return {
            "sql_error": error_msg,
            "final_dataframe": None
        }