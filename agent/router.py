"""
Intent Router Node for AKC Framework 3.0

This node analyzes user input and routes to the appropriate agent.
Currently routes to Data Analyst Agent for all data queries.
Future: May route to Marketing Strategist Agent for strategy questions.
"""
from datetime import datetime
from typing import Dict, Any
import logging
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from config.llm import llm
from agent.state import AgentState

# Setup logging
logger = logging.getLogger("akc.router")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

INTENT_ROUTER_PROMPT = """你是 AKC 智能助手的意圖路由器 (Intent Router)。

你的任務是分析使用者的問題，並決定路由方向。

**路由選項:**
1. **DataAnalyst** - 數據分析師 (預設)
   - 查詢數據、報表、排名、統計
   - 例如：「悠遊卡今年執行金額？」、「前三大格式」
   - **重要：** 若使用者是正在回答系統先前的「澄清問題」（例如提供編號、說「全部」、「第一個」），請務必導向 DataAnalyst。

2. **Strategist** - 營銷策略師 (未來功能)
   - 詢問建議、策略、優化方案
   - 例如：「如何提升 CTR？」維度分析

3. **Chitchat** - 閒聊/無法處理
   - 打招呼、無關問題

**當前系統時間 (System Time):**
- **今天日期 (Today):** {current_time}
- **今年年份 (Current Year):** {current_year}
- **去年年份 (Last Year):** {last_year}

**重要區分 - 維度 vs 實體:**

**維度 (Dimensions)** = 欄位名稱，不要放入 entity_keywords:
- "代理商" / "agency" → 這是查詢維度
- "廣告主" / "客戶" / "advertiser" / "client" → 這是查詢維度
- "活動" / "campaign" → 這是查詢維度
- "格式" / "ad format" → 這是查詢維度

**實體 (Entities)** = 具體名稱，要放入 entity_keywords:
- "悠遊卡" → 客戶名稱
- "Nike" → 品牌名稱
- "台北數位" → 代理商名稱
- "春節檔期" → 活動名稱

**時間判斷 (Time Extraction):**
- **最高準則**: 所有相對時間 (如 "過去三個月", "今年", "上週") **必須** 根據上方的 **今天日期 ({current_time})** 進行推算。
- 格式: YYYY-MM-DD
- 規則:
  - "今年": {current_year}-01-01 到 {current_year}-12-31
  - "去年": {last_year}-01-01 到 {last_year}-12-31
  - "上個月": 上個月的第一天到最後一天
  - "過去三個月": 從 **{current_time}** 往前推 90 天。
  - "2024年": 2024-01-01 到 2024-12-31
  - "全部時間" / "全期間" / "不限時間": 2020-01-01 到 {current_year}-12-31
  - 若使用者未提及時間，請回傳 null。

**分析步驟:**
1. 判斷使用者意圖類型
2. 提取**具體實體名稱**（不要把維度當成實體）
3. 提取時間關鍵字並計算 start_date/end_date (務必基於 {current_time})
4. 判斷分析類型（投資/執行/成效）

**輸出格式 (JSON):**
```json
{{
  "route_to": "DataAnalyst" | "Strategist" | "Chitchat",
  "entity_keywords": [],  // 只放具體名稱
  "time_keywords": ["今年"], // 原始時間詞彙
  "start_date": "YYYY-MM-DD" | null,
  "end_date": "YYYY-MM-DD" | null,
  "analysis_hint": "執行金額" | "投資金額" | "成效數據" | null,
  "confidence": "high" | "medium" | "low"
}}
```

**範例 (僅供參考格式):**
- 問題: "代理商 YTD 認列金額" (假設今天是 2025-05-20)
  → time_keywords: ["YTD"]
  → start_date: "2025-01-01"
  → end_date: "2025-05-20"

- 問題: "悠遊卡成效如何"
  → time_keywords: []
  → start_date: null
  → end_date: null

請分析使用者的問題並回應。
"""


def intent_router_node(state: AgentState) -> Dict[str, Any]:
    """
    Intent Router: Analyzes user intent and decides routing.

    Args:
        state: Current agent state

    Returns:
        Updated state with routing decision
    """
    messages = list(state.get("messages", []))

    # --- Get Context ---
    last_user_msg = ""
    last_ai_msg = ""
    original_query = ""

    # Search for messages
    for msg in reversed(messages):
        content = ""
        msg_type = ""
        
        if isinstance(msg, (HumanMessage, AIMessage)):
            content = msg.content
            msg_type = "human" if isinstance(msg, HumanMessage) else "ai"
        elif isinstance(msg, dict):
            content = msg.get("content", "")
            msg_type = msg.get("type", "")
        elif hasattr(msg, "content") and hasattr(msg, "type"):
            content = msg.content
            msg_type = msg.type
        
        if not content: continue

        # [FIX] Filter out synthesized context messages to prevent recursion
        if "使用者先前問題:" in content or "系統澄清提問:" in content:
            continue

        if msg_type == "human":
            if not last_user_msg:
                last_user_msg = content
            else:
                # The one before the last AI msg is usually the original query
                original_query = content
                break
        elif msg_type == "ai":
            if not last_ai_msg:
                last_ai_msg = content

    if not last_user_msg:
        return {"next": "END", "messages": [AIMessage(content="我沒有收到您的問題。")]}

    # --- Context Construction ---
    # If the user's message is short, it's likely a reply to a system question
    is_context_aware = False
    if last_ai_msg and ("請問您指的是" in last_ai_msg or "哪個時間段" in last_ai_msg):
        full_context_query = f"""
        使用者先前問題: {original_query}
        系統澄清提問: {last_ai_msg}
        使用者最新回覆: {last_user_msg}
        
        請根據使用者的最新回覆，結合先前的問題背景，判斷其最終查詢意圖。
        """
        logger.info("Context-aware routing activated.")
        is_context_aware = True
    else:
        full_context_query = last_user_msg

    # Prepare prompt
    now_dt = datetime.now()
    now_str = now_dt.strftime("%Y-%m-%d")
    current_year = now_dt.year
    last_year = current_year - 1
    
    system_msg = SystemMessage(content=INTENT_ROUTER_PROMPT.format(
        current_time=now_str,
        current_year=current_year,
        last_year=last_year
    ))
    user_msg = HumanMessage(content=full_context_query)

    # Invoke LLM
    logger.info(f"Analyzing: {full_context_query[:200]}...")
    response = llm.invoke([system_msg, user_msg])

    # Parse response
    import re
    import json

    content = response.content
    if isinstance(content, list):
        content = " ".join([
            item.get("text", "") if isinstance(item, dict) else str(item)
            for item in content
        ])

    # Extract JSON
    routing_decision = {
        "route_to": "DataAnalyst",  # Default
        "entity_keywords": [],
        "time_keywords": [],
        "start_date": None,
        "end_date": None,
        "analysis_hint": None,
        "confidence": "medium"
    }

    json_match = re.search(r"```json\s*(\{.*?\})\s*```", content, re.DOTALL)
    if json_match:
        try:
            routing_decision = json.loads(json_match.group(1))
            logger.info(f"Parsed routing: {routing_decision}")
        except Exception as e:
            logger.error(f"JSON parse failed: {e}")

    # Determine next node
    route = routing_decision.get("route_to", "DataAnalyst")
    
    # [FIX] Force DataAnalyst if context-aware, even if LLM says Chitchat
    if is_context_aware and route == "Chitchat":
        logger.info("Context-aware override: Chitchat -> DataAnalyst")
        route = "DataAnalyst"

    start_date = routing_decision.get("start_date")
    end_date = routing_decision.get("end_date")
    analysis_hint = routing_decision.get("analysis_hint")

    # --- Parameter Inheritance (State Memory) ---
    # If this is a follow-up query (e.g. "All", "The first one"),
    # we should inherit missing parameters from the previous turn.
    prev_context = state.get("routing_context", {})
    if prev_context and route == "DataAnalyst":
        if not start_date:
            start_date = prev_context.get("start_date")
            logger.info(f"Inherited start_date from previous context: {start_date}")
        if not end_date:
            end_date = prev_context.get("end_date")
            logger.info(f"Inherited end_date from previous context: {end_date}")
        if not analysis_hint:
            analysis_hint = prev_context.get("analysis_hint")
            logger.info(f"Inherited analysis_hint from previous context: {analysis_hint}")

    if route == "Chitchat":
        return {
            "next": "END",
            "messages": [AIMessage(content="抱歉,我是專門處理數據分析的助手。請問您有數據查詢的需求嗎?")]
        }
    elif route == "Strategist":
        logger.info("Strategist not implemented yet, routing to DataAnalyst")
        route = "DataAnalyst"

    # --- [NEW] Time Clarification Logic ---
    if route == "DataAnalyst" and (not start_date or not end_date):
        logger.warning("Missing time range. Asking user for clarification.")
        return {
            "next": "END",
            "messages": [AIMessage(content="請問您想查詢哪個時間段的數據？(例如：今年、過去三個月、2025年Q1)")]
        }

    # Store routing context for Data Analyst
    routing_context = {
        "entity_keywords": routing_decision.get("entity_keywords", []),
        "time_keywords": routing_decision.get("time_keywords", []),
        "start_date": start_date,
        "end_date": end_date,
        "analysis_hint": routing_decision.get("analysis_hint"),
        "original_query": full_context_query
    }

    logger.info(f"Routing to: {route} with dates: {start_date} ~ {end_date}")
    logger.info(f"Full Routing Context: {routing_context}")

    return {
        "next": "DataAnalyst",
        "routing_context": routing_context
    }