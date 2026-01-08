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
def query_campaign_basic(
    client_names: Optional[List[str]] = None,
    client_ids: Optional[List[int]] = None,
    industry_ids: Optional[List[int]] = None,
    sub_industry_ids: Optional[List[int]] = None,
    campaign_ids: Optional[List[int]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    查詢活動基本資訊 (Basic Info)，包含 Campaign ID, 名稱, 日期, 總預算。
    
    Args:
        client_names: 客戶/廣告主名稱列表 (例如 ['悠遊卡'])
        client_ids: 客戶 ID 列表 (精準搜尋用)
        industry_ids: 產業類別 (Category) ID 列表
        sub_industry_ids: 產業子類別 (Sub-Category) ID 列表
        campaign_ids: 直接指定 Campaign IDs (若已知)
        start_date: 開始日期過濾 (YYYY-MM-DD)
        end_date: 結束日期過濾 (YYYY-MM-DD)
    """
    context = {
        "client_names": client_names,
        "client_ids": client_ids,
        "industry_ids": industry_ids,
        "sub_industry_ids": sub_industry_ids,
        "campaign_ids": campaign_ids,
        "start_date": start_date,
        "end_date": end_date
    }
    return _render_and_execute_mysql("campaign_basic.sql", context)

@tool
def query_budget_details(
    campaign_ids: List[int]
) -> Dict[str, Any]:
    """
    查詢詳細的預算摘要 (Budget Details)，包含合約預算、進單金額與執行金額的比較。
    
    ⚠️ 注意: 此工具必須提供 `campaign_ids`。若只知客戶名稱，請先呼叫 `query_campaign_basic` 取得 IDs。
    
    Args:
        campaign_ids: Campaign IDs 列表 (必填)
    """
    context = {
        "campaign_ids": campaign_ids
    }
    return _render_and_execute_mysql("budget_details.sql", context)

@tool
def query_investment_budget(
    client_names: Optional[List[str]] = None,
    client_ids: Optional[List[int]] = None,
    agency_ids: Optional[List[int]] = None,
    industry_ids: Optional[List[int]] = None,
    sub_industry_ids: Optional[List[int]] = None,
    campaign_ids: Optional[List[int]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 5000
) -> Dict[str, Any]:
    """
    查詢「進單/投資」金額 (Investment Budget)，包含各格式的單價、預算分配。
    適用於查詢「預算」、「進單」相關問題。
    
    Args:
        client_names: 客戶名稱列表
        client_ids: 客戶 ID 列表
        agency_ids: 代理商 ID 列表
        industry_ids: 產業類別 (Category) ID 列表
        sub_industry_ids: 產業子類別 (Sub-Category) ID 列表
        campaign_ids: Campaign IDs 列表
        start_date: 開始日期
        end_date: 結束日期
        limit: 返回筆數限制 (預設 5000，排名分析時建議設為 500-1000)
    """
    context = {
        "client_names": client_names,
        "client_ids": client_ids,
        "agency_ids": agency_ids,
        "industry_ids": industry_ids,
        "sub_industry_ids": sub_industry_ids,
        "campaign_ids": campaign_ids,
        "start_date": start_date,
        "end_date": end_date,
        "limit": limit
    }
    return _render_and_execute_mysql("investment_budget.sql", context)

@tool
def query_execution_budget(
    client_names: Optional[List[str]] = None,
    client_ids: Optional[List[int]] = None,
    agency_ids: Optional[List[int]] = None,
    industry_ids: Optional[List[int]] = None,
    sub_industry_ids: Optional[List[int]] = None,
    campaign_ids: Optional[List[int]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 5000
) -> Dict[str, Any]:
    """
    查詢「執行/認列」金額 (Execution Budget)，包含實際執行的媒體、金額與狀態。
    適用於查詢「執行」、「認列」、「實際花費」相關問題。
    
    Args:
        client_names: 客戶名稱列表
        client_ids: 客戶 ID 列表
        agency_ids: 代理商 ID 列表
        industry_ids: 產業類別 (Category) ID 列表
        sub_industry_ids: 產業子類別 (Sub-Category) ID 列表
        campaign_ids: Campaign IDs 列表
        start_date: 開始日期
        end_date: 結束日期
        limit: 返回筆數限制 (預設 5000，排名分析時建議設為 500-1000)
    """
    context = {
        "client_names": client_names,
        "client_ids": client_ids,
        "agency_ids": agency_ids,
        "industry_ids": industry_ids,
        "sub_industry_ids": sub_industry_ids,
        "campaign_ids": campaign_ids,
        "start_date": start_date,
        "end_date": end_date,
        "limit": limit
    }
    return _render_and_execute_mysql("execution_budget.sql", context)

@tool
def query_industry_format_budget(
    dimension: str = 'industry',
    primary_view: str = 'dimension',
    industry_ids: Optional[List[int]] = None,
    sub_industry_ids: Optional[List[int]] = None,
    client_ids: Optional[List[int]] = None,
    agency_ids: Optional[List[int]] = None,
    format_ids: Optional[List[int]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 5000
) -> Dict[str, Any]:
    """
    多維度預算分佈統計 (強制包含格式細節)。
    
    【核心功能】
    此工具透過 `dimension` 參數控制「分組維度」，並自動展開格式細節 (不再支援合併為 All Formats)。
    
    【參數說明】
    - dimension (必填): 決定回傳結果的 GroupBy 對象
      - 'industry': 依「主產業」分組 (預設)。若用戶只說「產業」，請優先使用此選項。
      - 'sub_industry': 依「子產業」分組。僅在用戶明確要求「子產業」、「細分產業」時使用。
      - 'client': 依「客戶」分組
      - 'agency': 依「代理商」分組

    - primary_view (str, default='dimension'):
      - 'dimension': 結果第一欄為維度名稱 (產業/客戶)，第二欄為格式。適用於「以產業為主體」的分析。
      - 'format': 結果第一欄為格式名稱，第二欄為維度名稱。適用於「以格式為主體」的分析 (例如: "Banner 投放到了哪些產業？")。
    
        - 篩選條件 (Filters):
    
          - format_ids: 若指定，則只看特定格式。
    
            ⚠️ **全量查詢守則**: 若使用者問「所有格式」，請務必傳入 None。嚴禁嘗試列舉所有 ID (如 [1,2,3...])，這會導致數據遺漏。
    
          - industry_ids/client_ids: 若指定，則只看特定範圍。
    
            ⚠️ **全量查詢守則**: 若使用者問「全產業」或「所有客戶」，請務必傳入 None。不要自作聰明去列舉。
    
        
    
        - limit: 返回筆數限制 (預設 5000)。
    
          ⚠️ 注意: 若要計算「佔比」(Share) 或「總排名」，請勿設定過小 的 limit (例如 50)，以免分母被截斷導致佔比計算錯誤。
    
          除非用戶明確要求「前 N 名」，否則請保持預設值或設為較大數值 (如 1000)。
    
    【常見應用情境】
    1. 「所有格式投放到的產業排名」 -> dimension='industry', primary_view='format' (這時 'format' 會在第一欄，強調「針對各格式」的總表)
    2. 「Outstream格式投放到的前十大客戶」 -> dimension='client', format_ids=[...], primary_view='format'
    3. 「汽車產業投了哪些格式」 -> dimension='industry', industry_ids=[...], primary_view='dimension' (預設)
    """
    # 1. 參數清理 (Sanitization)
    def clean_list(lst):
        if not lst: return None
        # 過濾掉 None 和空字串，若過濾後為空則回傳 None
        cleaned = [x for x in lst if x is not None and str(x).strip() != '']
        return cleaned if cleaned else None

    industry_ids = clean_list(industry_ids)
    sub_industry_ids = clean_list(sub_industry_ids)
    client_ids = clean_list(client_ids)
    agency_ids = clean_list(agency_ids)
    format_ids = clean_list(format_ids)

    # 2. 邏輯檢查 (Validation): 遇到無效維度，回傳錯誤讓 Agent 自行修正
    valid_dimensions = ['industry', 'sub_industry', 'client', 'agency']
    if dimension not in valid_dimensions:
        return {
            "status": "error",
            "message": f"Invalid dimension value: '{dimension}'. Allowed values are: {valid_dimensions}. Please check your input and retry."
        }

    context = {
        "dimension": dimension,
        "split_by_format": True, # 強制依格式拆分，不再支援 False (All Formats)
        "primary_view": primary_view,
        "industry_ids": industry_ids,
        "sub_industry_ids": sub_industry_ids,
        "client_ids": client_ids,
        "agency_ids": agency_ids,
        "format_ids": format_ids,
        "start_date": start_date,
        "end_date": end_date,
        "limit": limit
    }
    return _render_and_execute_mysql("industry_format_budget.sql", context)

@tool
def query_targeting_segments(
    campaign_ids: List[int]
) -> Dict[str, Any]:
    """
    查詢活動的「數據鎖定」或「受眾標籤」設定 (Targeting Segments)。
    
    ⚠️ 注意: 此工具必須提供 `campaign_ids`。若只知客戶名稱，請先呼叫 `query_campaign_basic` 取得 IDs。
    
    Args:
        campaign_ids: Campaign IDs 列表 (必填)
    """
    context = {
        "campaign_ids": campaign_ids
    }
    return _render_and_execute_mysql("targeting_segments.sql", context)

@tool
def query_ad_formats(
    campaign_ids: List[int]
) -> Dict[str, Any]:
    """
    查詢活動的「廣告格式」明細 (Ad Formats)，包含格式名稱、平台、秒數等。
    
    ⚠️ 注意: 此工具必須提供 `campaign_ids`。若只知客戶名稱，請先呼叫 `query_campaign_basic` 取得 IDs。
    
    Args:
        campaign_ids: Campaign IDs 列表 (必填)
    """
    context = {
        "campaign_ids": campaign_ids
    }
    return _render_and_execute_mysql("ad_formats.sql", context)

@tool
def query_media_placements(
    campaign_ids: Optional[List[int]] = None,
    client_ids: Optional[List[int]] = None,
    agency_ids: Optional[List[int]] = None,
    industry_ids: Optional[List[int]] = None,
    sub_industry_ids: Optional[List[int]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 1000
) -> Dict[str, Any]:
    """
    查詢投放媒體與版位明細 (Media Placements) 及執行預算。
    此工具回傳的 placement_id (plaid) 是連接 MySQL 與 ClickHouse 成效數據的關鍵 Key。
    
    【核心應用】
    1. 查詢特定 Campaign 的版位: 提供 `campaign_ids`。
    2. 查詢特定客戶在某期間的「所有投放版位 ID (plaid)」: 提供 `client_ids` + `start_date` + `end_date`。
       👉 這是查詢「客戶層級」成效數據的標準前置步驟 (用來獲取 plaids)。
    
    Args:
        campaign_ids: Campaign IDs
        client_ids: Client IDs (用於跨活動查詢版位)
        agency_ids: Agency IDs
        industry_ids: 產業 IDs
        sub_industry_ids: 子產業 IDs
        start_date: 開始日期 (YYYY-MM-DD)
        end_date: 結束日期 (YYYY-MM-DD)
        limit: 限制筆數 (Default 1000)
    """
    context = {
        "campaign_ids": campaign_ids,
        "client_ids": client_ids,
        "agency_ids": agency_ids,
        "industry_ids": industry_ids,
        "sub_industry_ids": sub_industry_ids,
        "start_date": start_date,
        "end_date": end_date,
        "limit": limit
    }
    return _render_and_execute_mysql("media_placements.sql", context)

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
    
    可用的 template_name:
    - media_placements.sql: 投放媒體與版位
    - product_lines.sql: 產品線
    - contract_kpis.sql: 合約 KPI
    - execution_status.sql: 詳細執行狀態
    - 以及上述所有已封裝的模板
    
    Args:
        template_name: SQL 檔案名稱 (ex: 'media_placements.sql')
        campaign_ids: Campaign IDs
        client_names: 客戶名稱
        agency_ids: 代理商 ID 列表
        industry_ids: 產業類別 (Category) ID 列表
        sub_industry_ids: 產業子類別 (Sub-Category) ID 列表
        start_date: 開始日期
        end_date: 結束日期
        limit: 返回筆數限制 (預設 1000)
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