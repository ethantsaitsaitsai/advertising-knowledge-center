import re
from typing import Dict, Any
from schemas.state import AgentState


def clickhouse_validator_node(state: AgentState) -> Dict[str, Any]:
    """
    驗證 ClickHouse SQL 的安全性與效能規範。
    重點檢查：
    1. 是否為 SELECT 語句 (Read-Only)。
    2. 是否包含 Partition Key (day_local) 以避免全表掃描。
    3. 是否包含 LIMIT 限制。
    """
    sql = state.get("clickhouse_sql", "").strip()
    current_retry = state.get("retry_count", 0) or 0

    errors = []

    # 0. 檢查是否為空
    if not sql:
        errors.append("SQL is empty.")

    # 1. 檢查是否為唯讀
    elif not re.match(r"^SELECT", sql, re.IGNORECASE):
        errors.append("ClickHouse query must start with SELECT.")

    # 2. 【關鍵】檢查 Partition Key (day_local)
    if sql and "day_local" not in sql:
        errors.append("PERFORMANCE RISK: Query must filter by partition key 'day_local'.")

    # 3. 檢查 LIMIT
    if sql and "LIMIT" not in sql.upper():
        errors.append("SAFETY RISK: Query must include a LIMIT clause.")

    # 4. 檢查危險關鍵字
    forbidden_keywords = ["DROP", "TRUNCATE", "ALTER", "OPTIMIZE"]
    for kw in forbidden_keywords:
        if re.search(rf"\b{kw}\b", sql, re.IGNORECASE):
            errors.append(f"SECURITY RISK: Forbidden keyword '{kw}' detected.")

    if errors:
        # 驗證失敗
        error_msg = "SQL Validation Failed:\n" + "\n".join(errors)
        return {
            "is_valid_sql": False,
            "error_message": error_msg,
            "retry_count": current_retry + 1
        }

    # 驗證通過 -> Reset retry count
    return {
        "is_valid_sql": True, 
        "error_message": None,
        "retry_count": 0
    }