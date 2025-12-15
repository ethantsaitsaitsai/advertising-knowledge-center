from typing import List, Optional, Dict
from langchain.tools import tool
from sqlalchemy import text
from utils.rag_service import RagService
from config.database import get_mysql_db

def search_sql_like(keyword: str) -> List[str]:
    """
    Performs SQL LIKE search and returns formatted strings with source info.
    Format: "Value (Table: Column)"
    """
    candidates = []
    
    # Mapping: filter_type -> (table, column, extra_where)
    mapping = {
        "brands": ("clients", "product", "product IS NOT NULL AND product != ''"),
        "advertisers": ("clients", "company", "company IS NOT NULL AND company != ''"),
        "campaign_names": ("one_campaigns", "name", "name IS NOT NULL AND name != ''"), 
        "cue_campaigns": ("cue_lists", "campaign_name", "campaign_name IS NOT NULL AND campaign_name != ''"),
        "agencies": ("agency", "agencyname", "agencyname IS NOT NULL AND agencyname != ''"),
    }

    db = get_mysql_db()
    
    try:
        with db._engine.connect() as connection:
            # Fix unpacking: mapping.items() returns key, value_tuple
            for f_type, (table, col, condition) in mapping.items():
                query = text(f"SELECT DISTINCT `{col}` FROM `{table}` WHERE `{col}` LIKE :kw AND {condition} LIMIT 10")
                result = connection.execute(query, {"kw": f"%{keyword}%"})
                
                rows = result.fetchall()
                for row in rows:
                    val = row[0]
                    if val:
                        display_text = f"{val} ({table}: {col})"
                        candidates.append(display_text)
                result.close()
    except Exception as e:
        print(f"⚠️ SQL LIKE search failed: {e}")

    # Deduplicate while preserving order
    seen = set()
    unique_candidates = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            unique_candidates.append(c)

    return unique_candidates[:10]

def _search_ambiguous_term_impl(keyword: str) -> List[str]:
    """
    Implementation of search logic (Pure Python function).
    Returns all results, including both exact matches and partial matches.
    The caller (Intent Analyzer) will decide whether to confirm based on exact match count.
    """
    print(f"🔎 Searching '{keyword}'...")
    candidates = search_sql_like(keyword)

    if candidates:
        print(f"✅ Found {len(candidates)} matches.")
        # Extract the entity names (before the parentheses) for analysis
        entity_names = [c.split(" (")[0] for c in candidates]
        exact_matches = [c for c in candidates if c.split(" (")[0] == keyword]
        print(f"   - Exact matches: {len(exact_matches)}")
        print(f"   - Partial matches: {len(candidates) - len(exact_matches)}")
    else:
        print(f"📉 No matches found.")

    return candidates

@tool
def search_ambiguous_term(keyword: str) -> List[str]:
    """
    Searches for an entity in the database and returns candidates with their source table/column.
    Use this to verify entity names or resolve ambiguity.
    
    Returns a list of strings in the format: "EntityName (Table: ColumnName)"
    Example: "悠遊卡 (clients: product)"
    """
    return _search_ambiguous_term_impl(keyword)