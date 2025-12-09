
from typing import Dict, Any, List, Optional
from langchain_core.tools import tool
from services.campaign_generator import sql_generator
from services.campaign_executor import sql_executor
from schemas.state import AgentState

# 我們需要一個 Helper 來模擬 AgentState，因為既有的 sql_generator 依賴它
def create_mock_state(
    query_level: str,
    filters: Dict[str, Any],
    analysis_needs: Dict[str, Any],
    confirmed_entities: List[str] = None
) -> AgentState:
    return {
        "query_level": query_level,
        "extracted_filters": filters,
        "analysis_needs": analysis_needs,
        "confirmed_entities": confirmed_entities or [],
        "messages": [], # sql_generator 需要這個 key，即使是空的
        # 其他欄位給預設值以避免 KeyErrors
        "generated_sqls": [],
        "generated_sql": "",
        "sql_result": [],
        "sql_result_columns": [],
        "error_message": None,
        "is_valid_sql": False
    }

@tool
def query_campaign_data(
    query_level: str,
    filters: Dict[str, Any],
    analysis_needs: Dict[str, Any]
) -> Dict[str, Any]:
    """
    查詢 MySQL 資料庫以獲取廣告活動的元數據、預算、屬性與 ID 列表。
    這**不是**用來查成效 (Impressions, Clicks) 的，而是用來查結構與金額的。
    
    Args:
        query_level: 查詢層級 ('contract', 'strategy', 'execution', 'audience')
        filters: 包含 brands, advertisers, date_range 等過濾條件
        analysis_needs: 包含 metrics (如 Budget_Sum), dimensions (如 Campaign_Name)
    
    Returns:
        Dict: 包含 'sql_result' (資料列表) 和 'sql_result_columns' (欄位名)
    """
    
    # 1. 建構模擬 State
    # 注意：這裡我們重複利用了現有的 Nodes 邏輯，這是最快的方法
    # 未來如果要完全解耦，應該將 sql_generator 的核心邏輯拆解出來
    mock_state = create_mock_state(query_level, filters, analysis_needs)
    
    try:
        # 2. 生成 SQL
        # sql_generator 會回傳 {'generated_sql': ..., 'generated_sqls': ...}
        gen_result = sql_generator(mock_state)
        mock_state.update(gen_result)
        
        # 3. 執行 SQL
        # sql_executor 預期 state 有 'generated_sqls'
        exec_result = sql_executor(mock_state)
        
        if exec_result.get("error_message"):
            return {
                "error": exec_result["error_message"],
                "data": [],
                "columns": []
            }
            
        return {
            "error": None,
            "data": exec_result.get("sql_result", []),
            "columns": exec_result.get("sql_result_columns", [])
        }
        
    except Exception as e:
        return {
            "error": str(e),
            "data": [],
            "columns": []
        }
