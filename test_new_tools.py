import os
import json
from tools.campaign_template_tool import (
    query_campaign_basic,
    query_budget_details,
    query_targeting_segments
)
from dotenv import load_dotenv

def test_flow():
    load_dotenv()
    print("🚀 Starting Test Flow for '悠遊卡股份有限公司'...")

    # 1. Test query_campaign_basic
    print("\n--- 1. Testing query_campaign_basic ---")
    res_basic = query_campaign_basic.invoke({
        "client_names": ["悠遊卡股份有限公司"],
        "start_date": "2010-01-01",
        "end_date": "2026-12-31"
    })
    
    if res_basic["status"] == "success":
        print(f"✅ Success! Found {res_basic['count']} campaigns.")
        campaign_ids = [row["campaign_id"] for row in res_basic["data"]]
        print(f"Campaign IDs: {campaign_ids[:5]}...")
        
        if not campaign_ids:
            print("⚠️ No campaigns found. Stopping further tests.")
            return

        # 2. Test query_budget_details
        print("\n--- 2. Testing query_budget_details ---")
        res_budget = query_budget_details.invoke({"campaign_ids": campaign_ids[:5]})
        if res_budget["status"] == "success":
            print(f"✅ Success! Found {res_budget['count']} budget records.")
            # print(json.dumps(res_budget['data'][:2], indent=2, ensure_ascii=False))
        else:
            print(f"❌ Failed: {res_budget.get('message')}")

        # 3. Test query_targeting_segments
        print("\n--- 3. Testing query_targeting_segments ---")
        res_target = query_targeting_segments.invoke({"campaign_ids": campaign_ids[:5]})
        if res_target["status"] == "success":
            print(f"✅ Success! Found {res_target['count']} targeting segments.")
            # print(json.dumps(res_target['data'][:2], indent=2, ensure_ascii=False))
        else:
            print(f"❌ Failed: {res_target.get('message')}")
            
    else:
        print(f"❌ Failed Basic Query: {res_basic.get('message')}")
        if "Template Error" in res_basic.get("message", ""):
            print("💡 Hint: The SQL template might be missing or have syntax errors.")

def test_raw_sql():
    load_dotenv()
    print("\n--- 0. Testing Raw SQL for Client lookup ---")
    from sqlalchemy import text
    from config.database import get_mysql_db
    db = get_mysql_db()
    with db._engine.connect() as conn:
        res = conn.execute(text("SELECT id, company, advertiser_name FROM clients WHERE company LIKE '%悠遊卡%' OR advertiser_name LIKE '%悠遊卡%'"))
        rows = res.fetchall()
        print(f"Found {len(rows)} clients in DB:")
        for r in rows:
            print(r)
            client_id = r[0]
            
            # Check for cue_lists
            res_cl = conn.execute(text(f"SELECT count(*) FROM cue_lists WHERE client_id = {client_id}"))
            cl_count = res_cl.scalar()
            print(f"  - Cue lists count for client {client_id}: {cl_count}")
            
            # Check for one_campaigns via cue_lists
            res_oc = conn.execute(text(f"SELECT count(*) FROM one_campaigns oc JOIN cue_lists cl ON oc.cue_list_id = cl.id WHERE cl.client_id = {client_id}"))
            oc_count = res_oc.scalar()
            print(f"  - One campaigns count for client {client_id}: {oc_count}")
            
            if oc_count > 0:
                # Check status and is_test
                res_detail = conn.execute(text(f"SELECT oc.id, oc.status, oc.is_test, cl.status FROM one_campaigns oc JOIN cue_lists cl ON oc.cue_list_id = cl.id WHERE cl.client_id = {client_id} LIMIT 5"))
                print("  - Sample Campaign Details (id, oc_status, is_test, cl_status):")
                for detail in res_detail.fetchall():
                    print(f"    {detail}")

if __name__ == "__main__":
    test_raw_sql()
    # test_flow()
