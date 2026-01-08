from typing import List, Dict, Any, Optional
from langchain_core.tools import tool
from sqlalchemy import text, bindparam
from jinja2 import Environment, FileSystemLoader, select_autoescape
import os
from config.database import get_mysql_db

# 設定 Jinja2 環境
TEMPLATE_DIR = os.path.join(os.getcwd(), "templates", "sql")
env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(['sql'])
)

def _render_and_execute_mysql(template_name: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """
    內部共用函數：渲染並執行 MySQL 模板
    """
    db = get_mysql_db()
    
    # 1. 載入與渲染
    try:
        template = env.get_template(template_name)
        rendered_sql = template.render(**context)
    except Exception as e:
        return {"status": "error", "message": f"Template Error: {e}"}

    # 2. 準備參數 (處理 List -> Tuple 展開)
    stmt = text(rendered_sql)
    db_params = {}
    
    for k, v in context.items():
        # 只有在 SQL 中有出現該參數時才綁定
        if f":{k}" in rendered_sql:
            if isinstance(v, (list, tuple)):
                stmt = stmt.bindparams(bindparam(k, expanding=True))
                db_params[k] = list(v)
            else:
                db_params[k] = v

    # 3. 執行
    try:
        with db._engine.connect() as connection:
            result = connection.execute(stmt, db_params)
            columns = result.keys()
            rows = [dict(zip(columns, row)) for row in result.fetchall()]
            
            return {
                "status": "success",
                "data": rows,
                "count": len(rows),
                "generated_sql": rendered_sql
            }
    except Exception as e:
        return {
            "status": "error", 
            "message": str(e), 
            "generated_sql": rendered_sql
        }

@tool
def id_finder(
    start_date: str,
    end_date: str,
    client_ids: Optional[List[int]] = None,
    agency_ids: Optional[List[int]] = None,
    ad_format_type_ids: Optional[List[int]] = None,
    industry_ids: Optional[List[int]] = None,
    sub_industry_ids: Optional[List[int]] = None,
    product_line_ids: Optional[List[int]] = None,
    limit: int = 5000
) -> Dict[str, Any]:
    """
    【核心工具】ID 搜尋器。
    根據時間、客戶、格式等條件，找出所有相關的 IDs (CueList, Campaign, Plaid)。
    這些 IDs 是後續查詢預算、執行、成效的必要輸入。
    
    Args:
        start_date: 開始日期 (Required)
        end_date: 結束日期 (Required)
        client_ids: 客戶 ID 列表
        agency_ids: 代理商 ID 列表
        ad_format_type_ids: 廣告格式 ID 列表
        industry_ids: 產業 ID 列表
        sub_industry_ids: 子產業 ID 列表
        product_line_ids: 產品線 ID 列表
    """
    context = {
        "start_date": start_date,
        "end_date": end_date,
        "client_ids": client_ids,
        "agency_ids": agency_ids,
        "ad_format_type_ids": ad_format_type_ids,
        "industry_ids": industry_ids,
        "sub_industry_ids": sub_industry_ids,
        "product_line_ids": product_line_ids,
        "limit": limit
    }
    return _render_and_execute_mysql("id_finder.sql", context)

@tool
def query_campaign_basic(
    campaign_ids: List[int]
) -> Dict[str, Any]:
    """
    查詢活動基本資訊 (Metadata)，包含名稱、日期、客戶與 agency。
    並附帶該活動旗下的所有 Plaid 列表。
    
    Args:
        campaign_ids: Campaign IDs 列表 (必填)
    """
    context = {
        "campaign_ids": campaign_ids
    }
    return _render_and_execute_mysql("campaign_basic.sql", context)

@tool
def query_investment_budget(
    cue_list_ids: List[int]
) -> Dict[str, Any]:
    """
    查詢「進單/投資」金額 (Investment Budget)。
    
    Args:
        cue_list_ids: Cue List IDs 列表 (必填，來自 id_finder)
    """
    context = {
        "cue_list_ids": cue_list_ids
    }
    return _render_and_execute_mysql("investment_budget.sql", context)

@tool
def query_execution_budget(
    plaids: List[int]
) -> Dict[str, Any]:
    """
    查詢「執行/認列」金額 (Execution Budget)。
    
    Args:
        plaids: Pre-Campaign IDs 列表 (必填，來自 id_finder)
    """
    context = {
        "plaids": plaids
    }
    return _render_and_execute_mysql("execution_budget.sql", context)

@tool
def query_targeting_segments(
    plaids: List[int]
) -> Dict[str, Any]:
    """
    查詢活動的「數據鎖定」或「受眾標籤」設定 (Targeting Segments)。
    
    Args:
        plaids: Pre-Campaign IDs 列表 (必填，來自 id_finder)
    """
    context = {
        "plaids": plaids
    }
    return _render_and_execute_mysql("targeting_segments.sql", context)

@tool
def execute_sql_template(
    template_name: str,
    campaign_ids: Optional[List[int]] = None,
    client_names: Optional[List[str]] = None,
    agency_ids: Optional[List[int]] = None,
    industry_ids: Optional[List[int]] = None,
    sub_industry_ids: Optional[List[int]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 1000
) -> Dict[str, Any]:
    """
    [進階] 通用 SQL 模板執行器。只有在上述專用工具不適用時才使用。
    """
    context = {
        "campaign_ids": campaign_ids,
        "client_names": client_names,
        "agency_ids": agency_ids,
        "industry_ids": industry_ids,
        "sub_industry_ids": sub_industry_ids,
        "start_date": start_date,
        "end_date": end_date,
        "limit": limit
    }
    return _render_and_execute_mysql(template_name, context)
