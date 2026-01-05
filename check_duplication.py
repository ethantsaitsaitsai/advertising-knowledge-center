from config.database import get_mysql_db
from sqlalchemy import text

def check():
    db = get_mysql_db()
    with db._engine.connect() as conn:
        # Check 1: Do campaigns have multiple categories?
        sql = """
        SELECT one_campaign_id, COUNT(*) as cnt 
        FROM pre_campaign 
        GROUP BY one_campaign_id 
        HAVING cnt > 1 
        LIMIT 5
        """
        print("Checking for multiple categories per campaign...")
        res = conn.execute(text(sql)).fetchall()
        if res:
            print(f"⚠️ FOUND Duplicates! Example: {res}")
        else:
            print("✅ No duplicates found (1:1 relationship confirmed for Categories)")

        # Check 2: Do campaigns have multiple product lines?
        # (This is expected 1:N, but does it multiply budget?)
        # cue_lists -> product_lines -> ad_formats -> budgets
        # Budget is at leaf level, so summing them up is correct for Total Campaign Budget.
        
if __name__ == "__main__":
    check()
