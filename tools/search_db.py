import ast
from langchain.tools import tool
from config.database import db

def parse_db_result_to_list(result: str) -> list:
    """
    Parses the string representation of a list from a database query result into a Python list.
    Example: "['悠遊卡Q1', '悠遊卡_加值']" -> ['悠遊卡Q1', '悠遊卡_加值']
    """
    try:
        # Safely evaluate the string to a Python literal
        return ast.literal_eval(result)
    except (ValueError, SyntaxError):
        # If the result is not a string representation of a list, return it as a single-item list
        return [result]

@tool
def search_ambiguous_term(keyword: str, column_name: str, table_name: str = "cuelist") -> list:
    """
    Searches for possible full names in the database when the user's input is ambiguous.
    - keyword: The term entered by the user, e.g., '悠遊卡'
    - column_name: The column to search in, e.g., '廣告案件名稱' or '品牌'
    - table_name: The table to search in.
    """
    # Note on security: In a production environment, parameterized queries are recommended.
    # Here, we compose the string directly for demonstration of logic.
    # Limit to 10 results to avoid excessive token usage.
    query = f"""
    SELECT DISTINCT `{column_name}` 
    FROM `{table_name}` 
    WHERE `{column_name}` LIKE '%%{keyword}%%' 
    LIMIT 10;
    """
    try:
        result = db.run(query)
        # The result from db.run is often a string representation of a list
        return parse_db_result_to_list(result) 
    except Exception as e:
        return [f"Search failed: {e}"]
