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

    errors = []

    # 1. 檢查是否為唯讀
    if not re.match(r"^SELECT", sql, re.IGNORECASE):
        errors.append("ClickHouse query must start with SELECT.")

    # 2. 【關鍵】檢查 Partition Key (day_local)
    # 簡單檢查是否有 day_local 關鍵字出現在 WHERE 子句中
    # (更嚴謹的做法是解析 AST，但在這裡 Regex 通常夠用)
    if "day_local" not in sql:
        errors.append("PERFORMANCE RISK: Query must filter by partition key 'day_local'.")

    # 3. 檢查 LIMIT
    if "LIMIT" not in sql.upper():
        # 自動修正：如果沒有 LIMIT，我們可以幫它加，或者報錯
        # 這裡選擇報錯讓 Generator 重寫，或者直接在 state 中 append
        errors.append("SAFETY RISK: Query must include a LIMIT clause.")

    # 4. 檢查危險關鍵字 (針對 ClickHouse)
    forbidden_keywords = ["DROP", "TRUNCATE", "ALTER", "OPTIMIZE"]
    for kw in forbidden_keywords:
        if re.search(rf"\b{kw}\b", sql, re.IGNORECASE):
            errors.append(f"SECURITY RISK: Forbidden keyword '{kw}' detected.")

    if errors:
        # 驗證失敗
        error_msg = "SQL Validation Failed:\n" + "\n".join(errors)
        return {
            "is_valid_sql": False,
            "error_message": error_msg
        }

    # 驗證通過
    return {"is_valid_sql": True, "error_message": None}
