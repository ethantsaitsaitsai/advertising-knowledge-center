import os
import sys
import json
from datetime import datetime, timedelta

# Add project root to path
sys.path.append(os.getcwd())

from config.database import get_mysql_db, get_clickhouse_db
from sqlalchemy import text
from jinja2 import Environment, FileSystemLoader, select_autoescape

# Setup Jinja2 Environment
TEMPLATE_DIR = os.path.join(os.getcwd(), "templates", "sql")
env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(['sql'])
)

def test_industry_format_budget():
    print("\n=== Testing industry_format_budget.sql (MySQL) ===")
    
    # 模擬情境：查詢過去半年，客戶 ID=1 (假設) 或 產業 ID=1 (假設) 的資料
    # 先查一個存在的產業 ID
    db = get_mysql_db()
    with db._engine.connect() as conn:
        res = conn.execute(text("SELECT id, name FROM pre_campaign_categories LIMIT 1"))
        cat = res.fetchone()
        cat_id = cat[0] if cat else 1
        cat_name = cat[1] if cat else "Unknown"
        print(f"Using Industry: {cat_name} (ID: {cat_id})")

    start_date = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")
    end_date = datetime.now().strftime("%Y-%m-%d")

    context = {
        "industry_ids": [cat_id],
        "sub_industry_ids": None,
        "client_ids": None,
        "start_date": start_date,
        "end_date": end_date,
        "limit": 5
    }

    try:
        template = env.get_template("industry_format_budget.sql")
        rendered_sql = template.render(**context)
        print(f"Generated SQL (First 200 chars): {rendered_sql[:200]}...")

        # 執行
        with db._engine.connect() as conn:
            # 處理參數綁定 (模擬 tool 邏輯)
            stmt = text(rendered_sql)
            # 因為 template 已經 render 了數值，這裡直接執行即可，除非有其他綁定
            result = conn.execute(stmt)
            columns = result.keys()
            rows = [dict(zip(columns, row)) for row in result.fetchall()]
            
            print(f"Result Count: {len(rows)}")
            if rows:
                print("Top Result:")
                print(json.dumps(rows[0], indent=2, default=str))
            else:
                print("No data found.")

    except Exception as e:
        print(f"Error: {e}")

def test_format_benchmark():
    print("\n=== Testing format_benchmark.sql (ClickHouse) ===")
    
    start_date = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")
    end_date = datetime.now().strftime("%Y-%m-%d")

    # 模擬情境：全站格式排名 (不篩選 cmp_ids)
    context = {
        "start_date": start_date,
        "end_date": end_date,
        "cmp_ids": None,
        "format_ids": None
    }

    try:
        template = env.get_template("format_benchmark.sql")
        rendered_sql = template.render(**context)
        print(f"Generated SQL (First 200 chars): {rendered_sql[:200]}...")

        # 執行
        ch_client = get_clickhouse_db()
        result = ch_client.query(rendered_sql)
        
        columns = result.column_names
        rows = [dict(zip(columns, row)) for row in result.result_rows]
        
        print(f"Result Count: {len(rows)}")
        if rows:
            print("Top Result:")
            print(json.dumps(rows[0], indent=2, default=str))
        else:
            print("No data found.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_industry_format_budget()
    test_format_benchmark()
