import sys
import os
import sys

# Add project root to sys.path to allow imports
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from jinja2 import Environment, FileSystemLoader, select_autoescape
from config.database import get_clickhouse_db, get_mysql_db
from sqlalchemy import text

def test_unified_performance():
    # Setup Jinja2
    TEMPLATE_DIR = os.path.join(project_root, "templates", "sql")
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(['sql'])
    )
    
    template = env.get_template("unified_performance.sql")
    
    print("\n=== Test 1: Query by Client ID (1453) ===")
    
    context = {
        "dimensions": ["client_company", "product_line", "ad_format_type"],
        "start_date": "2025-10-01",
        "end_date": "2026-01-06",
        "client_ids": [1453],  # EasyCard
        "limit": 10
    }
    
    rendered_sql = template.render(**context)
    print("\n--- Generated SQL ---")
    print(rendered_sql)
    print("---------------------")
    
    try:
        ch_client = get_clickhouse_db()
        result = ch_client.query(rendered_sql)
        
        print(f"\n✅ Query Executed Successfully")
        print(f"Columns: {result.column_names}")
        print(f"Row Count: {len(result.result_rows)}")
        
        if result.result_rows:
            print("First Row Sample:")
            print(dict(zip(result.column_names, result.result_rows[0])))
        else:
            print("⚠️ Warning: No rows returned. Check date range or ID.")
            
    except Exception as e:
        print(f"\n❌ Query Failed: {e}")

    # --- Test 2: Fallback with Campaign IDs ---
    # First, fetch campaigns from MySQL for this client to be sure
    print("\n\n=== Pre-Check: Fetching Campaigns from MySQL ===")
    try:
        mysql_db = get_mysql_db()
        query = text("""
            SELECT oc.id, oc.name, oc.start_date, oc.end_date 
            FROM one_campaigns oc
            JOIN cue_lists cl ON oc.cue_list_id = cl.id
            WHERE cl.client_id = 1453
            AND oc.start_date <= '2026-01-06' 
            AND oc.end_date >= '2025-10-01'
            LIMIT 5
        """)
        
        campaigns = []
        with mysql_db._engine.connect() as conn:
            res = conn.execute(query)
            campaigns = [row for row in res]
            
        print(f"Found {len(campaigns)} active campaigns in MySQL:")
        cmp_ids = []
        for c in campaigns:
            print(f" - [{c[0]}] {c[1]} ({c[2]} ~ {c[3]})")
            cmp_ids.append(c[0])
            
        if cmp_ids:
            print(f"\n=== Test 2: Query by Campaign IDs ({cmp_ids}) ===")
            context_cmp = {
                "dimensions": ["campaign_name", "ad_format_type"],
                "start_date": "2025-10-01",
                "end_date": "2026-01-06",
                "cmpids": cmp_ids,
                "limit": 10
            }
            rendered_sql_cmp = template.render(**context_cmp)
            
            print("\n--- Generated SQL (Campaign Filter) ---")
            print(rendered_sql_cmp)
            
            result_cmp = ch_client.query(rendered_sql_cmp)
            print(f"\nRow Count: {len(result_cmp.result_rows)}")
            if result_cmp.result_rows:
                print(dict(zip(result_cmp.column_names, result_cmp.result_rows[0])))
        else:
            print("⚠️ No campaigns found in MySQL for this period. That explains why ClickHouse is empty.")

    except Exception as e:
        print(f"❌ MySQL Check Failed: {e}")

if __name__ == "__main__":
    test_unified_performance()
