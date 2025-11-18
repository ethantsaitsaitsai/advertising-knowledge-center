import re
from typing import Tuple
from schemas.state import GraphState
from langchain_core.messages import ToolMessage

# --- Configuration for SQL Constraints ---

SQL_CONSTRAINTS = {
    "DEFAULT_LIMIT": 100,
}

FORBIDDEN_KEYWORDS = {
    "write_operations": ["INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE", "ALTER", "CREATE"],
    "system_access": ["EXEC", "EXECUTE", "xp_", "sp_"],
    "dangerous_functions": ["LOAD_FILE", "INTO OUTFILE", "INTO DUMPFILE"]
}

COMPLEXITY_LIMITS = {
    "MAX_JOINS": 5,
}

# --- Constraint Functions ---

def validate_sql_safety(sql: str) -> Tuple[bool, str]:
    """Checks if the SQL contains any forbidden keywords."""
    sql_upper = sql.upper()
    for category, keywords in FORBIDDEN_KEYWORDS.items():
        for keyword in keywords:
            if re.search(r'\b' + keyword + r'\b', sql_upper):
                return False, f"SQL query rejected. Forbidden keyword '{keyword}' from category '{category}' found."
    return True, "OK"

def check_query_complexity(sql: str) -> Tuple[bool, str]:
    """Checks if the query complexity is within defined limits."""
    join_count = sql.upper().count(" JOIN ")
    if join_count > COMPLEXITY_LIMITS["MAX_JOINS"]:
        return False, f"SQL query rejected. Query complexity exceeds limits: Found {join_count} JOINs, maximum allowed is {COMPLEXITY_LIMITS['MAX_JOINS']}."
    return True, "OK"

def enforce_limit(sql: str) -> str:
    """Enforces a LIMIT clause on SELECT queries."""
    sql_upper = sql.upper()
    if sql_upper.startswith("SELECT") and "LIMIT" not in sql_upper:
        if "GROUP BY" not in sql_upper and "COUNT(" not in sql_upper and "SUM(" not in sql_upper and "AVG(" not in sql_upper:
             sql = sql.rstrip(';') + f" LIMIT {SQL_CONSTRAINTS['DEFAULT_LIMIT']}"
    return sql

# --- Main Node Function ---

def sql_constraint_checker_node(state: GraphState) -> GraphState:
    """
    A mandatory node that programmatically checks the agent-generated SQL for safety and compliance.
    """
    print("---SQL CONSTRAINT CHECKER---")
    messages = state["messages"]
    proposed_sql = messages[-1].content

    # 1. Safety Check
    is_safe, message = validate_sql_safety(proposed_sql)
    if not is_safe:
        print(f"Validation Failed: {message}")
        # Add error message to history for the agent to see on retry
        error_message = ToolMessage(content=message, tool_call_id="sql_constraint_checker")
        return {"sql_is_safe": False, "messages": messages + [error_message]}

    # 2. Complexity Check
    is_complex_ok, message = check_query_complexity(proposed_sql)
    if not is_complex_ok:
        print(f"Validation Failed: {message}")
        error_message = ToolMessage(content=message, tool_call_id="sql_constraint_checker")
        return {"sql_is_safe": False, "messages": messages + [error_message]}

    # 3. Enforce LIMIT
    safe_sql = enforce_limit(proposed_sql)
    
    print("Validation Passed. SQL is safe and modified.")
    return {
        "sql_is_safe": True,
        "safe_sql": safe_sql,
    }