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
    execute_sql_template,
    query_industry_format_budget
)
from tools.performance_tools import query_performance_metrics, query_format_benchmark
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
    query_industry_format_budget,
    query_performance_metrics,
    query_format_benchmark,
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
     - **參數強制規則 (Mandatory Params)**:
       - **必須且只能使用 `cmp_ids`**。
       - **嚴禁** 使用 `client_names` 查詢成效，因為 ClickHouse 中的名稱匹配極不穩定。
       - **標準流程**:
         1. 永遠先呼叫 `query_campaign_basic` 取得該客戶或活動的 Campaign IDs。
         2. 將取得的 `campaign_id` 列表傳入 `query_performance_metrics(cmp_ids=[...])`。
     - **維度說明**:
       - `dimension='format'`: 按廣告格式分組（預設）。
       - `dimension='campaign'`: 按活動分組。

   **統計與基準工具 (Statistical & Benchmark Tools)**:
   - `query_industry_format_budget`: 多維度預算分佈統計
     - **參數 dimension (重要)**:
       - `dimension='industry'` (預設): 大類產業。
       - `dimension='sub_industry'`: 子類產業 (推薦用於詳細產業分析)。
       - `dimension='client'`: 客戶。
       - `dimension='agency'`: 代理商。
     - **參數 split_by_format**:
       - `True`: 顯示格式細節 (預設)。
       - `False`: 僅顯示總計。
     - **參數 primary_view**:
       - `'dimension'` (預設): 第一欄為產業/客戶。
       - `'format'`: 第一欄為格式。
     - **使用範例**:
       - 查「Banner 投到哪些產業」: `dimension='industry'`, `format_ids=[BannerID]`, `primary_view='format'`
       - 查「Banner 的前十大客戶」: `dimension='client'`, `format_ids=[BannerID]`, `primary_view='format'`
       - 查「所有格式投放到的產業」: `dimension='industry'`, `primary_view='format'`
       - 查「汽車產業的格式分佈」: `dimension='industry'`, `industry_ids=[AutoID]`, `primary_view='dimension'`

   - `query_format_benchmark`: 查詢格式成效基準與排名
     - 適用：查詢「所有格式的 CTR 排名」、「汽車產業的平均 VTR」等**基準型**問題。
     - **優點**：直接回傳 CTR/VTR 平均值與排名，無需處理個別 Campaign。
     - 參數：cmp_ids (選填，用於產業篩選), format_ids (選填)。

   **進階工具**:
   - `execute_sql_template`: 通用模板執行器
     - 適用：media_placements.sql, product_lines.sql, contract_kpis.sql, execution_status.sql
     - **重要**: 若使用者詢問「**廣告格式與執行金額**」(按格式分出的認列金額)，請優先使用 `media_placements.sql`。該模板包含 `ad_format_name` 與執行層級的 `budget`。
     - 若需過濾產業，可使用 `industry_ids` (Category) 或 `sub_industry_ids` (Sub-Category) 參數。
     - 只在上述專用工具不適用時才使用

3. **判斷日期範圍 (重要)**
   - **系統已指定查詢範圍**:
     - **Start Date**: {start_date}
     - **End Date**: {end_date}
   - **請務必將此日期範圍應用於所有查詢工具的 `start_date` 與 `end_date` 參數。**
   - **最終回應要求**:
     - 在回答開頭或結尾，必須明確說明：「**本數據涵蓋範圍: {start_date} 至 {end_date}**」。

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
      - **核心原則**: 無論使用者問了多少個維度，最終**只能輸出一張整合表格**。
      - **Step 1: 決定主表 (Anchor Table)**
        - 若查詢包含「投資金額」、「預算分配」→ 主表為 `query_investment_budget` (Format Level)。
        - 若查詢包含「廣告格式」、「成效」→ 主表為 `query_ad_formats` 或 `query_performance_metrics` (Format Level)。
      - **Step 2: 準備屬性資料 (Attributes)**
        - **Segments**: 呼叫 `query_targeting_segments`，並**務必**先用 `groupby_concat` 壓平成 "One Row per Campaign" (concat_col="segment_name")。
      - **Step 3: 執行合併 (Left Join Sequence) - 這是最關鍵的一步！**
        - 你不能分開展示「投資金額表」和「成效表」。你必須使用 `pandas_processor(operation="merge", ...)` 將它們合而為一。
        - **順序**:
          1. 取得主表資料 (例如 Investment)。
          2. 取得副表資料 (例如 Performance)。
          3. 呼叫 `pandas_processor(operation="merge", data=主表, merge_data=副表, merge_on="format_type_id" or "campaign_id", ...)`。
          4. 若還有 Segments，再將結果與 Segments 表進行 Merge。
      
      **Mandatory Output Step (強制輸出步驟)**:
      - **當你已經呼叫了任何 `query_*` 工具並獲得資料後，你必須且只能做一件事：**
      - **呼叫 `pandas_processor` 輸出最終合併表**。
      - **重要參數**: 
        - 務必使用 `select_columns` 指定使用者感興趣的所有欄位 (例如 `['廣告格式', '投資金額', 'CTR', '數據鎖定']`)。
        - 如果你沒指定 `select_columns`，或者你的表中缺少了某些欄位 (因為沒 Merge)，使用者會覺得你沒回答完整。
      - **禁止**：禁止在獲得 SQL 資料後，不經過 pandas_processor 直接回答「資料如下...」。
      - **禁止**：禁止分開輸出多張小表，必須 Merge 成一張大表。
5. **最終回應 (Critical)**
   - 請提供簡潔的數據洞察，並以「詳細數據如下表：」作為結尾。
   - **不要** 輸出表格內容。

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
    
    # [NEW] Extract dates
    start_date = routing_context.get("start_date")
    end_date = routing_context.get("end_date")
    
    # Fallback default dates if not provided (safety net)
    if not start_date or not end_date:
        start_date = f"{last_year}-01-01"
        end_date = f"{current_year}-12-31"
        print(f"DEBUG [DataAnalyst] Using fallback dates: {start_date} ~ {end_date}")
    else:
        print(f"DEBUG [DataAnalyst] Using router provided dates: {start_date} ~ {end_date}")

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

    # Initialize logs
    execution_logs = []

    print(f"DEBUG [DataAnalyst] Starting analysis for: {original_query[:100]}...")
    print(f"DEBUG [DataAnalyst] Context: entities={entity_keywords}, time={time_keywords}, hint={analysis_hint}")
    print(f"DEBUG [DataAnalyst] Current date: {current_date}, Year: {current_year}")

    # Log initial context
    execution_logs.append({
        "step": "start",
        "timestamp": datetime.now().isoformat(),
        "query": original_query,
        "context": {
            "entity_keywords": entity_keywords,
            "time_keywords": time_keywords,
            "start_date": start_date,
            "end_date": end_date,
            "analysis_hint": analysis_hint,
            "resolved_entities_count": len(resolved_entities_state)
        }
    })

    # Build conversation with system prompt
    messages = [
        SystemMessage(content=ANALYST_SYSTEM_PROMPT.format(
            current_date=current_date,
            current_year=current_year,
            last_year=last_year,
            original_query=original_query,
            entity_keywords=entity_keywords,
            time_keywords=time_keywords,
            start_date=start_date, # [NEW]
            end_date=end_date,     # [NEW]
            analysis_hint=analysis_hint or "未指定"
        ) + resolved_context_str),
        HumanMessage(content=f"請協助分析這個查詢：{original_query}")
    ]

    # Agent ReAct Loop (max 15 iterations to prevent infinite loops)
    final_data = None
    markdown_response = ""
    cached_markdown_table = ""  # Store the perfect table from tool
    has_reminded_to_process = False # Failsafe flag

    # Initialize with state values to preserve memory
    resolved_entities = list(resolved_entities_state)
    latest_query_data = None  # Store complete SQL result for pandas_processor

    for iteration in range(15):
        print(f"DEBUG [DataAnalyst] Iteration {iteration + 1}")

        # Invoke LLM with tools
        response = llm_with_tools.invoke(messages)
        
        # Check if LLM returned final answer (no tool calls)
        if not response.tool_calls:
            # --- [NEW] Failsafe: Check if LLM tried to finish without processing data ---
            has_query = any("query_" in str(log.get("tool")) or log.get("tool") == "execute_sql_template" 
                            for log in execution_logs if log.get("step") == "tool_call")
            has_processor = any(log.get("tool") == "pandas_processor" 
                                for log in execution_logs if log.get("step") == "tool_call")
            
            if has_query and not has_processor and not has_reminded_to_process:
                print("DEBUG [DataAnalyst] LLM tried to finish without pandas_processor. Injecting reminder.")
                has_reminded_to_process = True
                messages.append(AIMessage(content="我已經收集完資料，現在準備進行整合。")) # 讓歷史記錄連貫
                messages.append(HumanMessage(content="[系統提示] 你已經查詢了數據，但尚未呼叫 pandas_processor 進行資料合併與表格產出。請務必使用 pandas_processor(operation='merge', ...) 整合所有維度（包含投資金額、成效、受眾等）並輸出最終表格。禁止直接結束！"))
                continue # Re-run loop with the reminder
            
            messages.append(response)
            markdown_response = response.content
            if isinstance(markdown_response, list):
                markdown_response = " ".join([
                    item.get("text", "") if isinstance(item, dict) else str(item)
                    for item in markdown_response
                ])
            print(f"DEBUG [DataAnalyst] Agent finished with response: {markdown_response[:200]}...")
            
            execution_logs.append({
                "step": "finish",
                "timestamp": datetime.now().isoformat(),
                "response_preview": markdown_response[:200]
            })
            break

        messages.append(response)
        # Execute tool calls
        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            args = tool_call["args"]

            print(f"DEBUG [DataAnalyst] Calling tool: {tool_name}")
            print(f"DEBUG [DataAnalyst] Arguments: {args}")

            # Log tool call
            execution_logs.append({
                "step": "tool_call",
                "timestamp": datetime.now().isoformat(),
                "iteration": iteration + 1,
                "tool": tool_name,
                "args": args
            })

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
                "query_industry_format_budget": query_industry_format_budget,
                "query_performance_metrics": query_performance_metrics,
                "query_format_benchmark": query_format_benchmark,
                "pandas_processor": pandas_processor
            }

            tool_func = tool_map.get(tool_name)
            if not tool_func:
                error_msg = f"Error: Tool '{tool_name}' not found."
                messages.append(ToolMessage(
                    tool_call_id=tool_call["id"],
                    content=error_msg
                ))
                execution_logs.append({
                    "step": "tool_error",
                    "timestamp": datetime.now().isoformat(),
                    "tool": tool_name,
                    "error": error_msg
                })
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
                    
                    execution_logs.append({
                        "step": "data_injection",
                        "timestamp": datetime.now().isoformat(),
                        "tool": tool_name,
                        "data_count": len(latest_query_data)
                    })

                # Execute tool
                result = tool_func.invoke(args)
                
                # Log tool result (summary)
                log_entry = {
                    "step": "tool_result",
                    "timestamp": datetime.now().isoformat(),
                    "tool": tool_name,
                    "status": "unknown"
                }

                # Post-process: Handle results based on tool type
                if tool_name == "resolve_entity":
                    # Store entity resolution results
                    if isinstance(result, dict):
                        status = result.get("status")
                        log_entry["status"] = status

                        if status == "exact_match":
                            # 儲存已確認的實體
                            resolved_entities.append(result.get("data"))
                            llm_result = result
                            log_entry["details"] = f"Resolved: {result.get('data', {}).get('name')}"

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
                            log_entry["details"] = f"Merged {len(merged_list)} entities"

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
                            log_entry["details"] = f"Found {len(candidates)} candidates"

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
                            log_entry["details"] = f"Returned {len(rag_data)} RAG results"

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
                        
                        log_entry["status"] = result.get("status")
                        log_entry["row_count"] = result.get("count")
                        log_entry["generated_sql"] = result.get("generated_sql", "")

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
                        
                        log_entry["status"] = result.get("status")
                        log_entry["row_count"] = result.get("count")

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
                        log_entry["status"] = "success"
                        log_entry["processed_count"] = result.get("count")
                        
                        # Capture the perfect markdown table
                        if "markdown" in result and result["markdown"]:
                            cached_markdown_table = result["markdown"]
                            print(f"DEBUG [DataAnalyst] Cached markdown table ({len(cached_markdown_table)} chars)")

                    llm_result = result

                else:
                    llm_result = result

                # Append log entry
                execution_logs.append(log_entry)

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
                execution_logs.append({
                    "step": "tool_exception",
                    "timestamp": datetime.now().isoformat(),
                    "tool": tool_name,
                    "error": str(e)
                })

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
        
        # Remove generated_sql from final output (keep it in debug_logs only)
        if isinstance(final_data, dict) and "generated_sql" in final_data:
            del final_data["generated_sql"]

    # --- Programmatic Table Append Logic ---
    # If we have a cached perfect table from pandas_processor, append it to the final response.
    # This prevents the LLM from trying to re-type it and hallucinating format errors.
    if cached_markdown_table:
        # [NEW] Anti-Duplication Filter
        # Check if LLM already hallucinated a table in markdown_response
        import re
        # Look for typical markdown table headers or separators
        table_pattern = re.compile(r'\|.*\|.*[\r\n]+\|[-:| ]+\|', re.MULTILINE)
        
        if markdown_response:
            match = table_pattern.search(markdown_response)
            if match:
                print(f"DEBUG [DataAnalyst] Detected hallucinated table in text response. Truncating...")
                # Keep text before the table
                markdown_response = markdown_response[:match.start()].strip()
                # Ensure we have a nice transition
                if not markdown_response.endswith("：") and not markdown_response.endswith(":"):
                    markdown_response += "\n\n詳細數據如下表："

        # Append the perfect cached table
        markdown_response = (markdown_response or "詳細數據如下表：") + "\n\n" + cached_markdown_table
        print(f"DEBUG [DataAnalyst] Appended cached table to final response")

    # Return updated state
    return {
        "analyst_data": final_data,
        "resolved_entities": resolved_entities,
        "final_response": markdown_response,
        "messages": [AIMessage(content=markdown_response)],
        "debug_logs": execution_logs,  # [NEW] Return the detailed execution logs
        "next": "END"
    }
