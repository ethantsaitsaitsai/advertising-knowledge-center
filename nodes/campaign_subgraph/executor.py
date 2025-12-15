import json
import time
from sqlalchemy import text
from config.database import get_mysql_db
from nodes.campaign_subgraph.state import CampaignSubState

def executor_node(state: CampaignSubState):
    """
    Executes the generated SQL with performance monitoring.
    Includes EXPLAIN analysis for slow queries.
    """
    sql = state["generated_sql"]
    print(f"DEBUG [CampaignExecutor] Executing: {sql[:200]}...")

    db = get_mysql_db()
    engine = db._engine

    try:
        with engine.connect() as connection:
            # Record execution time
            start_time = time.time()
            result = connection.execute(text(sql))
            keys = result.keys()
            data = [dict(zip(keys, row)) for row in result.fetchall()]
            elapsed_time = time.time() - start_time

            print(f"DEBUG [CampaignExecutor] Result: {len(data)} rows in {elapsed_time:.2f}s.")

            # If query took > 5 seconds, run EXPLAIN for debugging
            explain_result = None
            if elapsed_time > 5:
                print(f"DEBUG [CampaignExecutor] Query took {elapsed_time:.2f}s (slow). Running EXPLAIN...")
                try:
                    explain_sql = f"EXPLAIN FORMAT=JSON {sql}"
                    explain_res = connection.execute(text(explain_sql))
                    explain_data = explain_res.fetchall()
                    if explain_data:
                        explain_result = explain_data[0][0]
                        print(f"DEBUG [CampaignExecutor] EXPLAIN: {str(explain_result)[:500]}...")
                except Exception as e:
                    print(f"DEBUG [CampaignExecutor] EXPLAIN failed: {e}")

            # Return result with performance metadata
            campaign_data = {
                "data": data,
                "columns": list(keys),
                "generated_sqls": [sql],
                "execution_time_seconds": elapsed_time,
                "row_count": len(data)
            }

            if explain_result:
                campaign_data["explain_analysis"] = str(explain_result)

            if data:
                return {
                    "campaign_data": campaign_data,
                    "sql_error": None,
                    "internal_thoughts": [f"Execution: Success with {len(data)} rows in {elapsed_time:.2f}s."]
                }
            else:
                return {
                    "campaign_data": campaign_data,
                    "sql_error": None,
                    "internal_thoughts": [f"Execution: Success but 0 rows returned in {elapsed_time:.2f}s."]
                }

    except Exception as e:
        error_msg = str(e)
        print(f"DEBUG [CampaignExecutor] SQL Error: {error_msg}")
        return {
            "sql_error": error_msg,
            "campaign_data": None,
            "internal_thoughts": [f"Execution: Failed. Error: {error_msg}"]
        }
