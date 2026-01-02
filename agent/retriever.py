"""
Data Retriever Node for AKC Framework 3.0

Responsibilities:
1. Resolve Entities (Names -> IDs)
2. Execute SQL Queries (MySQL & ClickHouse)
3. Store raw results in state['data_store']
4. Pass control to DataReporter
"""
from typing import Dict, Any, List
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from config.llm import llm
from agent.state import AgentState
from tools.entity_resolver import resolve_entity
from tools.campaign_template_tool import (
    query_campaign_basic,
    query_budget_details,
    query_investment_budget,
    query_execution_budget,
    query_targeting_segments,
    query_ad_formats,
    execute_sql_template,
    query_industry_format_budget
)
from tools.performance_tools import query_performance_metrics, query_format_benchmark
import json
from datetime import datetime

# Tools for Retrieval ONLY (No Pandas)
RETRIEVER_TOOLS = [
    resolve_entity,
    query_campaign_basic,
    query_budget_details,
    query_investment_budget,
    query_execution_budget,
    query_targeting_segments,
    query_ad_formats,
    execute_sql_template,
    query_industry_format_budget,
    query_performance_metrics,
    query_format_benchmark
]

# Bind tools
llm_with_tools = llm.bind_tools(RETRIEVER_TOOLS)

RETRIEVER_SYSTEM_PROMPT = """你是 AKC 智能助手的數據檢索專家 (Data Retriever)。

**你的任務流程 (SOP)**:

**⚠️ 關鍵判斷：何時使用「統計與基準工具」？**
若使用者的問題屬於「全站/產業層級」的「佔比」或「排名」分析，**請優先使用以下高效工具**，並跳過後續的實體解析與活動查詢步驟：

1. **多維度預算佔比 (`query_industry_format_budget`)**:
   - 適用：「某產業的格式分佈」、「某格式的產業分佈」、「某格式的客戶分佈」。
   - **核心參數 `dimension` (決定分析視角)**:
     - 查「產業預算」或「投放哪些格式」→ `dimension='industry'` (大類) 或 `dimension='sub_industry'` (子類，若需要更細緻的產業分析時推薦使用)
     - 查「客戶預算」或「誰投了這個格式」→ `dimension='client'`
     - 查「代理商預算」→ `dimension='agency'`
   - **核心參數 `split_by_format` (決定聚合程度)**:
     - `True` (預設): 顯示格式細節 (例如: 汽車-Banner, 汽車-Video) -> **適用於「所有格式...」或「各格式...」的詳細分析**。
     - `False`: 僅顯示維度總計 (例如: 汽車總額) -> 適用於「純產業排名」且不關心格式時。
   - **核心參數 `primary_view` (決定欄位順序)**:
     - `'dimension'` (預設): 第一欄為產業/客戶。
     - `'format'`: 第一欄為格式。**當使用者問「所有格式投放到的...」或「Banner 投放到的...」時，請務必設為 `'format'`**。
   - **過濾參數**:
     - 若指定特定格式 (如「Banner」)，請設 `format_ids` (需先透過 `resolve_entity` 取得格式 ID)。
   - **範例**:
     - "半年內所有格式投放的產業" (格式視角) → `query_industry_format_budget(dimension='industry', split_by_format=True, primary_view='format', ...)`
     - "汽車產業投了哪些格式" (產業視角) → `query_industry_format_budget(dimension='industry', split_by_format=True, primary_view='dimension', industry_ids=[...])`

2. **全站格式成效 (`query_format_benchmark`)**:
   - 適用：「所有格式的 CTR 排名」、「產業的平均 VTR」。
   - 範例: "半年內所有格式的 CTR 排名" → `query_format_benchmark(start_date=..., end_date=...)`

---

**一般查詢流程 (針對特定實體/Campaign)**:

**⚠️ 關鍵判斷：何時需要實體解析？**
在執行 Step 1 之前，請先判斷使用者查詢的類型：

- **需要實體解析的查詢** (使用 `resolve_entity`):
  - 使用者提到**具體的名稱**，例如：
    - "悠遊卡的預算" (具體客戶名)
    - "台灣虎航的代理商" (具體客戶名)
    - "美妝產業的活動" (具體產業名)
    - "Outstream 格式的分佈" (具體格式名)

- **不需要實體解析的查詢** (直接進入 Step 3):
  - 使用者要求**整體排名/匯總/統計**，例如：
    - "代理商 YTD 認列金額" → 這是要所有代理商的金額，**不需要** `resolve_entity`
    - "前十大客戶的投資" → 這是要排名，**不需要** `resolve_entity`
    - "各產業的成效比較" → 這是要匯總，**不需要** `resolve_entity`
  - 關鍵字識別：「所有」「各」「前X」「Top X」「排名」「匯總」「統計」

1. **實體解析 (Step 1 - 僅在需要時執行)**:
   - **只有在使用者提到具體名稱時**，才使用 `resolve_entity` 將名稱 (如 "悠遊卡") 轉換為 ID。
   - **如果是匯總/排名查詢**，請跳過此步驟，直接進入 Step 3。

2. **獲取活動 (Step 2 - 僅在 Step 1 執行後)**:
   - **取得 ID 後，立刻** 使用 `query_campaign_basic(client_ids=[ID])` 取得該客戶的所有活動列表。

3. **數據蒐集 (Step 3 - 所有查詢都需要)**:
   - 根據使用者需求，呼叫適當的查詢工具：
     - `query_execution_budget`: 查詢「認列金額」或「執行金額」
     - `query_investment_budget`: 查詢「預算」或「進單金額」
     - `query_performance_metrics`: 查詢成效 (必須傳入 `cmp_ids`)
     - `query_targeting_segments`: 查詢受眾
     - `query_ad_formats`: **查詢廣告格式 (⚠️ 當使用者問到「格式」時，這是必須呼叫的工具)**
   - **匯總查詢時的參數設定**：
     - 如果是「代理商」相關查詢，使用 `query_execution_budget` (有 agency_name 欄位)
     - 如果是「產業」相關查詢，使用 `industry_ids` 或 `sub_industry_ids` 參數
     - 如果是「客戶」相關查詢，可以不帶任何過濾條件，讓 Reporter 做聚合
     - **⚠️ 重要 - LIMIT 設定策略**：
       - 當用戶要求「前N名」時，SQL 查詢的 `limit` 應設為 **N × 50**（例如：前20名 → limit=1000）
       - 原因：SQL 返回的是明細記錄，需要足夠的記錄才能聚合出N個分組
       - 一般匯總查詢：設定 `limit=5000`，確保獲取完整數據

**當前日期**: {current_date}

**核心原則 (鐵律)**:
- **ID 絕對優先**: 只要你取得了 `client_id` (例如 1453)，後續所有查詢 **必須** 使用 `client_ids=[1453]`。禁止再使用 `client_names`。
- **防止鬼打牆**: 如果系統提示「已確認實體資訊」，**請不要** 再次呼叫 `resolve_entity`，直接進入 Step 2。
- **成效查詢規範**:
  - 查詢成效 (`query_performance_metrics`) 時，**必須** 傳入 `cmp_ids`。
  - **重要**: 查詢歷史活動成效時，請務必設定寬鬆的時間範圍 (例如 `start_date='2021-01-01'`)，以免因預設時間範圍 (最近 3 個月) 而導致歷史數據遺失。

**結束條件**:
- 當你收集完所有必要的數據 (預算、成效、格式等)，請停止呼叫工具，並簡單回覆：「數據收集完畢，轉交報告者處理。」
"""

def data_retriever_node(state: AgentState) -> Dict[str, Any]:
    """
    Executes retrieval loop and accumulates data in state['data_store'].
    """
    # Initialize context
    now = datetime.now()
    current_date = now.strftime("%Y-%m-%d")

    routing_context = state.get("routing_context", {})
    original_query = routing_context.get("original_query", "")
    entity_keywords = routing_context.get("entity_keywords", [])

    # Initialize or Load Data Store
    data_store = state.get("data_store") or {}
    resolved_entities = state.get("resolved_entities") or []
    execution_logs = state.get("debug_logs") or []

    print(f"DEBUG [Retriever] Starting retrieval for: {original_query[:50]}...")

    # Build Messages
    messages = [
        SystemMessage(content=RETRIEVER_SYSTEM_PROMPT.format(current_date=current_date)),
        HumanMessage(content=f"查詢請求: {original_query}\n實體提示: {entity_keywords}")
    ]

    # Re-inject resolved entities context if any
    if resolved_entities:
        context_lines = []
        for e in resolved_entities:
            e_type = e.get('type', 'unknown')
            e_id = e.get('id')
            e_name = e.get('name')
            context_lines.append(f"- {e_type.upper()} ID: {e_id} (名稱: {e_name})")

        entity_context = "已確認的實體資訊：\n" + "\n".join(context_lines)
        messages.append(SystemMessage(content=entity_context))

    # Agent Loop
    tool_call_history = set()

    for i in range(10): # Max 10 steps for retrieval
        print(f"DEBUG [Retriever] Step {i+1}")
        response = llm_with_tools.invoke(messages)
        messages.append(response)

        if not response.tool_calls:
            print("DEBUG [Retriever] No more tool calls. Retrieval finished.")
            break

        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            args = tool_call["args"]

            # 1. Skip if duplicate call
            call_key = f"{tool_name}:{json.dumps(args, sort_keys=True)}"
            if call_key in tool_call_history:
                print(f"DEBUG [Retriever] Skipping duplicate call: {call_key}")
                messages.append(ToolMessage(tool_call_id=tool_call["id"], content="Notice: This query was already executed. Skipping."))
                continue
            tool_call_history.add(call_key)

            # Execute
            tool_map = {t.name: t for t in RETRIEVER_TOOLS}
            func = tool_map.get(tool_name)

            if not func:
                messages.append(ToolMessage(tool_call_id=tool_call["id"], content="Error: Tool not found"))
                continue

            try:
                print(f"DEBUG [Retriever] Calling {tool_name} with {args}")
                result = func.invoke(args)

                # 2. Logic to store data (with Deduplication)
                if isinstance(result, dict) and "data" in result:
                    data = result.get("data")
                    if data and isinstance(data, list) and len(data) > 0:
                        if tool_name not in data_store:
                            data_store[tool_name] = []

                        # Deduplicate: Only add rows that aren't already there
                        existing_data_str = {json.dumps(row, sort_keys=True, default=str) for row in data_store[tool_name]}
                        new_rows = []
                        for row in data:
                            row_str = json.dumps(row, sort_keys=True, default=str)
                            if row_str not in existing_data_str:
                                new_rows.append(row)
                                existing_data_str.add(row_str)

                        if new_rows:
                            data_store[tool_name].extend(new_rows)
                            print(f"DEBUG [Retriever] Stored {len(new_rows)} NEW rows from {tool_name}")
                        else:
                            print(f"DEBUG [Retriever] All rows from {tool_name} were duplicates. Skipped.")

                        # Handle Entity Resolution specifically
                        if tool_name == "resolve_entity":
                            status = result.get("status")

                            # ===== Handle Needs Confirmation =====
                            if status == "needs_confirmation":
                                candidates = result.get("data", [])
                                if candidates:
                                    # Auto-select the first candidate to avoid blocking the flow
                                    # In production, this would be where user selection happens
                                    selected = candidates[0]
                                    print(f"⚠️ [Retriever] Found {len(candidates)} candidates, auto-selecting: {selected.get('name')}")

                                    # Convert to merged_match format so the flow continues
                                    result = {
                                        "status": "merged_match",
                                        "data": candidates,  # Return all candidates for potential future use
                                        "message": f"⚠️ Auto-selected: {selected.get('name')} from {len(candidates)} candidates",
                                        "source": "auto_selection"
                                    }
                                    # Update status variable so the next elif will match
                                    status = "merged_match"

                            # ===== Handle Exact Match / Merged Match =====
                            if status in ["exact_match", "merged_match"]:
                                entity = result.get("data")
                                if isinstance(entity, list):
                                    resolved_entities.extend(entity)
                                    # Create entity-type-aware guidance for multiple entities
                                    guidance = []
                                    entity_ids = []
                                    entity_types = set()
                                    for e in entity:
                                        guidance.append(f"{e.get('name')} (ID: {e.get('id')})")
                                        entity_ids.append(e.get('id'))
                                        entity_types.add(e.get('type'))

                                    # Determine appropriate parameter based on entity type
                                    if "industry" in entity_types:
                                        param_name = "industry_ids"
                                    elif "sub_industry" in entity_types:
                                        param_name = "sub_industry_ids"
                                    elif "campaign" in entity_types:
                                        # Skip Step 2, already have campaign IDs
                                        guide_msg = f"✅ 已成功解析實體: {', '.join(guidance)}。\n👉 下一步 (Step 3): 已取得 campaign IDs，請直接查詢成效/預算/格式等數據，使用參數 `campaign_ids={json.dumps(entity_ids)}`。"
                                        messages.append(ToolMessage(tool_call_id=tool_call["id"], content=guide_msg))
                                        continue
                                    else:  # client, brand, agency
                                        param_name = "client_ids"

                                    guide_msg = f"✅ 已成功解析實體: {', '.join(guidance)}。\n👉 下一步 (Step 2): 請立刻呼叫 `query_campaign_basic`，並使用參數 `{param_name}={json.dumps(entity_ids)}`。\n📋 接下來 (Step 3): 取得活動列表後，請根據使用者查詢需求，呼叫 `query_ad_formats` (查詢格式) 和 `query_performance_metrics` (查詢成效數據)。"
                                    messages.append(ToolMessage(tool_call_id=tool_call["id"], content=guide_msg))
                                else:
                                    resolved_entities.append(entity)
                                    # Create entity-type-aware guidance for single entity
                                    e_id = entity.get('id')
                                    e_name = entity.get('name')
                                    e_type = entity.get('type')

                                    # Determine appropriate parameter based on entity type
                                    if e_type == "industry":
                                        param_name = "industry_ids"
                                    elif e_type == "sub_industry":
                                        param_name = "sub_industry_ids"
                                    elif e_type == "campaign":
                                        # Skip Step 2, already have campaign ID
                                        guide_msg = f"✅ 已成功解析實體: {e_name} (ID: {e_id})。\n👉 下一步 (Step 3): 已取得 campaign ID，請直接查詢成效/預算/格式等數據，使用參數 `campaign_ids=[{e_id}]`。"
                                        messages.append(ToolMessage(tool_call_id=tool_call["id"], content=guide_msg))
                                        continue
                                    else:  # client, brand, agency
                                        param_name = "client_ids"

                                    guide_msg = f"✅ 已成功解析實體: {e_name} (ID: {e_id})。\n👉 下一步 (Step 2): 請立刻呼叫 `query_campaign_basic`，並使用參數 `{param_name}=[{e_id}]`。\n📋 接下來 (Step 3): 取得活動列表後，請根據使用者查詢需求，呼叫 `query_ad_formats` (查詢格式) 和 `query_performance_metrics` (查詢成效數據)。"
                                    messages.append(ToolMessage(tool_call_id=tool_call["id"], content=guide_msg))

                            # ===== Handle RAG Results =====
                            elif status == "rag_results":
                                rag_data = result.get("data", [])
                                if rag_data and isinstance(rag_data, list):
                                    # RAG 返回的是 {value, source, table, filter_type, score} 格式
                                    # 選擇最高分的結果並直接使用名稱查詢

                                    # 從 filter_type 映射到實體類型和參數名稱
                                    filter_type_map = {
                                        "sub_industries": ("sub_industry", "sub_industry_ids"),
                                        "industries": ("industry", "industry_ids"),
                                        "advertisers": ("client", "client_ids"),
                                        "brands": ("brand", "client_ids"),
                                        "agencies": ("agency", "client_ids"),
                                        "campaigns": ("campaign", "campaign_ids")
                                    }

                                    # 智能選擇結果：優先選擇 industry/sub_industry 類型
                                    # 原因：產業查詢通常更符合使用者意圖，且可以直接進入數據查詢階段
                                    priority_types = ['industries', 'sub_industries']
                                    priority_results = [r for r in rag_data if r.get('filter_type') in priority_types]

                                    if priority_results:
                                        # 從優先類型中選擇最高分
                                        top_result = max(priority_results, key=lambda x: x.get('score', 0))
                                        print(f"DEBUG [Retriever] Smart RAG selection: Prioritized {top_result.get('filter_type')} type")
                                    else:
                                        # 沒有優先類型，回退到全局最高分
                                        top_result = max(rag_data, key=lambda x: x.get('score', 0))
                                        print(f"DEBUG [Retriever] Smart RAG selection: Fallback to highest score")

                                    filter_type = top_result.get('filter_type')

                                    if filter_type in filter_type_map:
                                        entity_type, param_name = filter_type_map[filter_type]
                                        entity_value = top_result.get('value')

                                        # 改進的 RAG 引導策略：
                                        # 1. 如果是 industry/sub_industry，可以直接使用名稱查詢（不需要 ID）
                                        # 2. 否則，引導 LLM 再次調用 resolve_entity

                                        if entity_type in ["industry", "sub_industry"]:
                                            # 產業類型：先嘗試獲取精確 ID，如果失敗則直接查詢數據
                                            guide_msg = f"🔍 RAG 找到相關產業: {entity_value} (類型: {entity_type}, 分數: {top_result.get('score'):.2f})。\n\n👉 **CRITICAL - 請立即執行以下步驟**：\n\n**Step 1**: 嘗試取得精確 ID（單次嘗試）\n```\nresolve_entity(keyword='{entity_value}', target_types=['{entity_type}'])\n```\n\n**Step 2**: 無論 Step 1 成功與否，立即查詢活動數據\n```\nquery_campaign_basic()  # 使用 Step 1 取得的 industry_ids 或 sub_industry_ids\n```\n\n**Step 3**: 從 Step 2 結果提取 campaign_ids，然後**依照使用者查詢需求**立即呼叫：\n\n⚠️ **必須根據使用者查詢關鍵字決定要呼叫哪些工具**：\n\n- 如果提到「格式」「廣告格式」「format」 → 必須呼叫：\n```\nquery_ad_formats(campaign_ids=[...])\n```\n\n- 如果提到「預算」「投資金額」「investment」 → 必須呼叫：\n```\nquery_investment_budget(campaign_ids=[...])\n```\n\n- 如果提到「認列金額」「執行金額」「execution」 → 必須呼叫：\n```\nquery_execution_budget(campaign_ids=[...])\n```\n\n- 如果提到「成效」「CTR」「VTR」「ER」「點擊率」「觀看率」「performance」 → 必須呼叫：\n```\nquery_performance_metrics(campaign_ids=[...])\n```\n\n- 如果提到「受眾」「數據鎖定」「targeting」「segment」 → 必須呼叫：\n```\nquery_targeting_segments(campaign_ids=[...])\n```\n\n🚨 **範例**：\n如果使用者問「汽車產業成效最好的格式，以及他使用了什麼數據鎖定」，你必須呼叫：\n1. `query_ad_formats` (因為提到「格式」)\n2. `query_performance_metrics` (因為提到「成效」)\n3. `query_targeting_segments` (因為提到「數據鎖定」)\n\n🚨 **禁止事項**：\n- 不要重複呼叫 `resolve_entity` 超過 2 次\n- 不要使用除 '{entity_value}' 以外的其他關鍵字\n- 不要漏掉使用者查詢中明確提到的數據類型"
                                            messages.append(ToolMessage(tool_call_id=tool_call["id"], content=guide_msg))
                                        else:
                                            # 其他類型（client, brand, agency）：需要精確 ID
                                            guide_msg = f"🔍 RAG 找到相關實體: {entity_value} (類型: {entity_type}, 分數: {top_result.get('score'):.2f})。\n👉 下一步: 請再次呼叫 `resolve_entity`，使用參數 `keyword='{entity_value}'` 和 `target_types=['{entity_type}']` 來取得精確的 ID。"
                                            messages.append(ToolMessage(tool_call_id=tool_call["id"], content=guide_msg))
                                    else:
                                        # 無法識別的 filter_type，返回所有結果讓 LLM 判斷
                                        candidates_summary = "\n".join([f"- {r.get('value')} ({r.get('filter_type')}, 分數: {r.get('score'):.2f})" for r in rag_data[:5]])
                                        guide_msg = f"🔍 RAG 找到 {len(rag_data)} 個相關結果：\n{candidates_summary}\n\n👉 請根據使用者的查詢需求，選擇最相關的實體，並使用 `resolve_entity` 取得精確 ID。"
                                        messages.append(ToolMessage(tool_call_id=tool_call["id"], content=guide_msg))

                # Log
                execution_logs.append({
                    "step": "retrieval",
                    "tool": tool_name,
                    "args": args,
                    "row_count": len(result.get("data", [])) if isinstance(result, dict) else 0
                })

                # [NEW] Add guidance for query_campaign_basic results
                if tool_name == "query_campaign_basic" and isinstance(result, dict) and result.get("data"):
                    campaign_ids = [row.get('campaign_id') for row in result.get("data", []) if row.get('campaign_id')]
                    if campaign_ids:
                        guide_msg = f"\n\n✅ 已取得 {len(campaign_ids)} 個活動的基本資料。\n👉 下一步 (Step 3): 請根據使用者查詢需求，呼叫以下工具：\n- `query_ad_formats(campaign_ids={json.dumps(campaign_ids[:10])})` - 查詢廣告格式\n- `query_performance_metrics(cmp_ids={json.dumps(campaign_ids[:10])})` - 查詢成效數據"
                        content = json.dumps(result, ensure_ascii=False, default=str) + guide_msg
                    else:
                        content = json.dumps(result, ensure_ascii=False, default=str)
                else:
                    content = json.dumps(result, ensure_ascii=False, default=str)

                messages.append(ToolMessage(tool_call_id=tool_call["id"], content=content))

            except Exception as e:
                error_msg = f"Error executing {tool_name}: {e}"
                print(f"ERROR [Retriever] {error_msg}")
                messages.append(ToolMessage(tool_call_id=tool_call["id"], content=error_msg))

    return {
        "data_store": data_store,
        "resolved_entities": resolved_entities,
        "debug_logs": execution_logs
    }
