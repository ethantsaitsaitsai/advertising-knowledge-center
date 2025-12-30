from typing import List, Dict, Any, Optional
from langchain_core.tools import tool
from sqlalchemy import text, bindparam
from jinja2 import Environment, FileSystemLoader, select_autoescape
import os
from config.database import get_mysql_db, get_clickhouse_db

# Setup Jinja2 Environment
TEMPLATE_DIR = os.path.join(os.getcwd(), "templates", "sql")
env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(['sql'])
)

def _get_cmp_ids_from_mysql(client_names: List[str], start_date: str, end_date: str) -> List[int]:
    """
    輔助函數：從客戶名稱解析到 Campaign IDs（跨 MySQL → ClickHouse）

    注意：這是備用方案。優先從已有查詢結果中提取 campaign_ids。
    """
    if not client_names:
        return []

    db = get_mysql_db()

    # 簡單的輔助查詢，不需要獨立 template
    query = text("""
        SELECT DISTINCT oc.id
        FROM one_campaigns oc
        JOIN cue_lists cl ON oc.cue_list_id = cl.id
        JOIN clients c ON cl.client_id = c.id
        WHERE (c.company IN :names OR c.advertiser_name IN :names)
          AND oc.start_date <= :end_date
          AND oc.end_date >= :start_date
    """)

    try:
        stmt = query.bindparams(bindparam("names", expanding=True))
        with db._engine.connect() as conn:
            result = conn.execute(stmt, {
                "names": client_names,
                "start_date": start_date,
                "end_date": end_date
            })
            return [row[0] for row in result.fetchall()]

    except Exception as e:
        print(f"⚠️ Error resolving client_names to campaign IDs: {e}")
        import traceback
        traceback.print_exc()
        return []

@tool
def query_performance_metrics(
    start_date: str,
    end_date: str,
    cmp_ids: List[int],
    dimension: str = 'format'
) -> Dict[str, Any]:
    """
    查詢 ClickHouse 成效數據 (Impressions, Clicks, CTR, VTR, ER)。

    Args:
        start_date: 開始日期 (YYYY-MM-DD)
        end_date: 結束日期 (YYYY-MM-DD)
        cmp_ids: 指定 Campaign IDs 列表 (必要，請先透過 query_campaign_basic 取得)
        dimension: 分析維度 ('campaign', 'format', 'daily')
    """
    
    if not cmp_ids:
        return {
            "status": "success",
            "data": [],
            "count": 0,
            "message": "No campaign IDs provided."
        }

    # 1. Render ClickHouse SQL
    try:
        template = env.get_template("performance_metrics.sql")
        # Prepare context
        context = {
            "start_date": start_date,
            "end_date": end_date,
            "dimension": dimension,
            "cmp_ids": cmp_ids,
        }
        rendered_sql = template.render(**context)
    except Exception as e:
        return {"status": "error", "message": f"Template Rendering Error: {e}"}

    # 3. Execute in ClickHouse
    try:
        ch_client = get_clickhouse_db()

        # Jinja2 template already rendered all variables, no parameter binding needed
        # Execute directly with rendered SQL
        result = ch_client.query(rendered_sql)
        
        # Format Results
        columns = result.column_names
        rows = [dict(zip(columns, row)) for row in result.result_rows]
        
        return {
            "status": "success",
            "data": rows,
            "count": len(rows),
            "generated_sql": rendered_sql,
            "columns": columns
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "message": f"ClickHouse Query Error: {e}",
            "generated_sql": rendered_sql
        }
