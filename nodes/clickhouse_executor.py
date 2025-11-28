from schemas.state import AgentState
from dotenv import load_dotenv
from config.database import get_clickhouse_db

load_dotenv()


def clickhouse_executor_node(state: AgentState) -> dict:
    """
    Executes the SQL query on ClickHouse and returns the result.
    Supports batch execution for list of SQLs.
    """
    # Prioritize list of SQLs
    clickhouse_sqls = state.get("clickhouse_sqls")
    if not clickhouse_sqls:
        single_sql = state.get("clickhouse_sql")
        if single_sql:
            clickhouse_sqls = [single_sql]
        else:
            return {"clickhouse_result": [], "error_message": "No ClickHouse SQL to execute."}

    try:
        # 從 get_clickhouse_db 函數獲取 Client 實例
        client = get_clickhouse_db()
        
        all_data = []
        column_names = []
        
        total_batches = len(clickhouse_sqls)
        for i, sql in enumerate(clickhouse_sqls):
            print(f"🚀 Executing ClickHouse Batch {i+1}/{total_batches}...")
            
            result = client.query(sql, settings={'max_execution_time': 30}) # Increased timeout slightly for safety

            batch_data = result.result_rows
            
            # Capture column names from first successful query
            if not column_names and result.column_names:
                column_names = result.column_names
                
            # Transform to dicts immediately to match expected output format
            # NOTE: We are extending the list. If the same entity (cmpid) appears in multiple batches,
            # it will appear multiple times in the result list. 
            # The Data Fusion node must handle this aggregation if needed.
            if batch_data:
                # If column_names are not available from result object (sometimes happens in older drivers?), assume consistent schema
                current_cols = result.column_names if result.column_names else column_names
                batch_dicts = [dict(zip(current_cols, row)) for row in batch_data]
                all_data.extend(batch_dicts)
            
            print(f"   Batch {i+1} returned {len(batch_data)} rows.")

        return {"clickhouse_result": all_data, "error_message": None}

    except Exception as e:
        return {"error_message": str(e), "clickhouse_result": []}
