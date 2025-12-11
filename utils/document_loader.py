import os

DOCS_DIR = os.path.join(os.getcwd(), "documents")

def load_clickhouse_schema() -> str:
    """
    Loads the ClickHouse schema documentation.
    """
    path = os.path.join(DOCS_DIR, "clickhouse_schema_context.md")
    if not os.path.exists(path):
        return "Error: ClickHouse Schema documentation not found."
    
    with open(path, "r", encoding="utf-8") as f:
        return f.read()
