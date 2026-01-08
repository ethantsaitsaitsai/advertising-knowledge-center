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
def query_format_benchmark(
    start_date: str,
    end_date: str,
    cmp_ids: Optional[List[int]] = None,
    format_ids: Optional[List[int]] = None
) -> Dict[str, Any]:
    """
    查詢【格式成效基準】(Benchmark) 與排名。
    適用於：
    1. "所有格式" 的 CTR/VTR 排名。
    2. "汽車產業" (透過 cmp_ids 篩選) 的格式成效平均值。
    3. "Mobile Banner" (透過 format_ids 篩選) 的全站平均成效。
    
    Args:
        start_date: 開始日期
        end_date: 結束日期
        cmp_ids: Campaign IDs (用於篩選特定產業或客戶群的 Campaign)
        format_ids: 格式 IDs (用於篩選特定格式)
    """
    
    # Render ClickHouse SQL
    try:
        template = env.get_template("format_benchmark.sql")
        context = {
            "start_date": start_date,
            "end_date": end_date,
            "cmp_ids": cmp_ids,
            "format_ids": format_ids
        }
        rendered_sql = template.render(**context)
    except Exception as e:
        return {"status": "error", "message": f"Template Rendering Error: {e}"}

    # Execute
    try:
        ch_client = get_clickhouse_db()
        result = ch_client.query(rendered_sql)
        
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
            "message": f"ClickHouse Benchmark Query Error: {e}",
            "generated_sql": rendered_sql
        }

@tool
def query_unified_performance(
    start_date: str,
    end_date: str,
    group_by: List[str],
    plaids: Optional[List[int]] = None,
    cmpids: Optional[List[int]] = None,
    product_line_ids: Optional[List[int]] = None,
    ad_format_type_ids: Optional[List[int]] = None,
    one_categories: Optional[List[str]] = None,
    one_sub_categories: Optional[List[str]] = None,
    limit: int = 100
) -> Dict[str, Any]:
    """
    【核心成效查詢工具】從 ClickHouse 查詢成效數據，使用 ID 進行精準過濾。
    
    ⚠️ 重要: 此工具不再接受 client_ids。若要查特定客戶成效，必須先呼叫 `query_media_placements` 取得 plaids。
    
    Args:
        start_date: 開始日期 (YYYY-MM-DD)
        end_date: 結束日期 (YYYY-MM-DD)
        group_by: 分析維度，支援：
                 ['client_company', 'product_line', 'one_category', 'one_sub_category',
                  'ad_format_type', 'campaign_name', 'client_id', 'product_line_id', 
                  'ad_format_type_id', 'plaid', 'cmpid']
        plaids: Placement IDs (強烈建議使用此欄位過濾)
        cmpids: Campaign IDs (ClickHouse cmpid)
        product_line_ids: Product Line IDs
        ad_format_type_ids: Ad Format Type IDs
        one_categories: 產業類別 (String)
        one_sub_categories: 子產業類別 (String)
    """
    
    # 安全性驗證
    ALLOWED_DIMS = {
        'client_company', 'product_line', 'one_category', 'one_sub_category',
        'ad_format_type', 'campaign_name', 'client_id', 'product_line_id',
        'ad_format_type_id', 'plaid', 'cmpid', 'ad_type', 'day_local'
    }
    
    valid_dims = [d for d in group_by if d in ALLOWED_DIMS]
    if not valid_dims:
        valid_dims = ['client_company'] 
        
    try:
        template = env.get_template("unified_performance.sql")
        context = {
            "start_date": start_date,
            "end_date": end_date,
            "dimensions": valid_dims,
            "plaids": plaids,
            "cmpids": cmpids,
            "product_line_ids": product_line_ids,
            "ad_format_type_ids": ad_format_type_ids,
            "one_categories": one_categories,
            "one_sub_categories": one_sub_categories,
            "limit": limit
        }
        rendered_sql = template.render(**context)
    except Exception as e:
        return {"status": "error", "message": f"Template Rendering Error: {e}"}

    try:
        ch_client = get_clickhouse_db()
        result = ch_client.query(rendered_sql)
        
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
            "message": f"Unified Performance Query Error: {e}",
            "generated_sql": rendered_sql
        }

@tool
def query_unified_dimensions(
    start_date: str,
    end_date: str,
    dimensions: List[str],
    plaids: Optional[List[int]] = None,
    cmpids: Optional[List[int]] = None,
    client_ids: Optional[List[int]] = None,
    product_line_ids: Optional[List[int]] = None,
    ad_format_type_ids: Optional[List[int]] = None,
    one_categories: Optional[List[str]] = None,
    one_sub_categories: Optional[List[str]] = None,
    limit: int = 100
) -> Dict[str, Any]:
    """
    【維度探索工具】查詢有哪些產品線、格式、版位或分類 (不含成效數據)。
    適用於：
    1. "Nike 有哪些產品線？"
    2. "汽車產業投了哪些格式？"
    3. "列出所有使用過的版位"
    
    Args:
        start_date: 開始日期 (YYYY-MM-DD)
        end_date: 結束日期 (YYYY-MM-DD)
        dimensions: 欲查詢的維度欄位，支援：
                   ['client_company', 'product_line', 'one_category', 'one_sub_category',
                    'ad_format_type', 'campaign_name', 'publisher', 'placement_name',
                    'client_id', 'product_line_id', 'ad_format_type_id']
        (其他過濾參數同 unified_performance)
    """
    
    # 安全性驗證
    ALLOWED_DIMS = {
        'client_company', 'product_line', 'one_category', 'one_sub_category',
        'ad_format_type', 'campaign_name', 'publisher', 'placement_name',
        'client_id', 'product_line_id', 'ad_format_type_id', 'plaid', 'cmpid', 
        'ad_type', 'ad_format_type'
    }
    
    valid_dims = [d for d in dimensions if d in ALLOWED_DIMS]
    if not valid_dims:
        return {"status": "error", "message": "No valid dimensions provided."}
        
    try:
        template = env.get_template("unified_dimensions.sql")
        context = {
            "start_date": start_date,
            "end_date": end_date,
            "dimensions": valid_dims,
            "plaids": plaids,
            "cmpids": cmpids,
            "client_ids": client_ids,
            "product_line_ids": product_line_ids,
            "ad_format_type_ids": ad_format_type_ids,
            "one_categories": one_categories,
            "one_sub_categories": one_sub_categories,
            "limit": limit
        }
        rendered_sql = template.render(**context)
    except Exception as e:
        return {"status": "error", "message": f"Template Rendering Error: {e}"}

    try:
        ch_client = get_clickhouse_db()
        result = ch_client.query(rendered_sql)
        
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
            "message": f"Unified Dimensions Query Error: {e}",
            "generated_sql": rendered_sql
        }
