import re
from schemas.state import GraphState


def sql_checker_node(state: GraphState) -> GraphState:
    """
    Checks the generated SQL query for correctness against the term clarifications.
    """
    print("---SQL CHECKER---")
    generated_sql = state["generated_sql"]
    term_clarifications = state.get("term_clarifications", [])
    sql_is_correct = True

    # Simple check to find the WHERE clause part of the query
    where_clause_match = re.search(r"WHERE\s+(.*)", generated_sql, re.IGNORECASE)
    where_clause = where_clause_match.group(1) if where_clause_match else ""

    for item in term_clarifications:
        # Check for resolved terms
        if item.get("type") != "unresolved" and "column" in item and "value" in item:
            column = item["column"]
            value = item["value"]
            # Check if the exact `column` = 'value' condition exists
            # This is a simplified check and might need to be more robust
            expected_condition = f"`{column}` = '{value}'"
            if expected_condition not in where_clause:
                print(f"ERROR: SQL query is missing or has incorrect condition for '{value}'. Expected: {expected_condition}")
                sql_is_correct = False
        
        # Check for unresolved terms that were rejected by the user
        elif item.get("type") == "unresolved":
            term = item["term"]
            # Check if the rejected term still appears in the WHERE clause
            if term in where_clause:
                print(f"ERROR: SQL query incorrectly contains rejected term '{term}'.")
                sql_is_correct = False

    if not sql_is_correct:
        # For now, we just flag it. A future improvement could be to loop back.
        print("SQL query failed validation.")
    else:
        print("SQL query passed validation.")

    return {
        "sql_is_correct": sql_is_correct
    }
