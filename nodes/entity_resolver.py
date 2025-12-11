from schemas.state import AgentState
from config.database import get_mysql_db 
from sqlalchemy import text 
import re

def entity_resolver_node(state: AgentState):
    """
    Deterministically resolves entities in UserIntent.
    """
    user_intent = state.get("user_intent")
    
    # 1. Fast Pass
    if not user_intent:
        return {"user_intent": user_intent}
    if user_intent.query_level == 'chitchat':
        return {"user_intent": user_intent}
    if not user_intent.entities:
        return {"user_intent": user_intent}

    # ... (Imports remain)

    original_entities = user_intent.entities
    print(f"DEBUG [EntityResolver] Resolving {len(original_entities)} entities: {original_entities}")
    
    db = get_mysql_db()
    engine = db._engine 
    
    resolved_campaign_ids = set()
    resolved_ad_format_ids = set()
    
    all_ambiguous_options = []
    has_ambiguity = False
    
    for raw_entity in original_entities:
        # Clean entity name
        entity = re.sub(r"\s*\(.*?\)$", "", raw_entity).strip()
        if not entity: continue
        
        print(f"DEBUG [EntityResolver] Processing: '{entity}'")
        
        # --- 1. Campaign/Client Search ---
        camp_options = []
        try:
            with engine.connect() as conn:
                # Query 1: Campaign Names
                res1 = conn.execute(text("SELECT DISTINCT name FROM one_campaigns WHERE name LIKE :term LIMIT 10"), {"term": f"%{entity}%"}).fetchall()
                camp_options.extend([row[0] for row in res1])
                
                # Query 2: Client Companies
                res2 = conn.execute(text("SELECT DISTINCT company FROM clients WHERE company LIKE :term LIMIT 10"), {"term": f"%{entity}%"}).fetchall()
                camp_options.extend([row[0] for row in res2])
                
                # Query 3: Client Products
                res3 = conn.execute(text("SELECT DISTINCT product FROM clients WHERE product LIKE :term LIMIT 10"), {"term": f"%{entity}%"}).fetchall()
                camp_options.extend([row[0] for row in res3])
                
                camp_options = list(set(camp_options))
        except Exception as e:
            print(f"DEBUG [EntityResolver] DB Error (Campaign): {e}")

        # --- 2. Ad Format Search ---
        format_options = []
        try:
            with engine.connect() as conn:
                res_fmt = conn.execute(text("SELECT id, title FROM ad_format_types WHERE title LIKE :term LIMIT 10"), {"term": f"%{entity}%"}).fetchall()
                # Store tuple (id, title)
                format_options = [(row[0], row[1]) for row in res_fmt]
        except Exception as e:
            print(f"DEBUG [EntityResolver] DB Error (Format): {e}")

        # --- 3. Decision Logic ---
        # Priority: Campaign > Format (Unless user specified otherwise, but here we check existence)
        
        # A. Campaign Match
        if camp_options:
            if len(camp_options) == 1 or entity in camp_options:
                # Exact/Unique Match -> Resolve ID
                target_name = camp_options[0] if len(camp_options) == 1 else entity
                try:
                    with engine.connect() as conn:
                        # Resolve Campaign IDs (Name matches Campaign or Client)
                        # Case 1: Campaign Name
                        ids_1 = conn.execute(text("SELECT id FROM one_campaigns WHERE name = :name"), {"name": target_name}).fetchall()
                        for row in ids_1: resolved_campaign_ids.add(row[0])
                        
                        # Case 2: Client (Company/Product)
                        ids_2 = conn.execute(text("""
                            SELECT c.id FROM one_campaigns c 
                            JOIN cue_lists cl ON c.cue_list_id = cl.id 
                            JOIN clients client ON cl.client_id = client.id 
                            WHERE client.company = :name OR client.product = :name
                        """), {"name": target_name}).fetchall()
                        for row in ids_2: resolved_campaign_ids.add(row[0])
                        
                except Exception as e:
                    print(f"DEBUG [EntityResolver] ID Resolution Error: {e}")
            else:
                # Ambiguous Campaign
                has_ambiguity = True
                # Add source hint
                all_ambiguous_options.extend([f"{opt} (Campaign/Client)" for opt in camp_options])

        # B. Format Match (Only if not already resolved as Campaign, OR if it clearly looks like a format)
        # If we found campaign options, we might skip format check to avoid noise, 
        # UNLESS the entity is something like "Video" which could be both.
        # Strategy: If found as Format, add IDs.
        if format_options:
            # Check for exact match in titles
            exact_fmt = next((f for f in format_options if f[1].lower() == entity.lower()), None)
            
            if len(format_options) == 1 or exact_fmt:
                target_fmt = exact_fmt if exact_fmt else format_options[0]
                resolved_ad_format_ids.add(target_fmt[0])
                print(f"DEBUG [EntityResolver] Resolved Format: {target_fmt[1]} (ID: {target_fmt[0]})")
            else:
                # Ambiguous Format - only if we didn't find it as a campaign
                # If it's ambiguous in BOTH, we should probably list both.
                if not camp_options: 
                    has_ambiguity = True
                    all_ambiguous_options.extend([f"{opt[1]} (Ad Format)" for opt in format_options])

        # C. No Match
        if not camp_options and not format_options:
            print(f"DEBUG [EntityResolver] No match for '{entity}'")
            # If it was the only entity, maybe mark ambiguous to trigger 'not found' msg?
            # But usually we just ignore unknown entities and let others handle it.
            if len(original_entities) == 1:
                 has_ambiguity = True
                 all_ambiguous_options.append(f"找不到 '{entity}' 的相關資料。")

    # Update UserIntent if ambiguous
    if has_ambiguity:
        user_intent.is_ambiguous = True
        user_intent.ambiguous_options = list(set(all_ambiguous_options))[:20]
        # Clear IDs to prevent partial execution? 
        # Strategy: If ambiguous, ask user. Don't run SQL yet.
        return {"user_intent": user_intent, "campaign_ids": [], "ad_format_ids": []}

    # Return resolved IDs
    return {
        "user_intent": user_intent,
        "campaign_ids": list(resolved_campaign_ids),
        "ad_format_ids": list(resolved_ad_format_ids)
    }