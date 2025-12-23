"""
測試所有 SQL templates 是否可以正常執行
"""
import os
from pathlib import Path
from jinja2 import Template
from config.database import get_mysql_db
from sqlalchemy import text

def test_template(template_name: str, params: dict = None):
    """測試單一 template"""
    print(f"\n{'='*60}")
    print(f"🧪 Testing: {template_name}")
    print(f"{'='*60}")

    template_path = Path("templates/sql") / template_name

    # 讀取 template
    try:
        with open(template_path, 'r', encoding='utf-8') as f:
            template_content = f.read()
    except FileNotFoundError:
        print(f"❌ Template file not found: {template_path}")
        return False

    # 渲染 SQL
    try:
        template = Template(template_content)
        sql = template.render(**(params or {}))
        print(f"📝 Rendered SQL:\n{sql[:500]}...")  # 只顯示前500字元
    except Exception as e:
        print(f"❌ Template rendering failed: {e}")
        return False

    # 執行 SQL
    try:
        db = get_mysql_db()
        # 只有在 SQL 沒有 LIMIT 的情況下才加 LIMIT 1
        test_sql = sql
        if 'LIMIT' not in sql.upper():
            test_sql = f"{sql} LIMIT 1"

        # 使用 engine 直接執行，並綁定參數
        with db._engine.connect() as conn:
            # 如果 params 中有參數，需要綁定
            if params:
                result = conn.execute(text(test_sql), params)
            else:
                result = conn.execute(text(test_sql))
            rows = result.fetchall()
            columns = result.keys()

            print(f"✅ Query executed successfully!")
            print(f"📊 Columns returned: {list(columns)}")
            print(f"📦 Rows returned: {len(rows)}")
            if rows:
                print(f"🔍 Sample row: {dict(zip(columns, rows[0]))}")
            return True

    except Exception as e:
        print(f"❌ Query execution failed!")
        print(f"Error type: {type(e).__name__}")
        print(f"Error message: {str(e)}")

        # 顯示更詳細的錯誤訊息
        if "Unknown column" in str(e):
            print("⚠️  Column name issue detected")
        elif "doesn't exist" in str(e):
            print("⚠️  Table name issue detected")

        return False

def main():
    """主測試流程"""
    print("\n" + "="*60)
    print("🚀 Starting SQL Template Tests")
    print("="*60)

    # 測試用的參數（使用簡單的測試條件）
    test_params = {
        # 不指定 campaign_ids，讓查詢返回所有符合條件的資料
        "client_names": None,  # 不過濾客戶
        "start_date": None,
        "end_date": None,
        "campaign_ids": None  # 不過濾 campaign_ids
    }

    templates_to_test = [
        ("campaign_basic.sql", {}),  # 不需要 campaign_ids 參數
        ("ad_formats.sql", {"campaign_ids": [1]}),  # 需要 campaign_ids，先測試 ID=1
        ("targeting_segments.sql", {"campaign_ids": [1]}),
        ("media_placements.sql", {"campaign_ids": [1]}),
        ("product_lines.sql", {"campaign_ids": [1]}),
        ("budget_details.sql", {"campaign_ids": [1]}),
        ("contract_kpis.sql", {"campaign_ids": [1]}),
        ("execution_status.sql", {"campaign_ids": [1]}),
    ]

    results = {}

    for template_name, params in templates_to_test:
        success = test_template(template_name, params)
        results[template_name] = success

    # 總結
    print("\n" + "="*60)
    print("📊 Test Summary")
    print("="*60)

    total = len(results)
    passed = sum(1 for v in results.values() if v)
    failed = total - passed

    for template_name, success in results.items():
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} - {template_name}")

    print(f"\n📈 Results: {passed}/{total} passed, {failed}/{total} failed")

    if failed > 0:
        print("\n⚠️  Some templates have errors. Please review the details above.")
        print("Common issues to check:")
        print("1. Column names (check schema documentation)")
        print("2. Table names (verify table exists)")
        print("3. Join conditions (verify foreign key relationships)")
    else:
        print("\n🎉 All templates passed!")

if __name__ == "__main__":
    main()
