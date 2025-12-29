"""
Data Analyst Agent for AKC Framework 3.0

This agent handles all data query requests using:
1. Entity Resolver - to identify database IDs from natural language
2. SQL Template Tools - to execute pre-defined SQL queries
3. Pandas Processor - to process and format results
"""
from typing import Dict, Any
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
    execute_sql_template
)
from tools.performance_tools import query_performance_metrics
from tools.data_processing_tool import pandas_processor
import json

# Available tools for Data Analyst
TOOLS = [
    resolve_entity,
    query_campaign_basic,
    query_budget_details,
    query_investment_budget,
    query_execution_budget,
    query_targeting_segments,
    query_ad_formats,
    execute_sql_template,
    query_performance_metrics,
    pandas_processor
]

# Bind tools to LLM
llm_with_tools = llm.bind_tools(TOOLS)

ANALYST_SYSTEM_PROMPT = """你是 AKC 智能助手的數據分析師 (Data Analyst)。

**當前日期:** {current_date}

**你的核心原則:**
- **絕對不要自己寫 SQL**。所有 SQL 邏輯已經在 Python 工具中定義好。
- 你的工作是「填空」而非「寫程式」。

**工作流程:**

1. **實體解析 (Entity Resolution) - 三階段流程**
   - **檢查 Context**: 先查看 System Prompt 中是否已有「已確認的實體」。若有且符合當前需求，**請直接使用該 ID，不要再次呼叫 resolve_entity**。
   - 使用 `resolve_entity(keyword="...")` 進行實體查詢
   - **參數設定原則**:
     - **預設情況**: **不要** 設定 `target_types` (保持預設值 None)。這會同時搜尋 Campaign, Client, Agency, Brand 等所有表格。
     - **例外情況**: 只有當使用者明確指定類型時（例如：「查詢**代理商**亞思博」、「**客戶**悠遊卡」、「**產業**美妝」），才設定 `target_types=["agency"]` 或 `target_types=["industry"]`。
     - **原因**: 若使用者只說「悠遊卡」，它可能是客戶名也可能是活動名。必須搜尋全部，若總結果只有 1 筆才會自動匹配。
   - 工具會自動執行：LIKE 查詢 → 使用者確認 → RAG 向量搜尋

   **處理不同的返回狀態:**

   a) `status: "exact_match"` - 找到唯一匹配
      - 直接使用返回的實體 ID 繼續查詢
      - 例如: `{{"status": "exact_match", "data": {{"id": 123, "name": "悠遊卡", "type": "client"}}}}`
      - 若 type 為 `industry` 或 `sub_industry`，請將 ID 分別放入 `industry_ids` 或 `sub_industry_ids` 參數中。

   b) `status: "needs_confirmation"` - 找到多個匹配
      - 向使用者展示選項清單
      - 使用 Markdown 格式化選項（編號、名稱、類型）
      - 要求使用者回覆編號或名稱
      - **停止當前分析，等待使用者選擇**
      - 當使用者回覆後，使用 `resolve_entity(keyword="...", selected_id=X, selected_type="...")` 確認選擇

   c) `status: "rag_results"` - LIKE 查詢無結果，但 RAG 找到相似實體
      - 向使用者展示 RAG 建議的實體
      - 詢問是否使用這些建議

   d) `status: "not_found"` - 完全找不到
      - 告知使用者無法找到該實體
      - 建議使用者檢查拼寫或提供更多資訊

   **處理使用者回覆選擇 (重要優化)**:
   - 若上一步是你詢問使用者「請選擇...」，而使用者回覆了選擇：
   - **規則 1: 完全名稱匹配 (Exact Name Match)**
     - 若使用者輸入的名稱與選項中的某個名稱**完全相同**（例如選項有 "(暫停使用) A" 和 "A"，使用者回覆 "A"），**請直接視為選擇了 "A"**。
     - **特殊狀況**: 若有多個選項名稱一模一樣 (例如兩個都叫 "台灣妮維雅股份有限公司")：
       - **不要再次詢問**！這會讓使用者困惑。
       - **自動選擇邏輯**: 優先選擇看起來是「啟用中」的那個 (例如排除有 "(暫停使用)" 標記的)。若無法判斷，選擇 ID 較大的那個 (通常是較新的資料)。
       - 直接使用該 ID 呼叫 `resolve_entity(..., selected_id=...)`。

   **多重實體處理 (Batch Processing)**:
   - 若 `entity_keywords` 包含多個關鍵字 (例如 "台北, 亞思博, 聖洋科技")：
     - 請務必對 **每一個** 關鍵字都呼叫 `resolve_entity`。
     - **不要** 在第一個關鍵字需要確認時就直接停止，請先解析完所有關鍵字。
     - 若有多個實體需要確認，請在同一次回應中列出所有的確認選項。
     - 若部分實體已確認 (Exact Match)，部分需要確認，請暫存已確認的 IDs，並針對模糊的項目提問。

   **產業別查詢優化 (Industry Aggregation Rule)**:
   - 當使用者查詢產業 (如「美妝」、「遊戲」) 時：
     - 若 `resolve_entity` 回傳多個相關的產業類別 (包含 `industry` 與 `sub_industry`)，且名稱與關鍵字高度相關。
     - **不要要求使用者逐一確認**。
     - 請**主動合併所有相關 ID** (例如同時傳入 `industry_ids=[2]` 與 `sub_industry_ids=[26, 16]`)。
     - 目的：確保統計結果涵蓋該產業的所有相關標籤，並提供最完整的總預算。

   - **規則 2: 編號選擇**
     - 若使用者回覆數字 (如 "1")，對應選項清單的編號。

   - **規則 3: 部分匹配**
     - 若使用者回覆部分名稱，嘗試找到最接近的匹配項。

   - **禁止事項**: 嚴禁在使用者已經明確回覆名稱（且該名稱在選項中存在）的情況下，再次跳出一樣的選項要求確認。

   **特殊情境：排名與全局查詢 (Ranking / Global Queries)**
   - 若 System Prompt 顯示 `entity_keywords` 為空，且問題涉及「排名」、「Top X」、「總額」：
     - **跳過實體解析** (Do not call resolve_entity)。
     - 直接使用 SQL 工具進行廣泛查詢。
     - **務必放大 Limit**：呼叫 `query_investment_budget` 或 `query_execution_budget` 時，請設定 `limit=5000` 以確保統計結果涵蓋完整年度數據。
     - **分組依據**：
       - 廣告主排名：針對 `client_name` 進行 `groupby_sum`。
       - 代理商排名：針對 `agency_name` 進行 `groupby_sum`。
     - **數量說明**：若最終結果少於使用者要求的數量（例如求 Top 20 但只列出 5 個），請在回應中說明「該期間僅有 5 筆符合條件的資料」。

   **每月/週期性分析 (Monthly / Period Analysis)**:
   - 若使用者要求「每月」、「每季」、「年度趨勢」：
     1. 呼叫 SQL 工具（如 `query_investment_budget`），確保資料中包含日期欄位。
     2. 呼叫 `pandas_processor(operation="add_time_period", date_col="...", period="month")` 生成 `period` 欄位。
     3. 再次呼叫 `pandas_processor(operation="groupby_sum", groupby_col="period, agency_name", ...)` 進行匯總。
     4. 絕對不要因為原始數據中沒有 "month" 欄位就直接說無法彙整，你必須主動使用工具生成它。

4. **資料處理 (CRITICAL!)**

   **基礎查詢工具**:
   - `query_campaign_basic`: 查詢活動基本資訊（客戶、活動名稱、日期、預算）
     - 適用：取得 campaign IDs、基本概覽
     - 參數：client_names, client_ids, industry_ids, sub_industry_ids, campaign_ids, start_date, end_date
     - **重要**: 當已確認實體為 Client (ID=X) 時，請務必使用 `client_ids=[X]`，**不要**只傳名稱。

   **預算相關工具**:
   - `query_investment_budget`: 查詢「進單/投資」金額（格式層級明細）
     - 適用：「預算」、「進單」、「投資金額」相關問題
     - 參數：client_names, client_ids, industry_ids, sub_industry_ids, campaign_ids, start_date, end_date
     - **重要**: 優先使用 `client_ids` 或 `campaign_ids` 進行精準過濾。
     - **重要**: 若涉及產業查詢，請務必將相關的大類 ID (`industry_ids`) 與子類 ID (`sub_industry_ids`) **合併在同一次工具調用中**，不要分開多次調用。

   - `query_execution_budget`: 查詢「執行/認列」金額（執行單層級明細）
     - 適用：「執行」、「認列」、「實際花費」相關問題
     - 參數：client_names, client_ids, industry_ids, sub_industry_ids, campaign_ids, start_date, end_date

   - `query_budget_details`: 查詢預算摘要（整合投資與執行金額）
     - 適用：「預算缺口」、「預算對比」分析
     - ⚠️ 必須提供 campaign_ids（需先呼叫 query_campaign_basic）

   **格式與受眾工具**:
   - `query_ad_formats`: 查詢廣告格式明細
     - 適用：「格式」、「廣告形式」、「秒數」、「平台」相關問題
     - ⚠️ 必須提供 campaign_ids

   - `query_targeting_segments`: 查詢數據鎖定/受眾標籤
     - 適用：「數據鎖定」、「受眾」、「TA」、「標籤」相關問題
     - ⚠️ 必須提供 campaign_ids

   **成效數據工具**:
   - `query_performance_metrics`: 查詢 ClickHouse 成效數據（CTR, VTR, ER, Impressions, Clicks）
     - 適用：所有成效相關問題
     - 參數：client_names 或 cmp_ids, dimension ('format' or 'campaign')
     - **產業成效查詢策略 (Industry Bridge)**:
       - 若查詢「某產業」的成效：
       - 1. 先呼叫 `query_campaign_basic(industry_ids=[...])` 取得 Campaign IDs。
       - 2. 再將取得的 IDs 傳入 `query_performance_metrics(cmp_ids=[...])`。

   **進階工具**:
   - `execute_sql_template`: 通用模板執行器
     - 適用：media_placements.sql, product_lines.sql, contract_kpis.sql, execution_status.sql
     - **重要**: 若使用者詢問「**廣告格式與執行金額**」(按格式分出的認列金額)，請優先使用 `media_placements.sql`。該模板包含 `ad_format_name` 與執行層級的 `budget`。
     - 若需過濾產業，可使用 `industry_ids` (Category) 或 `sub_industry_ids` (Sub-Category) 參數。
     - 只在上述專用工具不適用時才使用

3. **判斷日期範圍 (重要)**
   - **預設範圍**:
     - **Start Date**: {last_year}-01-01 (預設涵蓋去年與今年，避免遺漏近期活動)
     - **End Date**: {current_year}-12-31
   - **例外情況**:
     - 媒體排期常會預排至明年。若在當年查無特定活動，**請自動將 End Date 延長至明年底** (例如 {current_year}+1-12-31)。
     - 若使用者明確指定年份，則以使用者指定為準。

   **⚠️ 查無資料時的處理策略 (Retry Strategy)**:
   - 若使用 `query_campaign_basic` 查詢特定客戶但在指定日期內回傳 0 筆結果：
     - **不要直接放棄！**
     - 請**立刻**再次呼叫 `query_campaign_basic`，但**移除 start_date 與 end_date 參數**。
     - 目的：確認該客戶是否在其他年份有活動資料。若有，請告知使用者「該期間無活動，但找到其他期間的紀錄...」。

4. **資料處理 (CRITICAL!)**
   - SQL 工具回傳原始數據，可能包含 NULL 或重複的 entity_name
   - **你必須 ALWAYS 使用 `pandas_processor` 處理數據！**
   - **重要**：調用 pandas_processor 時，**不要傳 `data` 參數**，系統會自動注入完整數據

   **⚠️ CRITICAL - 理解數據狀態！**
   - **財務工具** (investment_budget, execution_budget) → 返回**原始明細數據**（可能有多行）→ **必須使用 `groupby_sum`**。
   - **成效工具** (query_performance_metrics) → 返回**已匯總數據**（已按 dimension 分組）→ **禁止使用 `groupby_sum`** (會導致 CTR/VTR 遺失或計算錯誤)。請直接使用 `operation="top_n"` 或 `operation="sort"` 來呈現。

   **處理財務數據（原始明細）**：
   - 使用 `operation="groupby_sum"` 分組加總
   - **參數規則**：
     - `groupby_col`: 分組欄位（如 "format_name"）
     - `sum_col`: **支援多欄位**（逗號分隔字串，如 "amount,budget,clicks"）
   - **示例**：
     ```python
     pandas_processor(
         operation="groupby_sum",
         groupby_col="format_name",
         sum_col="investment_amount,investment_gift",
         ascending=False
     )
     ```

   **合併數據策略 (Merge Strategy - 製作單一大表)**:
   - 使用者希望看到**一張整合的大表**，請盡可能將所有數據合併。
   - **標準合併流程 (Drill-Down Logic)**:
     1. 先呼叫 `query_campaign_basic` 取得 `campaign_ids`。
     2. **若步驟 1 有找到資料，絕對不要停止！** 你必須繼續使用這些 IDs 呼叫細節工具（如 `query_ad_formats`, `query_budget_details`, `query_performance_metrics`）。
     3. **處理一對多關係 (如受眾標籤、格式)**:
        - 這些數據通常會有重複的 Campaign ID。
        - **必須先使用 `groupby_concat` 壓平數據**。
        - 例如：針對受眾數據，執行 `pandas_processor(operation="groupby_concat", groupby_col="campaign_id", concat_col="segment_name")`。
        - 這樣每個 Campaign ID 只會有一筆資料，欄位變成 "segment_name" (內容為 "標籤A, 標籤B")。
     4. **最後合併 (Final Merge)**:
        - 以「金額」或「成效」表為主表 (Left Table)。
        - 使用 `pandas_processor(operation="merge", merge_on="campaign_id", ...)` 將壓平後的受眾/格式資料合併進來。
   - **嚴禁**在只有 Basic Info 但缺細節時直接回答「查無資料」。你必須去查細節！

   **資料處理安全檢查**:
   - 在呼叫 `pandas_processor` 前，請檢查 Tool Output 中的 `columns` 列表。
   - **不要** 對不存在的欄位進行 GroupBy 或 Sum。例如 `campaign_basic` 結果中沒有 `format_name`，請勿嘗試對其分組。

5. **最終回應 (Critical)**
   - `pandas_processor` 工具會回傳一個 `markdown` 欄位，其中包含已格式化好的表格。
   - **請直接將該 `markdown` 字串複製到您的回應中**。
   - **表格輸出規則**:
     - 確保表格前後都有空行。
     - **絕對不要** 嘗試重新對齊表格的垂直線 `|`，特別是當內容包含中文字時。
     - **絕對不要** 嘗試閱讀 JSON `data` 欄位並自己重新手寫表格，這會導致錯位或亂碼 (Hallucination)。
   - **若 Analyst Data 中有資料，絕不可回傳空字串或「查無資料」**。

**當前情境:**
- 使用者查詢: {original_query}
- 關鍵字提示: 實體={entity_keywords}, 時間={time_keywords}
- 分析提示: {analysis_hint}

現在開始工作吧!
"""


def data_analyst_node(state: AgentState) -> Dict[str, Any]:
    """
    Data Analyst Agent: Resolves entities, queries data, processes results.

    Workflow:
    1. Extract routing context from Intent Router
    2. Use Entity Resolver to find IDs
    3. Call appropriate SQL Template Tool
    4. Process data with Pandas
    5. Return formatted response

    Args:
        state: Current agent state

    Returns:
        Updated state with analyst results
    """
    from datetime import datetime

    # Get current date
    now = datetime.now()
    current_date = now.strftime("%Y-%m-%d")
    current_year = now.year
    last_year = current_year - 1

    # Extract context from state
    routing_context = state.get("routing_context", {})
    original_query = routing_context.get("original_query", "")
    entity_keywords = routing_context.get("entity_keywords", [])
    time_keywords = routing_context.get("time_keywords", [])
    analysis_hint = routing_context.get("analysis_hint")

    # Load previously resolved entities from state
    resolved_entities_state = state.get("resolved_entities", [])
    if resolved_entities_state is None:
        resolved_entities_state = []

    # Format resolved entities for context
    resolved_context_str = ""
    if resolved_entities_state:
        resolved_names = [f"{e.get('name')} ({e.get('type', 'unknown')}, ID: {e.get('id')})" for e in resolved_entities_state]
        resolved_context_str = f"\n**已確認的實體 (無需再次詢問):** {', '.join(resolved_names)}"
        print(f"DEBUG [DataAnalyst] Loaded resolved entities: {resolved_names}")

    # Handle multimodal content format (Gemini API may return list)
    if isinstance(original_query, list):
        text_parts = []
        for part in original_query:
            if isinstance(part, dict) and part.get("type") == "text":
                text_parts.append(part.get("text", ""))
            elif isinstance(part, str):
                text_parts.append(part)
        original_query = " ".join(text_parts).strip()
        print(f"DEBUG [DataAnalyst] Converted multimodal query to string")

    # Ensure original_query is string
    if not isinstance(original_query, str):
        original_query = str(original_query)

    print(f"DEBUG [DataAnalyst] Starting analysis for: {original_query[:100]}...")
    print(f"DEBUG [DataAnalyst] Context: entities={entity_keywords}, time={time_keywords}, hint={analysis_hint}")
    print(f"DEBUG [DataAnalyst] Current date: {current_date}, Year: {current_year}")

    # Build conversation with system prompt
    messages = [
        SystemMessage(content=ANALYST_SYSTEM_PROMPT.format(
            current_date=current_date,
            current_year=current_year,
            last_year=last_year,
            original_query=original_query,
            entity_keywords=entity_keywords,
            time_keywords=time_keywords,
            analysis_hint=analysis_hint or "未指定"
        ) + resolved_context_str),
        HumanMessage(content=f"請協助分析這個查詢：{original_query}")
    ]

    # Agent ReAct Loop (max 15 iterations to prevent infinite loops)
    final_data = None
    markdown_response = ""
    # Initialize with state values to preserve memory
    resolved_entities = list(resolved_entities_state)
    latest_query_data = None  # Store complete SQL result for pandas_processor

    for iteration in range(15):
        print(f"DEBUG [DataAnalyst] Iteration {iteration + 1}")

        # Invoke LLM with tools
        response = llm_with_tools.invoke(messages)
        messages.append(response)

        # Check if LLM returned final answer (no tool calls)
        if not response.tool_calls:
            markdown_response = response.content
            if isinstance(markdown_response, list):
                markdown_response = " ".join([
                    item.get("text", "") if isinstance(item, dict) else str(item)
                    for item in markdown_response
                ])
            print(f"DEBUG [DataAnalyst] Agent finished with response: {markdown_response[:200]}...")
            break

        # Execute tool calls
        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            args = tool_call["args"]

            print(f"DEBUG [DataAnalyst] Calling tool: {tool_name}")
            print(f"DEBUG [DataAnalyst] Arguments: {args}")

            # Map tool name to function
            tool_map = {
                "resolve_entity": resolve_entity,
                "query_campaign_basic": query_campaign_basic,
                "query_budget_details": query_budget_details,
                "query_investment_budget": query_investment_budget,
                "query_execution_budget": query_execution_budget,
                "query_targeting_segments": query_targeting_segments,
                "query_ad_formats": query_ad_formats,
                "execute_sql_template": execute_sql_template,
                "query_performance_metrics": query_performance_metrics,
                "pandas_processor": pandas_processor
            }

            tool_func = tool_map.get(tool_name)
            if not tool_func:
                messages.append(ToolMessage(
                    tool_call_id=tool_call["id"],
                    content=f"Error: Tool '{tool_name}' not found."
                ))
                continue

            # Pre-process: Inject data for pandas_processor BEFORE execution
            try:
                if tool_name == "pandas_processor" and latest_query_data and not args.get("data"):
                    # Convert Decimal and Date before injecting
                    from decimal import Decimal
                    from datetime import date, datetime
                    
                    def _safe_convert(obj):
                        if isinstance(obj, dict):
                            return {k: _safe_convert(v) for k, v in obj.items()}
                        elif isinstance(obj, list):
                            return [_safe_convert(item) for item in obj]
                        elif isinstance(obj, Decimal):
                            return float(obj)
                        elif isinstance(obj, (date, datetime)):
                            return obj.isoformat()
                        else:
                            return obj

                    args["data"] = _safe_convert(latest_query_data)
                    print(f"DEBUG [DataAnalyst] Injected {len(latest_query_data)} complete records into pandas_processor")

                # Execute tool
                result = tool_func.invoke(args)

                # Post-process: Handle results based on tool type
                if tool_name == "resolve_entity":
                    # Store entity resolution results
                    if isinstance(result, dict):
                        status = result.get("status")

                        if status == "exact_match":
                            # 儲存已確認的實體
                            resolved_entities.append(result.get("data"))
                            llm_result = result

                        elif status == "merged_match":
                            # 自動合併多個同名實體
                            merged_list = result.get("data", [])
                            resolved_entities.extend(merged_list)
                            
                            # 建立訊息告知 LLM
                            names_str = ", ".join([f"{item['name']} ({item['type']} ID:{item['id']})" for item in merged_list])
                            llm_result = {
                                "status": "success", 
                                "message": f"✅ 已自動合併 {len(merged_list)} 個同名實體: {names_str}",
                                "data": merged_list,
                                "instruction": "請根據上述 ID 分別呼叫對應的工具 (例如 query_campaign_basic 用 client_ids, query_investment_budget 用 agency_ids)"
                            }

                        elif status == "needs_confirmation":
                            # 格式化多選項展示 (分組化)
                            candidates = result.get("data", [])
                            
                            # 按類型分組
                            grouped = {}
                            for c in candidates:
                                c_type = c.get("type", "other")
                                if c_type not in grouped:
                                    grouped[c_type] = []
                                grouped[c_type].append(c)
                            
                            type_labels = {
                                "client": "🏢 客戶 (Clients)",
                                "agency": "🏢 代理商 (Agencies)",
                                "brand": "🏷️ 品牌/產品 (Brands)",
                                "campaign": "📢 執行活動 (Campaigns)",
                                "contract": "📄 合約/排期 (Contracts)",
                                "industry": "🏭 產業類別 (Industry)",
                                "sub_industry": "🏭 產業子類別 (Sub-Industry)",
                                "other": "❓ 其他"
                            }
                            
                            formatted_lines = []
                            global_idx = 1
                            
                            # 按照優先順序顯示類別
                            for t in ["industry", "sub_industry", "client", "agency", "brand", "campaign", "contract", "other"]:
                                if t in grouped:
                                    formatted_lines.append(f"\n**{type_labels.get(t, t)}**")
                                    for item in grouped[t]:
                                        meta_str = ""
                                        if "metadata" in item:
                                            m = item["metadata"]
                                            meta_parts = []
                                            if "year" in m: meta_parts.append(str(m["year"]))
                                            if "status" in m: meta_parts.append(m["status"])
                                            if meta_parts:
                                                meta_str = f" _({', '.join(meta_parts)})_"
                                        
                                        formatted_lines.append(
                                            f"{global_idx}. {item['name']}{meta_str}"
                                        )
                                        # 更新候選人數據中的索引，以便後續匹配
                                        item["temp_idx"] = global_idx
                                        global_idx += 1

                            llm_result = {
                                "status": "needs_confirmation",
                                "message": result.get("message"),
                                "instruction": "⚠️ 找到多個匹配項，請向使用者展示以下分組選項並要求其選擇：",
                                "formatted_list": "\n".join(formatted_lines),
                                "candidates_data": candidates,
                                "note": "當使用者回覆後，優先根據編號或名稱進行匹配"
                            }

                        elif status == "rag_results":
                            # 格式化 RAG 結果展示
                            rag_data = result.get("data", [])
                            formatted_rag = []
                            for idx, item in enumerate(rag_data, 1):
                                formatted_rag.append(
                                    f"{idx}. {item.get('value')} (相似度: {item.get('score', 0):.2f}) - 來源: {item.get('table')}.{item.get('source')}"
                                )

                            llm_result = {
                                "status": "rag_results",
                                "message": result.get("message"),
                                "instruction": "🔍 LIKE 查詢無結果，但 RAG 找到以下相似實體：",
                                "rag_suggestions": formatted_rag,
                                "note": "請向使用者確認是否使用這些建議，或要求其提供更準確的名稱"
                            }

                        else:
                            # not_found 或其他狀態
                            llm_result = result
                    else:
                        llm_result = result

                elif ("query_" in tool_name and tool_name != "query_performance_metrics") or tool_name == "execute_sql_template":
                    # Store SQL query results (from MySQL templates)
                    if isinstance(result, dict):
                        final_data = result
                        latest_query_data = result.get("data", [])  # Store complete data

                        # Convert Decimal to float for JSON serialization
                        from decimal import Decimal
                        def _convert_decimals(obj):
                            if isinstance(obj, dict):
                                return {k: _convert_decimals(v) for k, v in obj.items()}
                            elif isinstance(obj, list):
                                return [_convert_decimals(item) for item in obj]
                            elif isinstance(obj, Decimal):
                                return float(obj)
                            else:
                                return obj

                        sample_preview = _convert_decimals(result.get("data", [])[:5])

                        # Return simplified version to LLM with metadata
                        llm_result = {
                            "status": result.get("status"),
                            "count": result.get("count"),
                            "message": f"✅ 查詢成功！共 {result.get('count')} 筆數據已準備好。",
                            "instruction": "完整數據 ({0} 筆) 已載入，請使用 pandas_processor 處理".format(result.get("count")),
                            "columns": list(result.get("data", [{}])[0].keys()) if result.get("data") else [],
                            "sample_preview": sample_preview,
                            "generated_sql": result.get("generated_sql", "")  # 🔍 顯示執行的 SQL
                        }
                    else:
                        llm_result = result

                elif tool_name == "query_performance_metrics":
                    # Store performance query results (from ClickHouse)
                    if isinstance(result, dict):
                        final_data = result
                        latest_query_data = result.get("data", [])

                        from decimal import Decimal
                        def _convert_decimals(obj):
                            if isinstance(obj, dict):
                                return {k: _convert_decimals(v) for k, v in obj.items()}
                            elif isinstance(obj, list):
                                return [_convert_decimals(item) for item in obj]
                            elif isinstance(obj, Decimal):
                                return float(obj)
                            else:
                                return obj

                        sample_preview = _convert_decimals(result.get("data", [])[:5])

                        llm_result = {
                            "status": result.get("status"),
                            "count": result.get("count"),
                            "message": f"✅ 成效查詢成功！共 {result.get('count')} 筆數據已準備好。",
                            "instruction": "完整數據 ({0} 筆) 已載入，請使用 pandas_processor 處理".format(result.get("count")),
                            "columns": list(result.get("data", [{}])[0].keys()) if result.get("data") else [],
                            "sample_preview": sample_preview
                        }
                    else:
                        llm_result = result

                elif tool_name == "pandas_processor":
                    # Store processed data
                    if isinstance(result, dict) and result.get("status") == "success":
                        final_data = result
                    llm_result = result

                else:
                    llm_result = result

                # Convert result to JSON-safe format (handle Decimal, datetime, etc.)
                def convert_to_json_safe(obj):
                    """Convert non-JSON-serializable objects to JSON-safe types"""
                    from decimal import Decimal
                    from datetime import datetime, date
                    import math

                    if isinstance(obj, float):
                        if math.isnan(obj) or math.isinf(obj):
                            return None
                        return obj
                    elif isinstance(obj, dict):
                        return {k: convert_to_json_safe(v) for k, v in obj.items()}
                    elif isinstance(obj, list):
                        return [convert_to_json_safe(item) for item in obj]
                    elif isinstance(obj, Decimal):
                        return float(obj)
                    elif isinstance(obj, (datetime, date)):
                        return obj.isoformat()
                    else:
                        return obj

                llm_result = convert_to_json_safe(llm_result)

                messages.append(ToolMessage(
                    tool_call_id=tool_call["id"],
                    content=json.dumps(llm_result, ensure_ascii=False, indent=2)
                ))

            except Exception as e:
                error_msg = f"Tool execution error: {str(e)}"
                print(f"ERROR [DataAnalyst] {error_msg}")
                messages.append(ToolMessage(
                    tool_call_id=tool_call["id"],
                    content=error_msg
                ))

    # Ensure final_data is JSON safe
    if final_data:
        # Re-define or reuse convert_to_json_safe if needed, but since it was inner function, 
        # we need to define it again or rely on the fact that we process final_data if we caught it inside the loop.
        # However, final_data was assigned result BEFORE conversion in the loop:
        # if isinstance(result, dict) and result.get("status") == "success": final_data = result
        # So final_data still has Decimals.
        
        from decimal import Decimal
        from datetime import datetime, date
        import math
        
        def _final_convert(obj):
            if isinstance(obj, float):
                if math.isnan(obj) or math.isinf(obj):
                    return None
                return obj
            elif isinstance(obj, dict):
                return {k: _final_convert(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [_final_convert(item) for item in obj]
            elif isinstance(obj, Decimal):
                return float(obj)
            elif isinstance(obj, (datetime, date)):
                return obj.isoformat()
            else:
                return obj
                
        final_data = _final_convert(final_data)

    # Return updated state
    return {
        "analyst_data": final_data,
        "resolved_entities": resolved_entities,
        "final_response": markdown_response,
        "messages": [AIMessage(content=markdown_response)],
        "next": "END"
    }
