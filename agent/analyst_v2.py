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
    id_finder,
    query_campaign_basic,
    query_investment_budget,
    query_execution_budget,
    query_targeting_segments,
    execute_sql_template
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
    id_finder,
    query_campaign_basic,
    query_investment_budget,
    query_execution_budget,
    query_targeting_segments,
    execute_sql_template,
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

**核心任務**: 根據使用者需求，選擇正確的工具獲取數據。

### 🔍 實體解析規則 (Entity Resolution Rules) - 非常重要！

使用 `resolve_entity` 時，請嚴格遵守以下過濾邏輯，避免搜尋到不相關的實體：

1. **一般查詢 (預設)**：
   - 當使用者問「悠遊卡成效」、「Nike 預算」時，通常是指 **廣告主 (Client)** 或 **品牌 (Brand)**。
   - **指令**: `target_types=['client', 'brand', 'campaign']`
   - **禁止**: 絕對不要包含 `industry` 或 `sub_industry`，否則會搜到無關的產業類別。

2. **產業查詢 (明確指定)**：
   - 只有當使用者明確提到「**產業**」、「**類別**」、「**行業**」時 (例如：「健康保健產業」、「汽車類別」)。
   - **指令**: `target_types=['industry', 'sub_industry']`

3. **代理商查詢 (明確指定)**：
   - 當使用者明確提到「**代理商**」、「**Agency**」。
   - **指令**: `target_types=['agency']`

---

### 🛠️ 工具選擇指南 (SOP)

**情境 A: 「全站」或「產業」層級分析**

1. **問「預算佔比」或「金額排名」**:
   - Step 1: `resolve_entity` 取得 `industry_id` 或 `sub_industry_id`。
   - Step 2: **必須使用** `id_finder(industry_ids=[...])` 取得該期間內的所有相關 IDs。
   - Step 3: 呼叫 `query_investment_budget` 或 `query_execution_budget` 取得金額。

2. **問「成效 (CTR/VTR)」或「表現」**:
   - Step 1: `resolve_entity` 取得 ID。
   - Step 2: **必須使用** `id_finder` 取得相關 IDs。
   - Step 3: 呼叫 `query_unified_performance(plaids=[...])`。

3. **問「有哪些...」 (探索清單)**:
   - ⚡️ **直接使用** `query_unified_dimensions(dimensions=['product_line'])`。

**情境 B: 「特定客戶/實體」分析 (例如: Nike)**

1. **Step 1: 實體解析 (必須)**
   - 使用 `resolve_entity(keyword='Nike')` 取得 `client_id`。

2. **Step 2: 取得 IDs (關鍵)**
   - **優先使用** `id_finder(client_ids=[id], start_date=..., end_date=...)`。
   - 這會回傳該客戶在指定期間內的所有 `cue_list_id`, `campaign_id`, `plaid`。

3. **Step 3: 根據需求分流**
   - **查預算/進單**:
     - `query_investment_budget(cue_list_ids=[...])`。
   - **查花費/執行**:
     - `query_execution_budget(plaids=[...])`。
   - **查成效 (CTR/VTR)**:
     - `query_unified_performance(plaids=[...], group_by=['ad_format_type'])`。
   - **查受眾/設定**:
     - `query_targeting_segments(plaids=[...])`。

**情境 C: 混合計算 (例如: Nike 的產品線 CPC)**
   1. `id_finder` (拿 IDs)
   2. `query_unified_performance(plaids=[...])` (拿 Clicks)
   3. `query_investment_budget(cue_list_ids=[...])` (拿 Budget)
   4. **結束工具呼叫**。

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
        base_prompt += entity_context
    
    # [NEW] Inject Quality Check Feedback as a System Directive
    feedback = request.state.get("quality_check_feedback")
    if feedback:
        base_prompt += f"\n\n🚨 **系統緊急修正指令 (CRITICAL FIX)** 🚨\n{feedback}\n請忽略之前的錯誤嘗試，直接執行上述指令，不要重新搜尋 ID！"

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

    # Force Date Override
    if state.get("routing_context"):
        logger.info(f"Routing Context: {state.get('routing_context')}")
        system_start = state["routing_context"].get("start_date")
        system_end = state["routing_context"].get("end_date")
        original_query = state["routing_context"].get("original_query", "").lower()
        
        # [NEW] Strict Entity Type Enforcement
        if tool_name == "resolve_entity":
            industry_keywords = ["產業", "類別", "行業", "industry", "category"]
            is_industry_query = any(kw in original_query for kw in industry_keywords)
            
            if is_industry_query:
                # Force Industry types only
                logger.warning(f"Strict Enforcement: Query implies Industry. Forcing target_types=['industry', 'sub_industry']")
                args["target_types"] = ["industry", "sub_industry"]
            else:
                # Force Non-Industry types (exclude industry to prevent noise)
                # Unless the LLM specifically asked for 'ad_format' (rare but possible), but usually ad_format is handled by dimensions
                logger.warning(f"Strict Enforcement: Query implies General Entity. Forcing target_types=['client', 'agency', 'brand', 'campaign']")
                args["target_types"] = ["client", "agency", "brand", "campaign"]

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
                    # Clear any previous ambiguity since we found a match
                    state["ambiguity_status"] = None
                elif status in ["rag_results", "needs_confirmation"]:
                    # Store ambiguity for QualityCheck to intercept
                    logger.info(f"Detected entity ambiguity ({status}). Storing for interception.")
                    state["ambiguity_status"] = raw_result
                
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
            
            if tool_name == "id_finder" and raw_result.get("data"):
                rows = raw_result.get("data", [])
                cue_list_ids = list(set(r['cue_list_id'] for r in rows if r.get('cue_list_id')))
                plaids = list(set(r['plaid'] for r in rows if r.get('plaid')))
                if plaids or cue_list_ids:
                    content += f"\n\n✅ 已取得相關 IDs。CueLists: {len(cue_list_ids)}, Plaids: {len(plaids)}。\n👉 下一步: 請根據需求呼叫 `query_investment_budget` (預算) 或 `query_execution_budget` (執行) 或 `query_unified_performance` (成效)。"
            
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
    
    needs = {
        "needs_benchmark": False,
        "needs_performance": False
    }
    if has_format and has_performance:
        if has_client:
            needs["needs_performance"] = not has_performance_tool
        else:
            needs["needs_benchmark"] = not has_benchmark
    return needs

def data_retriever_v2_node(state: ProjectAgentState) -> Dict[str, Any]:
    initial_messages_count = len(state.get("messages", []))
    initial_logs_count = len(state.get("debug_logs", []))
    
    # Reset data_store for new turn
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

    # [FIX] Manually extract ambiguity_status from messages if missing from result
    # This ensures propagation even if create_agent strips custom state keys
    ambiguity_status = result.get("ambiguity_status")
    if not ambiguity_status:
        for msg in new_messages:
            if isinstance(msg, ToolMessage):
                try:
                    content = json.loads(msg.content)
                    if isinstance(content, dict) and content.get("status") in ["rag_results", "needs_confirmation"]:
                        logger.info("Manually extracted ambiguity_status from ToolMessage")
                        ambiguity_status = content
                        break # Found it, stop searching
                except:
                    pass
        
    # Auto-invoke Benchmark
    if needs.get("needs_benchmark"):
        logger.warning("Detected missing query_format_benchmark call. Auto-invoking...")
        try:
            invoke_params = {"start_date": start_date, "end_date": end_date}
            # Note: id_finder results are structural, hard to guess 'cmp_ids' for benchmark
            # If we have id_finder data, maybe we can extract?
            # For now, default to global benchmark if no specific IDs found
            logger.warning("Auto-invoking benchmark for 全站查詢")
            benchmark_result = query_format_benchmark.invoke(invoke_params)
            if benchmark_result.get("status") == "success" and benchmark_result.get("data"):
                result["data_store"]["query_format_benchmark"] = benchmark_result.get("data", [])
                logger.info(f"Auto-invoked query_format_benchmark, got {len(benchmark_result.get('data', []))} rows")
        except Exception as e:
            logger.warning(f"Auto-invoke benchmark failed: {e}")

    output = {
        "messages": new_messages,
        "debug_logs": new_logs,
        "data_store": result.get("data_store"),
        "resolved_entities": result.get("resolved_entities"),
        "ambiguity_status": ambiguity_status # [FIX] Use local variable
    }
    return output

def quality_check_node(state: ProjectAgentState) -> Dict[str, Any]:
    """
    Check if the Analyst has fetched all necessary data before proceeding to Reporter.
    Also acts as a Gatekeeper for Entity Resolution Ambiguity.
    """
    data_store = state.get("data_store", {})
    original_query = state.get("routing_context", {}).get("original_query", "").lower()
    retry_count = state.get("retry_count", 0)
    
    # --- 1. Ambiguity Interception (Human-in-the-loop) ---
    ambiguity = state.get("ambiguity_status")
    if ambiguity:
        status = ambiguity.get("status")
        candidates = ambiguity.get("data", [])
        
        if status in ["rag_results", "needs_confirmation"] and candidates:
            # Construct clarification message
            options = []
            for i, cand in enumerate(candidates[:5]): # Limit to top 5
                name = cand.get("value") or cand.get("name")
                type_ = cand.get("filter_type") or cand.get("type")
                label = f"{name} ({type_})" if type_ else name
                options.append(f"{i+1}. {label}")
            
            options_str = "\n".join(options)
            clarification_msg = (
                f"⚠️ 我找到了多個與「{original_query}」相關的項目，請問您指的是哪一個？\n\n"
                f"{options_str}\n\n"
                "請直接輸入您想要的名稱（例如：「醫藥美容類」）。"
            )
            
            logger.info(f"Quality Check Intercept: Ambiguity found. Asking user.")
            
            # NOTE: We return ambiguity_status: None here to clear it for the NEXT turn,
            # but we use the information to generate the response for THIS turn.
            return {
                "next": "END", # Stop the graph
                "final_response": clarification_msg,
                "messages": [AIMessage(content=clarification_msg)],
                "ambiguity_status": None # Clear it so we don't intercept again in a loop
            }

    # Max retries to prevent infinite loops
    MAX_RETRIES = 2
    if retry_count >= MAX_RETRIES:
        logger.warning(f"Quality Check: Max retries ({MAX_RETRIES}) reached. Proceeding to Reporter.")
        return {"next": "Reporter"}

    # Keyword Analysis for Intent
    budget_keywords = ["預算", "金額", "cost", "budget", "投資", "花費", "佔比"]
    performance_keywords = ["成效", "點擊", "ctr", "vtr", "er", "performance", "click", "impression"]
    
    needs_budget = any(k in original_query for k in budget_keywords)
    needs_performance = any(k in original_query for k in performance_keywords)
    
    has_ids = "id_finder" in data_store and len(data_store["id_finder"]) > 0
    has_budget_data = "query_investment_budget" in data_store or "query_execution_budget" in data_store
    has_performance_data = "query_unified_performance" in data_store
    
    feedback = None
    
    # Check 1: Found IDs but no Budget (when budget needed)
    if has_ids and needs_budget and not has_budget_data:
        feedback = "❌ 品質檢查未通過：你已經找到了 ID (id_finder)，但使用者詢問「預算/金額」，而你尚未呼叫 `query_investment_budget`。請立即呼叫該工具來獲取金額數據。"
        
    # Check 2: Found IDs but no Performance (when performance needed)
    elif has_ids and needs_performance and not has_performance_data:
        feedback = "❌ 品質檢查未通過：你已經找到了 ID (id_finder)，但使用者詢問「成效」，而你尚未呼叫 `query_unified_performance`。請立即呼叫該工具來獲取數據。"

    if feedback:
        logger.warning(f"Quality Check Failed: {feedback}")
        return {
            "next": "DataAnalyst",
            "retry_count": retry_count + 1,
            "quality_check_feedback": feedback,
            # Inject feedback as a HumanMessage to guide the agent
            "messages": [HumanMessage(content=feedback)]
        }
    
    logger.info("Quality Check Passed.")
    return {"next": "Reporter"}