
from typing import Dict, Any, List
from langchain_core.tools import tool
from services.performance_generator import clickhouse_generator_node
from services.performance_executor import clickhouse_executor_node
from schemas.state import AgentState

def create_ch_mock_state(
    sql_result: List[Dict[str, Any]],
    sql_result_columns: List[str],
    filters: Dict[str, Any],
    analysis_needs: Dict[str, Any]
) -> AgentState:
    return {
        "sql_result": sql_result,
        "sql_result_columns": sql_result_columns,
        "extracted_filters": filters,
        "analysis_needs": analysis_needs,
        # Default keys
        "clickhouse_sqls": [],
        "clickhouse_result": [],
        "error_message": None,
        "is_valid_sql": False
    }

@tool
def query_performance_data(
    ids_data: List[Dict[str, Any]],
    ids_columns: List[str],
    filters: Dict[str, Any],
    analysis_needs: Dict[str, Any]
) -> Dict[str, Any]:
    """
    查詢 ClickHouse 資料庫以獲取廣告成效數據 (Impressions, Clicks, CTR, VTR 等)。
    必須先從 query_campaign_data 獲取 ID 列表 (ids_data) 才能呼叫此工具。
    
    Args:
        ids_data: 從 query_campaign_data 獲取的結果數據 (包含 cmpid)
        ids_columns: 對應的欄位名稱列表
        filters: 用於日期範圍 (date_start, date_end)
        analysis_needs: 定義需要的成效指標 (metrics)
        
    Returns:
        Dict: 包含 'clickhouse_result' (成效數據列表)
    """
    
    if not ids_data:
        return {"error": "No ID data provided via MySQL result.", "data": []}

    mock_state = create_ch_mock_state(ids_data, ids_columns, filters, analysis_needs)
    
    try:
        # 1. 生成 ClickHouse SQL
        gen_result = clickhouse_generator_node(mock_state)
        mock_state.update(gen_result)
        
        # 如果生成失敗 (例如沒有有效 ID)
        if not gen_result.get("clickhouse_sqls"):
             return {"error": "Failed to generate ClickHouse SQL (possibly missing IDs).", "data": []}

        # 2. 執行 SQL
        exec_result = clickhouse_executor_node(mock_state)
        
        if exec_result.get("error_message"):
            return {"error": exec_result["error_message"], "data": []}
            
        return {
            "error": None,
            "data": exec_result.get("clickhouse_result", [])
        }
        
    except Exception as e:
         return {"error": str(e), "data": []}
