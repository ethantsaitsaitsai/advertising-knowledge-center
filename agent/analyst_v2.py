"""
AKC Framework 3.0 - Data Analyst Agent (V2)
Implemented using langchain.agents.create_agent
"""
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

from langchain.agents import create_agent, AgentState
from langchain.agents.middleware import wrap_tool_call, dynamic_prompt, ModelRequest
from langchain.messages import SystemMessage, ToolMessage, AIMessage, HumanMessage
from langchain_core.messages import BaseMessage

from config.llm import llm
from agent.state import AgentState as ProjectAgentState
from tools.entity_resolver import resolve_entity
from tools.campaign_template_tool import (
    query_campaign_basic,
    query_budget_details,
    query_investment_budget,
    query_execution_budget,
    query_targeting_segments,
    query_ad_formats,
    execute_sql_template,
    query_industry_format_budget,
    query_media_placements
)
from tools.performance_tools import (
    query_format_benchmark,
    query_unified_performance,
    query_unified_dimensions
)

# Setup logging
logger = logging.getLogger("akc.analyst")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

# Tools for Retrieval
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
    query_media_placements,
    query_format_benchmark,
    query_unified_performance,
    query_unified_dimensions
]

RETRIEVER_SYSTEM_PROMPT = """你是 AKC 智能助手的數據檢索專家 (Data Retriever)。

**當前日期**: {current_date}

**系統指定查詢範圍 (Strict Constraints)**:
- **開始日期**: {start_date}
- **結束日期**: {end_date}
- **強制執行**: 即使使用者的問題中看起來有日期 (例如 "2023年")，若上方指定了日期範圍，**請務必使用系統指定日期**。

**核心任務**: 根據使用者需求，選擇正確的資料源 (MySQL 或 ClickHouse) 獲取數據。

---

### 🚦 雙軌分流策略 (Dual-Track Strategy)

**原則：成效與探索走 ClickHouse (快)，錢與設定走 MySQL (準)。**

#### 1. 成效與維度探索 (Performance & Discovery) → 🚀 使用 ClickHouse
當查詢涉及：**點擊、曝光、CTR、產品線 (Product Line)、格式清單、版位清單**。
- **工具**:
  - `query_unified_performance`: **(主要工具)** 查成效 (Impressions, Clicks, CTR)。
  - `query_unified_dimensions`: 查清單 (有哪些產品線？有哪些格式？)。
- **優勢**: 速度快，支援產品線維度。

#### 2. 金額與設定 (Budget & Setup) → 💰 使用 MySQL
當查詢涉及：**預算、金額 (Cost/Investment)、受眾 (Targeting)、合約狀態**。
- **工具**:
  - `query_budget_details`: 查活動總預算。
  - `query_industry_format_budget`: 查產業/客戶的預算佔比 (Share)。
  - `query_targeting_segments`: 查受眾設定。
  - `query_investment_budget`: 查詳細進單金額。
- **限制**: 不支援產品線維度。

#### 3. 混合需求 (Hybrid) → 🔗 雙邊查詢 + Pandas 合併
當使用者同時問「成效」與「預算」時 (例如：各產品線的 CPC？)。
- **執行步驟**:
  1. 呼叫 `query_unified_performance` 取得成效 (含 `plaid` 或 `cmpid`)。
  2. 呼叫 `query_media_placements` (或相關工具) 取得預算 (含 `placement_id` 或 `campaign_id`)。
  3. **(關鍵)**: 停止工具呼叫，讓 Reporter 使用 Pandas 將兩份數據依據 ID (`plaid` = `placement_id`) 合併計算。

---

### 🛠️ 工具選擇指南 (SOP)

**情境 A: 「全站」或「產業」層級分析**

1. **問「預算佔比」或「金額排名」**:
   - ⚡️ **直接使用** `query_industry_format_budget(dimension='industry'|'client')`。
   - 不要查 Campaign List，也不要查 ClickHouse。

2. **問「成效 (CTR/VTR)」或「產品線表現」**:
   - ⚡️ **直接使用** `query_unified_performance(group_by=['product_line']...)`。
   - 若需特定產業，傳入 `one_categories=['Automotive']` (需先確認正確名稱或 ID)。

3. **問「有哪些...」 (探索清單)**:
   - ⚡️ **直接使用** `query_unified_dimensions(dimensions=['product_line'])`。

**情境 B: 「特定客戶/實體」分析 (例如: Nike)**

1. **Step 1: 實體解析 (必須)**
   - 使用 `resolve_entity(keyword='Nike')` 取得 `client_id`。

2. **Step 2: 取得 Campaign IDs (關鍵)**
   - ⚠️ **ClickHouse 字典可能會有延遲或缺漏，請務必先從 MySQL 獲取精確 ID。**
   - **優先使用** `query_campaign_basic(client_ids=[id], start_date=..., end_date=...)`。
   - 這會回傳該客戶在指定期間內的所有 `campaign_id`。

3. **Step 3: 根據需求分流**
   - **查成效/格式/產品線**:
     - `query_unified_performance(cmpids=[...], group_by=['ad_format_type', 'product_line'])`。
     - **注意**: 請將 Step 2 拿到的 `campaign_id` 列表傳入 `cmpids` 參數。這是最標準的做法。
   
   - **查細部版位 (Deep Dive) 或 數據鎖定成效**:
     - 若用戶問到「版位表現」或「數據鎖定成效」(Targeting Performance)：
       1. 呼叫 `query_media_placements(campaign_ids=[...])` 取得 `plaids` 與 `placement_id`。
       2. 呼叫 `query_unified_performance`：
          - **必須包含** `group_by=['ad_format_type', 'plaid']` (關鍵：保留 plaid 以便與 Targeting 對接)。
          - 傳入 `plaids=[...]` 進行過濾。
       3. 呼叫 `query_targeting_segments(campaign_ids=[...])`。

   - **查預算/花費**:
     - `query_investment_budget(client_ids=[id])` (看進單) 或 `query_execution_budget` (看執行)。
   - **查受眾/設定**:
     - 直接 `query_targeting_segments(campaign_ids=[...])`。

**情境 C: 混合計算 (例如: Nike 的產品線 CPC)**
   1. `query_campaign_basic` (拿 cmpids)
   2. `query_unified_performance(cmpids=[...])` (拿 Clicks)
   3. `query_investment_budget(client_ids=[id])` (拿 Budget)
   4. **結束工具呼叫**。 (Reporter 會處理 `Budget / Clicks`)

---

**⚠️ ID 使用鐵律**:
- ClickHouse 工具的 ID 參數為: `client_ids`, `product_line_ids`, `plaids` (對應 MySQL placement_id), `cmpids` (對應 MySQL campaign_id)。
- 只要 `resolve_entity` 拿到 ID，就必須優先傳入 ID 參數，不要傳 Name。

**結束條件**:
-當必要的「成效面」與「金額面」數據都拿到後，請停止。
"""

@dynamic_prompt
def retriever_dynamic_prompt(request: ModelRequest) -> str:
    """Injects current date, date range, and resolved entities into the system prompt."""
    now = datetime.now()
    current_date = now.strftime("%Y-%m-%d")
    
    # Get date range from routing_context
    routing_context = request.state.get("routing_context", {})
    start_date = routing_context.get("start_date") or "2021-01-01"
    end_date = routing_context.get("end_date") or current_date
    
    base_prompt = RETRIEVER_SYSTEM_PROMPT.format(
        current_date=current_date,
        start_date=start_date,
        end_date=end_date
    )
    
    # In-context learning for resolved entities
    resolved_entities = request.state.get("resolved_entities", [])
    if resolved_entities:
        context_lines = []
        for e in resolved_entities:
            e_type = e.get('type', 'unknown')
            e_id = e.get('id')
            e_name = e.get('name')
            context_lines.append(f"- {e_type.upper()} ID: {e_id} (名稱: {e_name})")

        entity_context = "\n\n已確認的實體資訊：\n" + "\n".join(context_lines)
        return base_prompt + entity_context
    
    return base_prompt

@wrap_tool_call
def retriever_tool_middleware(request: Any, handler):
    """
    Middleware to handle:
    1. Data storage in state['data_store']
    2. Custom guidance for Entity Resolution and Campaign queries
    3. Debug logging
    4. Force Date Override
    """
    tool_call = request.tool_call
    tool_name = tool_call["name"]
    args = tool_call["args"]
    state = request.state
    
    # Initialize state fields if needed
    if "data_store" not in state or state["data_store"] is None:
        state["data_store"] = {}
    if "debug_logs" not in state or state["debug_logs"] is None:
        state["debug_logs"] = []
    if "resolved_entities" not in state or state["resolved_entities"] is None:
        state["resolved_entities"] = []

    # [NEW] Force Date Override
    if state.get("routing_context"):
        logger.info(f"Routing Context: {state.get('routing_context')}")
        system_start = state["routing_context"].get("start_date")
        system_end = state["routing_context"].get("end_date")
        
        if system_start and "start_date" in args:
            if args["start_date"] != system_start:
                logger.warning(f"Force overriding start_date: {args['start_date']} -> {system_start}")
                args["start_date"] = system_start
                
        if system_end and "end_date" in args:
            if args["end_date"] != system_end:
                logger.warning(f"Force overriding end_date: {args['end_date']} -> {system_end}")
                args["end_date"] = system_end

    try:
        # Execute tool
        result = handler(request)
        
        # Extract raw data from result
        raw_result = None
        if isinstance(result, ToolMessage):
            content = result.content
            try:
                raw_result = json.loads(content)
            except:
                try:
                    import ast
                    import re
                    cleaned = re.sub(r"Decimal\('([^']+)'\)", r"\1", content)
                    cleaned = re.sub(r"datetime\.date\((\d+), (\d+), (\d+)\)", r"'\1-\2-\3'", cleaned)
                    cleaned = re.sub(r"datetime\.datetime\((\d+), (\d+), (\d+),? ?(\d+)?,? ?(\d+)?,? ?(\d+)?\)", 
                                     lambda m: "'" + m.group(1) + "-" + m.group(2) + "-" + m.group(3) + "'", cleaned)
                    
                    raw_result = ast.literal_eval(cleaned)
                except Exception as parse_e:
                    logger.debug(f"Failed to parse content for {tool_name}: {parse_e}")
        elif isinstance(result, dict):
            raw_result = result
            
        if raw_result and isinstance(raw_result, dict):
            # 1. Logic to store data (with Deduplication)
            if "data" in raw_result:
                data = raw_result.get("data")
                if data and isinstance(data, list) and len(data) > 0:
                    if tool_name not in state["data_store"]:
                        state["data_store"][tool_name] = []

                    # Deduplicate
                    try:
                        existing_data_str = {json.dumps(row, sort_keys=True, default=str) for row in state["data_store"][tool_name]}
                        new_rows = []
                        for row in data:
                            row_str = json.dumps(row, sort_keys=True, default=str)
                            if row_str not in existing_data_str:
                                new_rows.append(row)
                                existing_data_str.add(row_str)

                        if new_rows:
                            state["data_store"][tool_name].extend(new_rows)
                            logger.info(f"Stored {len(new_rows)} rows in data_store for {tool_name}")
                    except Exception as e:
                        logger.error(f"Deduplication failed: {e}")
                        state["data_store"][tool_name].extend(data)
            
            # 2. Handle Entity Resolution specifically for state update
            if tool_name == "resolve_entity":
                status = raw_result.get("status")
                if status in ["exact_match", "merged_match"]:
                    entity = raw_result.get("data")
                    if isinstance(entity, list):
                        state["resolved_entities"].extend(entity)
                    else:
                        state["resolved_entities"].append(entity)
                logger.info(f"Updated resolved_entities: {len(state['resolved_entities'])}")

            # 3. Add guidance and convert to valid JSON
            def json_default(obj):
                import decimal
                import datetime
                if isinstance(obj, decimal.Decimal):
                    return float(obj)
                if isinstance(obj, (datetime.date, datetime.datetime)):
                    return obj.isoformat()
                return str(obj)

            content = json.dumps(raw_result, ensure_ascii=False, default=json_default)
            
            if tool_name == "query_campaign_basic" and raw_result.get("data"):
                campaign_ids = [row.get('campaign_id') for row in raw_result.get("data", []) if row.get('campaign_id')]
                if campaign_ids:
                    content += f"\n\n✅ 已取得 {len(campaign_ids)} 個活動的基本資料。\n👉 下一步: 請查詢成效/預算等數據。"
            
            return ToolMessage(tool_call_id=tool_call["id"], content=content)

        return result
    except Exception as e:
        logger.error(f"Tool error: {e}")
        return ToolMessage(tool_call_id=tool_call["id"], content=json.dumps({"error": str(e)}))

# Create the agent
retriever_agent = create_agent(
    model=llm,
    tools=RETRIEVER_TOOLS,
    middleware=[retriever_dynamic_prompt, retriever_tool_middleware],
    state_schema=ProjectAgentState
)

def _check_performance_tools_needed(state: ProjectAgentState, result: Dict[str, Any]) -> Dict[str, bool]:
    original_query = state.get("routing_context", {}).get("original_query", "").lower()
    format_keywords = ["格式", "format", "banner", "影音", "廣告形式"]
    has_format = any(kw in original_query for kw in format_keywords)
    performance_keywords = ["ctr", "vtr", "er", "點擊率", "觀看率", "互動率", "成效", "排名", "平均"]
    has_performance = any(kw in original_query for kw in performance_keywords)
    client_keywords = ["客戶", "client", "廣告主", "品牌"]
    has_client = any(kw in original_query for kw in client_keywords)
    data_store = result.get("data_store", {})
    has_benchmark = "query_format_benchmark" in data_store
    has_performance_tool = "query_unified_performance" in data_store
    has_campaign_basic = "query_campaign_basic" in data_store
    needs = {
        "needs_benchmark": False,
        "needs_performance": False,
        "needs_campaign_basic": False
    }
    if has_format and has_performance:
        if has_client:
            needs["needs_performance"] = not has_performance_tool
            needs["needs_campaign_basic"] = not has_campaign_basic
        else:
            needs["needs_benchmark"] = not has_benchmark
    return needs

def data_retriever_v2_node(state: ProjectAgentState) -> Dict[str, Any]:
    initial_messages_count = len(state.get("messages", []))
    initial_logs_count = len(state.get("debug_logs", []))
    
    # --- [CRITICAL FIX] Reset data_store for new turn ---
    # To prevent hallucinations from previous query results, we start with a fresh store.
    # Note: We keep resolved_entities as they might be useful for follow-up questions.
    state["data_store"] = {}
    
    sanitized_messages = []
    for msg in state.get("messages", []):
        if isinstance(msg, dict):
            msg_type = msg.get("type", "human")
            content = msg.get("content", "")
            if msg_type == "human":
                sanitized_messages.append(HumanMessage(content=content))
            elif msg_type == "ai":
                sanitized_messages.append(AIMessage(content=content))
            elif msg_type == "system":
                sanitized_messages.append(SystemMessage(content=content))
            elif msg_type == "tool":
                tool_call_id = msg.get("tool_call_id", "unknown")
                sanitized_messages.append(ToolMessage(content=content, tool_call_id=tool_call_id))
            else:
                sanitized_messages.append(HumanMessage(content=str(msg)))
        elif isinstance(msg, BaseMessage):
            if msg.type == "human":
                sanitized_messages.append(HumanMessage(content=msg.content))
            elif msg.type == "ai":
                sanitized_messages.append(AIMessage(content=msg.content))
            elif msg.type == "system":
                sanitized_messages.append(SystemMessage(content=msg.content))
            elif msg.type == "tool":
                sanitized_messages.append(msg)
            else:
                sanitized_messages.append(HumanMessage(content=msg.content))
        else:
            sanitized_messages.append(HumanMessage(content=str(msg)))
    local_state = state.copy()
    local_state["messages"] = sanitized_messages
    result = retriever_agent.invoke(local_state)
    final_messages = result.get("messages", [])
    new_messages = final_messages[len(sanitized_messages):]
    final_logs = result.get("debug_logs", [])
    new_logs = final_logs[initial_logs_count:]
    needs = _check_performance_tools_needed(state, result)
    routing_context = state.get("routing_context", {})
    start_date = routing_context.get("start_date", "2021-01-01")
    end_date = routing_context.get("end_date", datetime.now().strftime("%Y-%m-%d"))
    if "data_store" not in result:
        result["data_store"] = {}
    if needs.get("needs_benchmark"):
        logger.warning("Detected missing query_format_benchmark call. Auto-invoking...")
        try:
            campaign_data = result.get("data_store", {}).get("query_campaign_basic", [])
            cmp_ids = [row.get('campaign_id') for row in campaign_data if row.get('campaign_id')] if campaign_data else None
            invoke_params = {"start_date": start_date, "end_date": end_date}
            if cmp_ids:
                invoke_params["cmp_ids"] = cmp_ids
                logger.warning(f"Auto-invoking benchmark with {len(cmp_ids)} campaign IDs")
            else:
                logger.warning("Auto-invoking benchmark for 全站查詢")
            benchmark_result = query_format_benchmark.invoke(invoke_params)
            if benchmark_result.get("status") == "success" and benchmark_result.get("data"):
                result["data_store"]["query_format_benchmark"] = benchmark_result.get("data", [])
                logger.info(f"Auto-invoked query_format_benchmark, got {len(benchmark_result.get('data', []))} rows")
        except Exception as e:
            logger.warning(f"Auto-invoke benchmark failed: {e}")
    if needs.get("needs_performance") or needs.get("needs_campaign_basic"):
        logger.warning("Detected client-level performance query. Auto-invoking required tools...")
        if needs.get("needs_campaign_basic"):
            logger.warning("Auto-invoking query_campaign_basic for 全站客戶")
            try:
                campaign_result = query_campaign_basic.invoke({"start_date": start_date, "end_date": end_date})
                if campaign_result.get("status") == "success" and campaign_result.get("data"):
                    result["data_store"]["query_campaign_basic"] = campaign_result.get("data", [])
                    logger.info(f"Auto-invoked query_campaign_basic, got {len(campaign_result.get('data', []))} campaigns")
            except Exception as e:
                logger.warning(f"Auto-invoke campaign_basic failed: {e}")
        if needs.get("needs_performance"):
            campaign_data = result.get("data_store", {}).get("query_campaign_basic", [])
            cmp_ids = [row.get('campaign_id') for row in campaign_data if row.get('campaign_id')]
            if cmp_ids:
                logger.warning(f"Auto-invoking query_unified_performance with {len(cmp_ids)} campaign IDs")
                try:
                    performance_result = query_unified_performance.invoke({
                        "start_date": start_date,
                        "end_date": end_date,
                        "cmpids": cmp_ids,
                        "group_by": ["ad_format_type"]
                    })
                    if performance_result.get("status") == "success" and performance_result.get("data"):
                        result["data_store"]["query_unified_performance"] = performance_result.get("data", [])
                        logger.info(f"Auto-invoked query_unified_performance, got {len(performance_result.get('data', []))} rows")
                except Exception as e:
                    logger.warning(f"Auto-invoke unified_performance failed: {e}")
            else:
                logger.warning("Cannot invoke query_unified_performance: no campaign IDs available")
    output = {
        "messages": new_messages,
        "debug_logs": new_logs,
        "data_store": result.get("data_store"),
        "resolved_entities": result.get("resolved_entities")
    }
    return output
