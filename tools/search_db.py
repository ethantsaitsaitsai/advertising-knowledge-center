from typing import List, Optional, Dict
from langchain.tools import tool
from sqlalchemy import text
from utils.rag_service import RagService
from config.database import get_mysql_db

def search_sql_like(keyword: str, type_filter: Optional[str] = None) -> List[dict]:
    """
    Performs SQL LIKE search for exact/partial string matches.
    """
    candidates = []
    
    # Mapping: filter_type -> (table, column, extra_where)
    mapping = {
        "brands": ("clients", "product", "product IS NOT NULL AND product != ''"),
        "advertisers": ("clients", "company", "company IS NOT NULL AND company != ''"),
        "agencies": ("agency", "agencyname", "agencyname IS NOT NULL AND agencyname != ''"),
        "campaign_names": ("cue_lists", "campaign_name", "campaign_name IS NOT NULL AND campaign_name != ''"),
        "industries": ("pre_campaign_categories", "name", "name IS NOT NULL AND name != ''"),
        "keywords": ("target_segments", "data_value", "data_source='keyword' AND data_value IS NOT NULL AND data_value != ''")
    }

    targets = []
    if type_filter and type_filter != "all":
        if type_filter in mapping:
            targets.append((type_filter, *mapping[type_filter]))
    else:
        # If no filter, search everywhere (except maybe keywords to avoid noise?)
        # Let's search everywhere for now.
        for k, v in mapping.items():
            targets.append((k, *v))

    db = get_mysql_db()
    
    try:
        with db._engine.connect() as connection:
            for f_type, table, col, condition in targets:
                # Limit each category to 3 to avoid flooding if it's a generic term
                query = text(f"SELECT DISTINCT `{col}` FROM `{table}` WHERE `{col}` LIKE :kw AND {condition} LIMIT 3")
                result = connection.execute(query, {"kw": f"%{keyword}%"})
                
                for row in result:
                    val = row[0]
                    if val:
                        candidates.append({
                            "value": val,
                            "source": col,
                            "table": table,
                            "filter_type": f_type,
                            "score": 1.0 # SQL match is considered perfect match
                        })
    except Exception as e:
        print(f"⚠️ SQL LIKE search failed: {e}")
        # Fallback will happen naturally as candidates will be empty or partial

    return candidates

@tool
def search_ambiguous_term(keyword: str, type_filter: Optional[str] = None) -> List[dict]:
    """
    Hybrid Search: SQL LIKE First -> RAG Fallback.
    
    1. Tries to find exact/partial matches using SQL LIKE.
    2. If no results found (or very few), falls back to RAG (Vector Search) for semantic matching.
    
    Args:
        keyword: The term to search for.
        type_filter: Optional. If provided (e.g., 'agencies', 'brands'), restricts search.
    """
    print(f"🔎 Searching '{keyword}' (Filter: {type_filter})...")
    
    # 1. Try SQL LIKE
    candidates = search_sql_like(keyword, type_filter)
    
    # 2. RAG Fallback
    # If we have 0 results, definitely RAG.
    # You can adjust this logic (e.g. if len < 3, also RAG)
    if not candidates:
        print(f"📉 SQL LIKE found no results. Falling back to RAG...")
        rag = RagService()
        # RAG Service uses its own default top_k and threshold
        rag_results = rag.search(keyword, type_filter=type_filter)
        
        for res in rag_results:
            candidates.append({
                "value": res["value"],
                "source": res.get("source", res.get("source_col")), 
                "table": res["table"],
                "filter_type": res["filter_type"],
                "score": res["score"]
            })
    else:
        print(f"✅ SQL LIKE found {len(candidates)} matches. Skipping RAG.")

    return candidates