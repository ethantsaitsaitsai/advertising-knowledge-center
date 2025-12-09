import re
from typing import Dict, Any
from schemas.state import AgentState


def sql_validator_node(state: AgentState) -> Dict[str, Any]:
    """
    負責檢查 SQL 的安全性與基本語法規範。
    支援檢查單一 SQL (generated_sql) 或批次 SQL 列表 (generated_sqls)。
    如果不通過，回傳錯誤訊息，將流程導回 SQLGenerator。
    """
    # 優先檢查批次 SQL 列表
    sql_queries = state.get("generated_sqls")
    if not sql_queries:
        # Fallback 到單一 SQL
        single_sql = state.get("generated_sql", "").strip()
        if single_sql:
            sql_queries = [single_sql]
        else:
            # 如果沒有 SQL Query，直接通過
            return {
                "error_message": None,
                "is_valid_sql": True
            }

    forbidden_keywords = [
        r"\bINSERT\b", r"\bUPDATE\b", r"\bDELETE\b", r"\bDROP\b",
        r"\bALTER\b", r"\bTRUNCATE\b", r"\bGRANT\b", r"\bREVOKE\b"
    ]

    errors = []

    for i, sql_query in enumerate(sql_queries):
        # --- 1. 安全性檢查 (Security Check) ---
        for pattern in forbidden_keywords:
            if re.search(pattern, sql_query, re.IGNORECASE):
                clean_pattern = pattern.replace(r"\\b", "")
                errors.append(f"SQL [{i}] 安全性警報：偵測到禁用關鍵字 '{clean_pattern}'。")

    # --- 3. 判斷結果 ---
    if errors:
        error_msg = "SQL 驗證失敗:\n" + "\n".join(errors)
        return {
            "error_message": error_msg,
            "is_valid_sql": False 
        }
    else:
        return {
            "error_message": None,
            "is_valid_sql": True
        }
