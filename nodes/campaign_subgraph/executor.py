import json
from sqlalchemy import text
from config.database import get_mysql_db 
from nodes.campaign_subgraph.state import CampaignSubState

def executor_node(state: CampaignSubState):
    """
    Executes the generated SQL.
    """
    sql = state["generated_sql"]
    print(f"DEBUG [CampaignExecutor] Executing: {sql}")
    
    db = get_mysql_db()
    engine = db._engine 
    
    try:
        with engine.connect() as connection:
            result = connection.execute(text(sql))
            keys = result.keys()
            data = [dict(zip(keys, row)) for row in result.fetchall()]
            
        print(f"DEBUG [CampaignExecutor] Result: {len(data)} rows.")
        
        if data:
            return {
                "campaign_data": {"data": data, "columns": list(keys), "generated_sqls": [sql]},
                "sql_error": None,
                # Add a thought so Router knows we succeeded
                "internal_thoughts": ["Execution: Success with data."]
            }
        else:
            return {
                "campaign_data": {"data": [], "message": "No data found."},
                "sql_error": None,
                "internal_thoughts": ["Execution: Success but 0 rows returned."]
            }

    except Exception as e:
        error_msg = str(e)
        print(f"DEBUG [CampaignExecutor] SQL Error: {error_msg}")
        return {
            "sql_error": error_msg,
            "campaign_data": None,
            "internal_thoughts": [f"Execution: Failed. Error: {error_msg}"]
        }
