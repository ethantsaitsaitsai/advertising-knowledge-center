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
    id_finder,
    query_campaign_basic,
    query_investment_budget,
    query_execution_budget,
    query_targeting_segments,
    execute_sql_template,
    query_industry_format_budget
)
from tools.performance_tools import query_unified_performance, query_format_benchmark
import json
from datetime import datetime

# Tools for Retrieval ONLY (No Pandas)
RETRIEVER_TOOLS = [
    resolve_entity,
    id_finder,
    query_campaign_basic,
    query_investment_budget,
    query_execution_budget,
    query_targeting_segments,
    execute_sql_template,
    query_industry_format_budget,
    query_unified_performance,
    query_format_benchmark
]

# Bind tools
llm_with_tools = llm.bind_tools(RETRIEVER_TOOLS)

RETRIEVER_SYSTEM_PROMPT = """你是 AKC 智能助手的數據檢索專家 (Data Retriever)。

**你的核心任務**:
負責從資料庫中檢索原始數據。你**不負責**計算、合併或畫表，這些是 Reporter 的工作。你的目標是精準地找出相關的「ID」，並利用這些 ID 撈取詳細屬性。

**標準作業流程 (SOP)**:

**Step 1: 探索與定位 (Discovery)**
-當使用者提到特定的客戶、產業、格式或時間範圍時，**首先**呼叫 `id_finder`。
- `id_finder` 是你的核心導航器，它會回傳符合條件的所有 `cue_list_id` (合約), `campaign_id` (活動), 和 `plaid` (版位)。
- **注意**: 若使用者給的是「名稱」(如 "悠遊卡")，請先用 `resolve_entity` 轉成 ID，再傳給 `id_finder`。

**Step 2: 數據撈取 (Data Fetching)**
- 取得 ID 後，根據使用者需求呼叫對應的詳細工具 (可平行呼叫)：
  - **想看預算/進單金額/格式配置** → 呼叫 `query_investment_budget(cue_list_ids=[...])`
  - **想看執行金額/實際花費** → 呼叫 `query_execution_budget(plaids=[...])`
  - **想看成效 (CTR/VTR/ER)** → 呼叫 `query_unified_performance(plaids=[...], group_by=['ad_format_type'])`
  - **想看受眾/數據鎖定** → 呼叫 `query_targeting_segments(plaids=[...])`
  - **想看活動詳細資訊 (名稱/日期)** → 呼叫 `query_campaign_basic(campaign_ids=[...])`

**特殊場景**:
- **產業/大盤統計** (如 "汽車產業的格式佔比")：
  - 不需要查 ID，直接使用 `query_industry_format_budget(dimension='industry', ...)`。
  - **警告**: 請勿將此工具用於查詢特定客戶的明細，它只適合看大趨勢。

**工具參數指南**:
- `id_finder`: 必須提供 `start_date` 與 `end_date`。
- `query_unified_performance`: 建議使用 `plaids` 進行精準過濾。`group_by` 參數依需求設定 (如 `['campaign_name', 'ad_format_type']`)。
- `query_investment_budget`: **必須** 使用 `cue_list_ids`。
- `query_execution_budget`: **必須** 使用 `plaids`。

**當前日期**: {current_date}

**核心原則 (鐵律)**:
- **ID 為王**: 拿到 ID 後，後續查詢一律使用 ID (List[int])，嚴禁使用名稱。
- **避免濫用**: 不要對同一個 ID 重複呼叫相同的工具。
- **精準回應**: 當你收集完所有必要數據後，請回覆：「數據收集完畢，轉交報告者處理。」
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
                            if status in ["exact_match", "merged_match"]:
                                entity = result.get("data")
                                if isinstance(entity, list):
                                    resolved_entities.extend(entity)
                                else:
                                    resolved_entities.append(entity)
                                
                                # Guide: Use id_finder after resolution
                                guide_msg = f"✅ 已解析實體。下一步: 請呼叫 `id_finder`，傳入 `client_ids` (或其他對應 ID) 以及查詢的時間範圍 `start_date`, `end_date`。"
                                messages.append(ToolMessage(tool_call_id=tool_call["id"], content=guide_msg))
                                continue

                # Log
                execution_logs.append({
                    "step": "retrieval",
                    "tool": tool_name,
                    "args": args,
                    "row_count": len(result.get("data", [])) if isinstance(result, dict) else 0
                })

                # [NEW] Add guidance for id_finder results
                if tool_name == "id_finder" and isinstance(result, dict) and result.get("data"):
                    rows = result.get("data", [])
                    # Extract ID lists
                    cue_list_ids = list(set(r['cue_list_id'] for r in rows if r.get('cue_list_id')))
                    campaign_ids = list(set(r['campaign_id'] for r in rows if r.get('campaign_id')))
                    plaids = list(set(r['plaid'] for r in rows if r.get('plaid')))
                    
                    if plaids:
                        guide_msg = f"\n\n✅ 已找到相關 IDs (共 {len(rows)} 筆)。\n👉 下一步: 請根據需求平行呼叫以下工具：\n"
                        guide_msg += f"- `query_investment_budget(cue_list_ids={json.dumps(cue_list_ids[:20])})` (查預算)\n"
                        guide_msg += f"- `query_execution_budget(plaids={json.dumps(plaids[:20])})` (查執行金額)\n"
                        guide_msg += f"- `query_unified_performance(plaids={json.dumps(plaids[:20])}, group_by=['campaign_name'])` (查成效)\n"
                        guide_msg += f"- `query_targeting_segments(plaids={json.dumps(plaids[:20])})` (查受眾)\n"
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