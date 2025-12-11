from tools.search_db import _search_ambiguous_term_impl
from config.database import get_mysql_db, test_mysql_connection

def run_debug():
    print("=== 1. Testing DB Connection ===")
    test_mysql_connection()
    
    print("\n=== 2. Testing search('悠遊卡') ===")
    results = _search_ambiguous_term_impl("悠遊卡")
    print(f"Results: {results}")
    
    # Try partial
    print("\n=== 3. Testing search('悠遊') ===")
    results_partial = _search_ambiguous_term_impl("悠遊")
    print(f"Results: {results_partial}")

if __name__ == "__main__":
    run_debug()