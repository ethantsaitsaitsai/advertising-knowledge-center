"""
AKC Framework 3.0 - Data Analyst Agent (V2)
Implemented using langchain.agents.create_agent
"""
import json
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
    query_industry_format_budget
)
from tools.performance_tools import query_performance_metrics, query_format_benchmark

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
    query_performance_metrics,
    query_format_benchmark
]

RETRIEVER_SYSTEM_PROMPT = """你是 AKC 智能助手的數據檢索專家 (Data Retriever)。

**你的任務流程 (SOP)**:

**⚠️ 關鍵判斷：何時使用「統計與基準工具」？**
若使用者的問題屬於「全站/產業層級」的「佔比」或「排名」分析，**請優先使用以下高效工具**，並跳過後續的實體解析與活動查詢步驟：

1. **多維度預算佔比 (`query_industry_format_budget`)**:
   - 適用：「某產業的格式分佈」、「某格式的產業分佈」、「某格式的客戶分佈」。
   - **核心參數 `dimension` (決定分析視角)**:
     - 查「產業預算」或「投放哪些格式」→ 推薦使用 `dimension='sub_industry'` (子類) 以獲得更細緻的分析 (若無特定需求也可選 `dimension='industry'` 大類)。
     - 查「客戶預算」或「誰投了這個格式」→ `dimension='client'`
     - 查「代理商預算」→ `dimension='agency'`
   - **核心參數 `primary_view` (決定主體與第一欄)**:
     - `'dimension'` (預設): 以「產業/客戶」為主體。第一欄顯示產業，適用於「某產業投了什麼」。
     - `'format'`: 以「格式」為主體。第一欄顯示格式，適用於「某格式投到了哪裡」或「所有格式的表現」。
   - **過濾參數**:
     - 若指定特定格式 (如「Banner」)，請設 `format_ids` (需先透過 `resolve_entity` 取得格式 ID)。

2. **全站格式成效 (`query_format_benchmark`)**:
   - 適用：「所有格式的 CTR 排名」、「產業的平均 VTR」。

---

**一般查詢流程 (針對特定實體/Campaign)**:

**⚠️ 關鍵判斷：何時需要實體解析？**
在執行 Step 1 之前，請先判斷使用者查詢的類型：

- **需要實體解析的查詢** (使用 `resolve_entity`):
  - 使用者提到**具體的名稱**，例如："悠遊卡的預算"、"美妝產業的活動"。

- **不需要實體解析的查詢** (直接進入 Step 3):
  - 使用者要求**整體排名/匯總/統計**，例如："代理商 YTD 認列金額"、"前十大客戶的投資"。

1. **實體解析 (Step 1 - 僅在需要時執行)**:
   - **只有在使用者提到具體名稱時**，才使用 `resolve_entity` 將名稱轉換為 ID。

2. **獲取活動 (Step 2 - 僅在 Step 1 執行後)**:
   - **取得 ID 後，立刻** 使用 `query_campaign_basic` 取得該客戶的所有活動列表。

3. **數據蒐集 (Step 3 - 所有查詢都需要)**:
   - 根據使用者需求，呼叫適當的查詢工具：
     - `query_execution_budget`: 查詢「認列金額」或「執行金額」
     - `query_investment_budget`: 查詢「預算」或「進單金額」
     - `query_performance_metrics`: 查詢成效 (必須傳入 `cmp_ids`)
     - `query_targeting_segments`: 查詢受眾
     - `query_ad_formats`: 查詢廣告格式

**核心原則 (鐵律)**:
- **ID 絕對優先**: 只要你取得了 ID，後續所有查詢 **必須** 使用 ID。
- **成效查詢規範**: 必須傳入 `cmp_ids`。請設定寬鬆的時間範圍 (例如 `start_date='2021-01-01'`) 以獲取歷史數據。

**結束條件**:
- 當你收集完所有必要的數據，請停止呼叫工具，並簡單回覆：「數據收集完畢，轉交報告者處理。」
"""

@dynamic_prompt
def retriever_dynamic_prompt(request: ModelRequest) -> str:
    """Injects current date and resolved entities into the system prompt."""
    now = datetime.now()
    current_date = now.strftime("%Y-%m-%d")
    
    base_prompt = RETRIEVER_SYSTEM_PROMPT.format(current_date=current_date)
    
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
                    # Handle Decimal inside string representation
                    # e.g. "{'amt': Decimal('10.5')}" -> "{'amt': 10.5}"
                    # Simple regex replace might be safer than eval with context
                    import re
                    # Replace Decimal('123.45') with 123.45
                    cleaned = re.sub(r"Decimal\('([^']+)'\)", r"\1", content)
                    # Replace datetime.date(2023, 1, 1) with '2023-01-01'
                    cleaned = re.sub(r"datetime\.date\((\d+), (\d+), (\d+)\)", r"'\1-\2-\3'", cleaned)
                    # Replace datetime.datetime(2023, 1, 1, 12, 0) with '2023-01-01T12:00:00'
                    # Handle optional time components (simple greedy match might be risky, stick to basic pattern)
                    cleaned = re.sub(r"datetime\.datetime\((\d+), (\d+), (\d+),? ?(\d+)?,? ?(\d+)?,? ?(\d+)?\)", 
                                     lambda m: f"'{m.group(1)}-{m.group(2)}-{m.group(3)}'", cleaned) # Simplify to date for now or improve regex
                    
                    raw_result = ast.literal_eval(cleaned)
                except Exception as parse_e:
                    print(f"DEBUG [RetrieverMiddleware] Failed to parse content for {tool_name}: {parse_e}")
                    print(f"DEBUG [RetrieverMiddleware] Content preview: {content[:200]}...")
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
                    existing_data_str = {json.dumps(row, sort_keys=True, default=str) for row in state["data_store"][tool_name]}
                    new_rows = []
                    for row in data:
                        row_str = json.dumps(row, sort_keys=True, default=str)
                        if row_str not in existing_data_str:
                            new_rows.append(row)
                            existing_data_str.add(row_str)

                    if new_rows:
                        state["data_store"][tool_name].extend(new_rows)
                        print(f"DEBUG [RetrieverMiddleware] Stored {len(new_rows)} rows in data_store")
            
            # 2. Handle Entity Resolution specifically for state update
            if tool_name == "resolve_entity":
                status = raw_result.get("status")
                if status in ["exact_match", "merged_match"]:
                    entity = raw_result.get("data")
                    if isinstance(entity, list):
                        state["resolved_entities"].extend(entity)
                    else:
                        state["resolved_entities"].append(entity)
                print(f"DEBUG [RetrieverMiddleware] Updated resolved_entities: {len(state['resolved_entities'])}")

            # 3. Add guidance and convert to valid JSON
            # Use a custom encoder/default function to handle Decimals/Dates safely
            def json_default(obj):
                import decimal
                import datetime
                if isinstance(obj, decimal.Decimal):
                    return float(obj)
                if isinstance(obj, (datetime.date, datetime.datetime)):
                    return obj.isoformat()
                return str(obj)

            content = json.dumps(raw_result, ensure_ascii=False, default=json_default)
            
            # Add guidance for query_campaign_basic
            if tool_name == "query_campaign_basic" and raw_result.get("data"):
                campaign_ids = [row.get('campaign_id') for row in raw_result.get("data", []) if row.get('campaign_id')]
                if campaign_ids:
                    content += f"\n\n✅ 已取得 {len(campaign_ids)} 個活動的基本資料。\n👉 下一步: 請查詢成效/預算等數據。"
            
            # 4. Return as ToolMessage to ensure JSON format
            return ToolMessage(tool_call_id=tool_call["id"], content=content)

        return result
    except Exception as e:
        print(f"ERROR [RetrieverMiddleware] {e}")
        return ToolMessage(tool_call_id=tool_call["id"], content=json.dumps({"error": str(e)}))

# Create the agent
retriever_agent = create_agent(
    model=llm,
    tools=RETRIEVER_TOOLS,
    middleware=[retriever_dynamic_prompt, retriever_tool_middleware],
    state_schema=ProjectAgentState
)

def data_retriever_v2_node(state: ProjectAgentState) -> Dict[str, Any]:
    """
    Wrapper for the retriever_agent to be used as a node in analyst_graph.
    """
    # Calculate starting counts to determine new items
    initial_messages_count = len(state.get("messages", []))
    initial_logs_count = len(state.get("debug_logs", []))
    
    # [NEW] Sanitize messages: Convert dicts to Objects locally
    # This prevents LangChain from choking on dicts without dirtying the global state with duplicates
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
                # Handle tool messages from dict if needed
                tool_call_id = msg.get("tool_call_id", "unknown")
                sanitized_messages.append(ToolMessage(content=content, tool_call_id=tool_call_id))
            else:
                # Fallback for unknown dict types
                sanitized_messages.append(HumanMessage(content=str(msg)))
        elif isinstance(msg, BaseMessage):
            # Check for generic BaseMessage and convert to HumanMessage if it's not a specific type
            # Google GenAI strictly requires specific message types
            if msg.type == "human":
                sanitized_messages.append(HumanMessage(content=msg.content))
            elif msg.type == "ai":
                sanitized_messages.append(AIMessage(content=msg.content))
            elif msg.type == "system":
                sanitized_messages.append(SystemMessage(content=msg.content))
            elif msg.type == "tool":
                sanitized_messages.append(msg) # ToolMessage is usually fine
            else:
                # If it's a generic BaseMessage without a clear type, treat as HumanMessage
                sanitized_messages.append(HumanMessage(content=msg.content))
        else:
            # Fallback for any other object
            sanitized_messages.append(HumanMessage(content=str(msg)))
            
    # Create a local state copy with sanitized messages
    local_state = state.copy()
    local_state["messages"] = sanitized_messages

    # Run the agent with sanitized state
    result = retriever_agent.invoke(local_state)
    
    # Extract only new items to avoid duplication with operator.add
    final_messages = result.get("messages", [])
    new_messages = final_messages[len(sanitized_messages):] # Diff based on sanitized input length
    
    final_logs = result.get("debug_logs", [])
    new_logs = final_logs[initial_logs_count:]
    
    # Construct output update
    output = {
        "messages": new_messages,
        "debug_logs": new_logs,
        # data_store and resolved_entities are typically overwritten or merged by logic, 
        # but since they don't have reducers in AgentState (or might not), passing full object is safer/required
        "data_store": result.get("data_store"),
        "resolved_entities": result.get("resolved_entities")
    }
    
    return output
