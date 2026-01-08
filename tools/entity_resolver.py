from typing import List, Dict, Any, Optional
from langchain_core.tools import tool
from sqlalchemy import text
from config.database import get_mysql_db
from services.rag_service import RagService

# 定義搜尋範圍配置
SEARCH_CONFIGS = [
    {
        "type": "client",
        "table": "clients",
        "id_col": "id",
        "name_col": "company",
        "desc": "客戶公司名稱",
        "meta_cols": []
    },
    {
        "type": "agency",
        "table": "agency",
        "id_col": "id",
        "name_col": "agencyname",
        "desc": "代理商名稱",
        "meta_cols": []
    },
    {
        "type": "brand",
        "table": "clients",
        "id_col": "id",
        "name_col": "product",
        "desc": "產品/品牌名稱",
        "meta_cols": []
    },
    {
        "type": "campaign",
        "table": "one_campaigns",
        "id_col": "id",
        "name_col": "name",
        "desc": "執行活動名稱",
        "meta_cols": ["start_date", "status"]
    },
    {
        "type": "contract",
        "table": "cue_lists",
        "id_col": "id",
        "name_col": "campaign_name",
        "desc": "合約/排期名稱",
        "meta_cols": ["start_date", "status"]
    },
    {
        "type": "industry",
        "table": "pre_campaign_categories",
        "id_col": "id",
        "name_col": "name",
        "desc": "產業類別 (大類)",
        "meta_cols": []
    },
    {
        "type": "sub_industry",
        "table": "pre_campaign_sub_categories",
        "id_col": "id",
        "name_col": "name",
        "desc": "產業子類別",
        "meta_cols": []
    },
    {
        "type": "ad_format",
        "table": "ad_format_types",
        "id_col": "id",
        "name_col": "title",
        "desc": "廣告格式",
        "meta_cols": []
    }
]

def _search_table(conn, config: Dict, keyword: str) -> List[Dict[str, Any]]:
    """
    執行單一表格的 SQL 搜尋（LIKE 查詢）
    """
    meta_select = ""
    if config.get("meta_cols"):
        meta_select = ", " + ", ".join(config["meta_cols"])

    # 過濾掉空字串或 NULL 的欄位
    query = text(f"""
        SELECT {config['id_col']} as id, {config['name_col']} as name {meta_select}
        FROM {config['table']}
        WHERE {config['name_col']} LIKE :kw
          AND {config['name_col']} IS NOT NULL
          AND {config['name_col']} != ''
        ORDER BY {config['id_col']} DESC
        LIMIT 15
    """)

    try:
        result = conn.execute(query, {"kw": f"%{keyword}%"})
        columns = result.keys()
        rows = result.fetchall()
        
        candidates = []
        for row in rows:
            row_dict = dict(zip(columns, row))
            candidate = {
                "id": row_dict["id"],
                "name": row_dict["name"],
                "type": config["type"],
                "table": config["table"],
                "column": config["name_col"],
                "description": f"{row_dict['name']} ({config['desc']})"
            }
            
            # 處理 Metadata
            meta = {}
            if "start_date" in row_dict and row_dict["start_date"]:
                # 轉為年份
                try:
                    meta["year"] = row_dict["start_date"].year if hasattr(row_dict["start_date"], 'year') else str(row_dict["start_date"])[:4]
                except:
                    meta["year"] = str(row_dict["start_date"])[:4]
            
            if "status" in row_dict:
                status_map = {
                    "converted": "已轉正式",
                    "requested": "需求中",
                    "oncue": "投放中",
                    "close": "已結案",
                    "deleted": "已刪除"
                }
                meta["status"] = status_map.get(row_dict["status"], row_dict["status"])
            
            if meta:
                candidate["metadata"] = meta
                
            candidates.append(candidate)
            
        return candidates
    except Exception as e:
        print(f"⚠️ LIKE search failed for {config['table']}.{config['name_col']}: {e}")
        return []

@tool
def resolve_entity(
    keyword: str,
    target_types: Optional[List[str]] = None,
    use_rag: bool = True,
    selected_id: Optional[int] = None,
    selected_type: Optional[str] = None
) -> Dict[str, Any]:
    """
    三階段實體解析工具：LIKE 查詢 → 使用者確認 → RAG 向量搜尋

    Args:
        keyword: 要搜尋的實體名稱 (例如: "悠遊卡", "台新")
        target_types: 可選的類型過濾 ['campaign', 'client', 'agency', 'brand', 'contract']
        use_rag: 當 LIKE 查詢無結果時是否使用 RAG (預設 True)
        selected_id: 使用者選擇的實體 ID (用於確認流程)
        selected_type: 使用者選擇的實體類型 (用於確認流程)

    Returns:
        {
            "status": "exact_match" | "needs_confirmation" | "rag_results" | "not_found",
            "data": {...} or [...],
            "message": "...",
            "source": "like_query" | "rag" | "user_selection"
        }

    流程：
    1. 如果提供了 selected_id 和 selected_type，直接返回該實體 (使用者已確認)
    2. 執行 LIKE 查詢 (搜尋 campaign, clients, agency 等欄位)
       - 如果結果 = 1 筆 → 返回 exact_match
       - 如果結果 > 1 筆 → 返回 needs_confirmation (需要使用者選擇)
       - 如果結果 = 0 筆 → 進入步驟 3
    3. 使用 RAG 向量搜尋 (Qdrant)
       - 返回相似度高的候選實體
    """
    print(f"🔍 [EntityResolver] Resolving: '{keyword}'")

    # ===== 階段 0: 使用者已確認選擇 =====
    if selected_id and selected_type:
        print(f"✅ [EntityResolver] User confirmed selection: {selected_type} ID={selected_id}")
        db = get_mysql_db()
        with db._engine.connect() as connection:
            # 根據 type 找到對應的 config
            config = next((c for c in SEARCH_CONFIGS if c["type"] == selected_type), None)
            if not config:
                return {
                    "status": "error",
                    "data": {},
                    "message": f"Invalid entity type: {selected_type}",
                    "source": "user_selection"
                }

            # 查詢該實體的詳細資訊
            query = text(f"""
                SELECT {config['id_col']} as id, {config['name_col']} as name
                FROM {config['table']}
                WHERE {config['id_col']} = :entity_id
            """)
            result = connection.execute(query, {"entity_id": selected_id})
            row = result.fetchone()

            if row:
                return {
                    "status": "exact_match",
                    "data": {
                        "id": row[0],
                        "name": row[1],
                        "type": selected_type,
                        "table": config["table"],
                        "column": config["name_col"]
                    },
                    "message": f"User confirmed: {row[1]}",
                    "source": "user_selection"
                }

    # ===== 階段 1: LIKE 查詢 =====
    print(f"📊 [EntityResolver] Phase 1: LIKE query in database...")
    db = get_mysql_db()
    candidates = []

    with db._engine.connect() as connection:
        # First Pass: With target_types filter
        for config in SEARCH_CONFIGS:
            if target_types and config["type"] not in target_types:
                continue
            results = _search_table(connection, config, keyword)
            candidates.extend(results)

    # 去重：避免同一個 ID 被多次搜出 (例如 brand 和 client 可能來自同一表)
    unique_candidates = []
    seen = set()
    for c in candidates:
        key = (c['type'], c['id'])
        if key not in seen:
            seen.add(key)
            unique_candidates.append(c)

    print(f"📊 [EntityResolver] LIKE query found {len(unique_candidates)} unique results")

    # 策略三: 類型感知優先級 (Type-Aware Exact Match Priority) & 層級過濾 (Hierarchy Filtering)
    
    # 定義父子層級關係
    PARENT_TYPES = {'client', 'brand', 'agency', 'industry', 'sub_industry'}
    CHILD_TYPES = {'campaign', 'contract'}
    
    # 輔助函數: 正規化名稱 (移除常見後綴)
    def _normalize_name(name: str) -> str:
        suffixes = ['股份有限公司', '有限公司', 'company', 'ltd', 'inc', 'corp']
        n = name.strip().lower()
        for s in suffixes:
            n = n.replace(s, '')
        return n.strip()

    normalized_keyword = _normalize_name(keyword)
    
    # 1. 找出完全匹配 (Exact Matches) - 使用正規化名稱比對
    exact_matches = [
        c for c in unique_candidates 
        if _normalize_name(c['name']) == normalized_keyword
    ]
    
    has_exact_match_anchor = False
    
    if exact_matches:
        has_exact_match_anchor = True
        covered_types = set(c['type'] for c in exact_matches)
        print(f"🎯 [EntityResolver] Found exact matches for types: {covered_types}")
        
        filtered_candidates = []
        for c in unique_candidates:
            # 判斷是否為 Exact Match (使用正規化名稱)
            is_exact = _normalize_name(c['name']) == normalized_keyword
            
            if is_exact:
                filtered_candidates.append(c)
            elif c['type'] not in covered_types:
                # 該類型還沒有完全匹配，保留模糊結果 (如: 悠遊卡股份有限公司)
                filtered_candidates.append(c)
            else:
                # 該類型已有完全匹配，丟棄模糊雜訊 (如: 教育部體育署)
                print(f"🗑️ [EntityResolver] Discarding noise: {c['name']} ({c['type']})")
        
        # 2. 層級過濾 (Hierarchy Filtering)
        # 如果結果中包含父層級 (Client/Brand/Agency)，則移除所有子層級 (Campaign/Contract)
        # 避免 SQL 中同時傳入 client_id 和少數幾個 campaign_id 導致查詢範圍被錯誤限縮
        has_parent = any(c['type'] in PARENT_TYPES for c in filtered_candidates)
        if has_parent:
            original_count = len(filtered_candidates)
            filtered_candidates = [c for c in filtered_candidates if c['type'] not in CHILD_TYPES]
            removed_count = original_count - len(filtered_candidates)
            if removed_count > 0:
                print(f"🧹 [EntityResolver] Hierarchy Filter: Removed {removed_count} child entities (campaigns/contracts) because parent entity (client/brand) was found.")

        unique_candidates = filtered_candidates

    # 判斷結果
    if len(unique_candidates) == 1:
        # 只有一筆結果 → 直接返回
        entity = unique_candidates[0]
        msg = f"✅ Found exact match: {entity['name']}"
        
        # [Strategy] Add explicit next-step guidance for Industry types to prevent early stopping
        if entity['type'] in ['industry', 'sub_industry']:
            msg += f". 👉 Next Step: You MUST use `query_industry_format_budget` with {entity['type']}_ids=[{entity['id']}] to get the data."
        elif entity['type'] in ['client', 'brand']:
            msg += f". 👉 Next Step: You MUST use `query_campaign_basic` with {entity['type']}_ids=[{entity['id']}] to get the campaign list."

        return {
            "status": "exact_match",
            "data": entity,
            "message": msg,
            "source": "like_query"
        }
    elif len(unique_candidates) > 1:
        # 策略二修正: 自動合併 (Auto-Merge)
        # 觸發條件:
        # 1. 名字全部一樣 (原有邏輯)
        # 2. OR 剛剛觸發了 Type-Aware Filter (代表我們已經鎖定了特定關鍵字，剩下的都是跨類型的相關實體)
        
        first_name = unique_candidates[0]['name'].strip().lower()
        all_same_name = all(c['name'].strip().lower() == first_name for c in unique_candidates)
        
        if all_same_name or has_exact_match_anchor:
            print(f"✅ [EntityResolver] Auto-merging {len(unique_candidates)} entities. (Same Name: {all_same_name}, Anchored: {has_exact_match_anchor})")
            return {
                "status": "merged_match",
                "data": unique_candidates,
                "message": f"✅ Found {len(unique_candidates)} related entities for '{keyword}'. Merging results.",
                "source": "like_query_merged"
            }

        # 多筆結果且名字不同，且沒有完全匹配的錨點 → 需要使用者確認
        return {
            "status": "needs_confirmation",
            "data": unique_candidates[:20],
            "message": f"⚠️ Found {len(unique_candidates)} matches. Please select one:",
            "source": "like_query"
        }

    # ===== 階段 2: RAG 向量搜尋 =====
    if use_rag:
        print(f"🧠 [EntityResolver] Phase 2: RAG vector search...")
        try:
            rag_service = RagService()
            
            # Map singular types to Qdrant plural types
            type_mapping = {
                "client": "advertisers",
                "agency": "agencies",
                "brand": "brands",
                "industry": "industries",
                "sub_industry": "sub_industries",
                "campaign": "campaigns"
            }
            
            rag_filter = None
            if target_types:
                # Map all target types to their plural forms
                mapped_types = []
                for t in target_types:
                    mapped = type_mapping.get(t, t)
                    if mapped not in mapped_types:
                        mapped_types.append(mapped)
                
                if mapped_types:
                    rag_filter = mapped_types if len(mapped_types) > 1 else mapped_types[0]

            rag_results = rag_service.search(
                query=keyword,
                top_k=10,
                score_threshold=0.85,  # 降低閾值以獲取更多候選結果
                type_filter=rag_filter
            )

            if rag_results:
                print(f"🧠 [EntityResolver] RAG found {len(rag_results)} results")
                # Extract top 3 names for the prompt
                top_names = [r['value'] for r in rag_results[:3]]
                names_str = ", ".join(f"'{n}'" for n in top_names)
                
                return {
                    "status": "rag_results",
                    "data": rag_results,
                    "message": f"⚠️ AMBIGUOUS ENTITY: Found {len(rag_results)} candidates but NO EXACT MATCH. You CANNOT proceed with these results. You MUST pick one of the following names and call `resolve_entity` again with THAT EXACT NAME: {names_str}. ⛔ DO NOT use the original keyword '{keyword}' again.",
                    "source": "rag"
                }
        except Exception as e:
            print(f"⚠️ [EntityResolver] RAG search failed: {e}")

    # ===== 階段 3: 完全找不到 =====
    return {
        "status": "not_found",
        "data": [],
        "message": f"❌ No entities found for '{keyword}' (tried LIKE query and RAG)",
        "source": "none"
    }
