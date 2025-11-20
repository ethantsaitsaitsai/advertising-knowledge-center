import re
from typing import Dict, Any
from schemas.state import AgentState


def sql_validator_node(state: AgentState) -> Dict[str, Any]:
    """
    負責檢查 SQL 的安全性與基本語法規範。
    如果不通過，回傳錯誤訊息，將流程導回 SQLGenerator。
    """
    sql_query = state.get("generated_sql", "").strip()
    # 如果沒有 SQL Query，直接通過，讓後續節點處理
    if not sql_query:
        return {
            "error_message": None,
            "is_valid_sql": True
        }

    errors = []

    # --- 1. 安全性檢查 (Security Check) ---
    # 定義禁止的 DML/DDL 關鍵字
    forbidden_keywords = [
        r"\bINSERT\b", r"\bUPDATE\b", r"\bDELETE\b", r"\bDROP\b",
        r"\bALTER\b", r"\bTRUNCATE\b", r"\bGRANT\b", r"\bREVOKE\b"
    ]
    # 使用 Regex 檢查 (忽略大小寫)
    for pattern in forbidden_keywords:
        if re.search(pattern, sql_query, re.IGNORECASE):
            clean_pattern = pattern.replace(r"\\b", "")
            errors.append(f"SQL 安全性警報：偵測到禁用關鍵字 '{clean_pattern}'。此代理為唯讀模式。")

    # --- 2. 語法規範檢查 (此處從簡) ---
    # 根據解決方案文件，我們主要依賴 Prompt 強制和執行錯誤來捕捉 backtick 問題，
    # 因此這裡的檢查保持簡單，主要集中在安全性。

    # --- 3. 判斷結果 ---
    if errors:
        # 將錯誤組裝，準備回傳給 SQLGenerator 讓他重寫
        error_msg = "SQL 驗證失敗:\n" + "\n".join(errors)
        return {
            "error_message": error_msg,
            "is_valid_sql": False  # 新增一個狀態旗標來控制路由
        }
    else:
        # 驗證通過，清除可能存在的舊錯誤
        return {
            "error_message": None,
            "is_valid_sql": True
        }
