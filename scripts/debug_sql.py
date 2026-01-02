import os
import sys
from jinja2 import Environment, FileSystemLoader, select_autoescape

# Setup Jinja2 Environment
TEMPLATE_DIR = os.path.join(os.getcwd(), "templates", "sql")
env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(['sql'])
)

def debug_industry_format_budget():
    print("\n=== Debugging industry_format_budget.sql rendering ===")
    
    # Context mimicking the failing call
    context = {
        "dimension": "industry",
        "split_by_format": True,  # Boolean True
        "primary_view": "format",
        "start_date": "2025-07-02",
        "end_date": "2026-01-02",
        "limit": 50
    }

    try:
        template = env.get_template("industry_format_budget.sql")
        rendered_sql = template.render(**context)
        
        print(f"Context: {context}")
        print("-" * 20)
        # Check the SELECT clause (First ~500 chars)
        print(rendered_sql[:500])
        print("-" * 20)
        
        if "'All Formats' AS format_name" in rendered_sql:
            print("❌ FAILURE: Rendered SQL contains 'All Formats' despite split_by_format=True")
        else:
            print("✅ SUCCESS: Rendered SQL correctly selects format names")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    debug_industry_format_budget()
