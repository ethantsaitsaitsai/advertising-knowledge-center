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
    client_names: Optional[List[str]] = None,
    dimension: str = 'format',
    cmp_ids: Optional[List[int]] = None
) -> Dict[str, Any]:
    """
    查詢 ClickHouse 成效數據 (Impressions, Clicks, CTR, VTR, ER)。
    支援自動將客戶名稱 (client_names) 轉換為 Campaign IDs。

    Args:
        start_date: 開始日期 (YYYY-MM-DD)
        end_date: 結束日期 (YYYY-MM-DD)
        client_names: 客戶名稱列表 (選填, 系統會自動去 MySQL 查找對應的 Campaign IDs)
        dimension: 分析維度 ('campaign', 'format', 'daily')
        cmp_ids: 直接指定 Campaign IDs (選填, 若有 client_names 則會自動覆蓋/合併)
    """
    
    # 1. Resolve Client Names to Campaign IDs if needed
    target_cmp_ids = cmp_ids or []
    if client_names:
        resolved_ids = _get_cmp_ids_from_mysql(client_names, start_date, end_date)
        if resolved_ids:
            # Combine distinct IDs
            target_cmp_ids = list(set(target_cmp_ids + resolved_ids))
            print(f"DEBUG [PerformanceTool] Resolved {len(resolved_ids)} campaign IDs for clients: {client_names}")
        else:
             print(f"DEBUG [PerformanceTool] No campaigns found for clients: {client_names} in range")
             # If client names were provided but no campaigns found, we should probably return empty or handle gracefully
             # However, passing empty list to IN clause might break SQL or return all if not handled.
             # The template uses {% if cmp_ids %}, so empty list means "no filter". 
             # But here "no filter" is WRONG (it would query EVERYTHING).
             # We must force a filter that returns nothing if resolution failed but client filter was requested.
             return {
                 "status": "success",
                 "data": [],
                 "count": 0,
                 "message": f"No campaigns found for clients {client_names} in the specified date range."
             }

    # 2. Render ClickHouse SQL
    try:
        template = env.get_template("performance_metrics.sql")
        # Prepare context
        context = {
            "start_date": start_date,
            "end_date": end_date,
            "dimension": dimension,
            "cmp_ids": target_cmp_ids,
            # format_ids could be supported in future
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
