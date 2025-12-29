# AKC Framework 3.0 技術架構文件

**版本:** 3.1.1 (Master Branch)
**日期:** 2025年12月

## 1. 執行摘要 (Executive Summary)

AKC Framework 3.0 是專為廣告產業設計的 **Text-to-SQL AI Agent**。它允許使用者透過自然語言查詢複雜的廣告數據，跨越兩個異質資料庫系統。本系統已從 v2 的 Supervisor-Worker 架構演進為精簡的 **Intent-Centric Router-Analyst** (意圖導向路由-分析師) 架構，重點優化了準確率、反應速度與實體解析的強韌性。

### 核心能力
*   **雙資料庫查詢:** 無縫整合 metadata/財務數據 (MySQL) 與成效指標數據 (ClickHouse)。
*   **智慧實體解析 (Intelligent Entity Resolution):** 採用多階段策略 (類型感知精準匹配 -> 自動合併 -> 使用者確認 -> RAG 向量搜尋) 來識別客戶、品牌與活動。
*   **SQL 模板化:** 業務邏輯封裝於 Jinja2 SQL 模板中，而非由 LLM 臨時生成 SQL，確保安全性與正確性。
*   **數據後處理:** 使用 Python Pandas 沙箱環境進行精確的聚合運算 (Sums, GroupBys)，避免依賴複雜且易錯的 SQL 子查詢。

---

## 2. 系統架構 (System Architecture)

系統基於 **LangGraph** 進行流程編排，並使用 **LangChain** 進行工具介接。

### 2.1 高層次數據流 (High-Level Data Flow)

```mermaid
graph TD
    User[使用者輸入] --> InputAdapter[輸入適配器]
    InputAdapter --> Router[意圖路由器]
    
    subgraph "Agent Runtime (LangGraph)"
        Router -- "數據查詢" --> Analyst[數據分析師 Agent]
        Router -- "閒聊/無關" --> EndNode[結束]
        
        Analyst --> ER[實體解析器]
        Analyst --> SQL[SQL 模板工具 (MySQL)]
        Analyst --> CH[成效數據工具 (ClickHouse)]
        Analyst --> Pandas[Pandas 處理器]
    end
    
    ER <--> MySQL[(MySQL DB)]
    ER <--> Qdrant[(向量 DB)]
    SQL <--> MySQL
    CH <--> ClickHouse[(ClickHouse DB)]
    
    Analyst --> Response[Markdown 回應]
```

### 2.2 組件細節 (Component Breakdown)

| 組件名稱 | 檔案路徑 | 職責 |
|-----------|-----------|----------------|
| **Input Adapter** (輸入適配器) | `agent/graph.py` | 將來自 CLI、Chainlit UI 或 LangGraph Studio 的輸入標準化為 `HumanMessage` 格式。支援多模態輸入處理。 |
| **Intent Router** (意圖路由器) | `agent/router.py` | 分析使用者查詢，區分 **實體 (Entities)** (如 "Nike") 與 **維度 (Dimensions)** (如 "代理商")。決定路由路徑。 |
| **Data Analyst** (數據分析師) | `agent/analyst.py` | 主要的工作節點。使用 **ReAct** 迴圈來執行實體解析、獲取數據、處理數據並生成答案。 |
| **Entity Resolver** (實體解析器) | `tools/entity_resolver.py` | 透過模糊比對、層級規則與向量搜尋 (RAG)，將自然語言名稱映射為資料庫 ID。 |
| **SQL Engine** (SQL 引擎) | `tools/campaign_template_tool.py` | 對 MySQL 執行預定義的 Jinja2 SQL 模板。 |
| **Performance Engine** (成效引擎) | `tools/performance_tools.py` | 從 ClickHouse 查詢海量成效數據。 |

---

## 3. 核心邏輯與工作流 (Core Logic & Workflows)

### 3.1 意圖路由邏輯 (`agent/router.py`)

Router 是第一道防線，解決常見的「概念 vs 實體」混淆問題。

*   **邏輯:**
    1.  **維度偵測:** 識別 "代理商"、"客戶"、"活動"、"格式" 等詞彙為 *維度*，而非實體。
    2.  **實體提取:** 提取具體名稱 (如 "台北數位"、"春節檔期") 作為 `entity_keywords`。
    3.  **上下文合併:** 若使用者發送簡短的後續追問 (如 "1" 或 "那去年的呢？")，Router 會將其與上一條訊息合併以保留上下文。
    4.  **輸出:** 回傳結構化的 JSON，包含 `route_to` (路由目標)、`entity_keywords`、`time_keywords` 與 `analysis_hint`。

### 3.2 分析師迴圈 (`agent/analyst.py`)

Analyst 使用嚴格定義的 **ReAct** (Reasoning + Acting) 迴圈，並透過 System Prompt 強制執行業務規則。

**System Prompt 強制的關鍵規則:**
*   **禁止 Raw SQL:** Agent *不能* 自行撰寫 SQL。必須使用工具。
*   **強制 Pandas 處理:** Agent *必須* 使用 `pandas_processor` 來計算總和/統計，以保證算術正確性 (LLM 不擅長數學)。
*   **產業橋接 (Industry Bridge):** 查詢 "某產業" 成效時，必須先從 MySQL 取得 Campaign IDs，再用這些 ID 去查 ClickHouse。

### 3.3 實體解析策略 (`tools/entity_resolver.py`)

這是系統中最複雜的演算法，設計用於處理歧義 (例如 "Nike" 可能是客戶名，也可能是品牌名，或是某個活動名稱的一部分)。

**演算法步驟:**

1.  **精準匹配與層級過濾 (優先級 1):**
    *   對所有表格執行 LIKE 查詢。
    *   **類型感知過濾 (Type-Aware Filter):** 若在 "父層級" 類型 (Client/Brand/Agency) 找到完全匹配，系統會 *丟棄* "子層級" 類型 (Campaigns) 的部分匹配結果。
    *   *範例:* 查詢 "悠遊卡"。結果: Client "悠遊卡股份有限公司" vs Campaign "悠遊卡 2024 新春活動"。
    *   *動作:* 系統自動選擇 Client 並忽略 Campaign，避免數據雜訊。

2.  **自動合併 (優先級 2):**
    *   若多個實體擁有完全相同的名稱 (例如 DB 中的重複項目)，它們會被自動合併為一個列表。
    *   Agent 被指示查詢時需使用 *所有* 合併後的 ID。

3.  **使用者確認 (優先級 3):**
    *   若找到多個截然不同且模糊的實體 (例如 "Nike 鞋" vs "Nike 服飾")，工具回傳 `status: "needs_confirmation"`。
    *   Agent 會向使用者展示編號列表供選擇。

4.  **RAG 備援 (優先級 4):**
    *   若 LIKE 查詢結果為 0，系統會查詢向量資料庫 (Qdrant) 尋找語意相似的名稱。

---

## 4. 數據層與工具 (Data Layer & Tools)

### 4.1 MySQL 整合 (Metadata & 財務數據)

*   **連線:** 透過 `config/database.py` 管理。支援 **SSH Tunneling** 進行遠端安全存取。包含連線池 (`pool_recycle`, `pool_pre_ping`) 機制。
*   **工具:** `tools/campaign_template_tool.py`。
*   **模板:** 位於 `templates/sql/`。
    *   `campaign_basic.sql`: 入口點。用於尋找 ID 與基本資訊。
    *   `investment_budget.sql`: "進單/投資" (Internal Budget/Booking)。粒度: Campaign/Format 層級。
    *   `execution_budget.sql`: "執行/認列" (Recognized Revenue/Cost)。粒度: 月/日執行層級。
    *   `media_placements.sql`: 媒體與版位的詳細細分。

### 4.2 ClickHouse 整合 (成效數據)

*   **連線:** 透過 `clickhouse_connect` 經由 HTTPS (Port 8443) 連線。
*   **工具:** `tools/performance_tools.py`。
*   **數據:** 儲存大量的曝光 (Impressions)、點擊 (Clicks)、CTR、VTR、影片觀看數等數據。
*   **優化:** 查詢已依據維度 (`campaign_id`, `format`, `date`) 進行預聚合，確保亞秒級的查詢延遲。

### 4.3 Pandas 處理器 (`tools/data_processing_tool.py`)

一個用於安全數據操作的沙箱環境。

*   **原因:** LLM 不擅長數學運算，且動態生成的 SQL `GROUP BY` 邏輯容易出錯。
*   **運作方式:**
    1.  Agent 查詢數據 -> 工具回傳 JSON。
    2.  Agent 呼叫 `pandas_processor` 並指定操作 (如 `operation="groupby_sum"` 或 `operation="add_time_period"`)。
    3.  Python 程式計算結果並生成 Markdown 表格字串。
    4.  Agent 直接將 Markdown 表格回傳給使用者。

---

## 5. SQL 模板實作細節 (SQL Template Implementation)

本框架放棄讓 LLM 動態生成 SQL 的做法，轉而採用 **Jinja2 SQL 模板**。這確保了複雜商業邏輯（如：進單金額 vs 認列金額的定義）的一致性與安全性。

### 5.1 技術堆疊
*   **模板引擎**: Jinja2 (`templates/sql/`)
*   **執行引擎**: SQLAlchemy (MySQL)
*   **參數綁定**: 使用 SQLAlchemy 的 `bindparam` 進行安全綁定，防範 SQL Injection。

### 5.2 核心設計模式
所有模板皆遵循以下模式：
1.  **動態過濾 (Dynamic Filtering)**: 使用 Jinja2 `{% if %}` 區塊來根據 Python 傳入的參數決定是否加入該 `WHERE` 條件。
2.  **列表展開 (List Expansion)**: 自動將 Python 的 `List[int]` 轉換為 SQL 的 `IN (...)` 語法。
3.  **預設邏輯 (Defaults)**: 若未傳入參數，則不加入該限制 (Open Query)，或套用預設的日期範圍。

### 5.3 實作範例：`campaign_basic.sql`
此模板展示了如何處理多種 ID 過濾與名稱搜尋。

```sql
SELECT 
    oc.id AS campaign_id,
    COALESCE(c.advertiser_name, c.company) AS client_name,
    oc.budget,
    oc.status
FROM one_campaigns oc
JOIN cue_lists cl ON oc.cue_list_id = cl.id
JOIN clients c ON cl.client_id = c.id
WHERE 1=1
    -- 動態插入 Campaign IDs 過濾
    {% if campaign_ids %}
    AND oc.id IN ({{ campaign_ids|join(',') }})
    {% endif %}

    -- 動態插入 Client IDs 過濾
    {% if client_ids %}
    AND c.id IN ({{ client_ids|join(',') }})
    {% endif %}

    -- 產業查詢子查詢 (Subquery for Industry)
    {% if industry_ids %}
    AND oc.id IN (
        SELECT one_campaign_id FROM pre_campaign pc 
        WHERE pc.category_id IN ({{ industry_ids|join(',') }})
    )
    {% endif %}
ORDER BY oc.start_date DESC
```

### 5.4 實作範例：`investment_budget.sql`
此模板封裝了複雜的 JOIN 邏輯來計算正確的「進單金額」。

```sql
SELECT
    oc.id AS campaign_id,
    -- 優先使用 Format Title，若無則用 Name
    COALESCE(aft.title, aft.name, 'Unspecified') AS format_name,
    -- 來自合約預算表的金額 (Investment)
    clb.budget AS investment_amount,
    cl.start_date
FROM one_campaigns oc
-- 透過多層 JOIN 關聯到預算表 (cue_list_budgets)
JOIN cue_lists cl ON oc.cue_list_id = cl.id
JOIN cue_list_product_lines clpl ON clpl.cue_list_id = cl.id
JOIN cue_list_ad_formats claf ON claf.cue_list_product_line_id = clpl.id
JOIN cue_list_budgets clb ON clb.cue_list_ad_format_id = claf.id
JOIN ad_format_types aft ON claf.ad_format_type_id = aft.id
WHERE 1=1
    -- 業務邏輯：只計算已轉正式或需求中的單
    AND cl.status IN ('converted', 'requested')
    
    {% if start_date %}
    AND cl.end_date >= '{{ start_date }}'
    {% endif %}
```

---

## 6. 請求生命週期範例 (Request Lifecycle Example)

**使用者查詢:** *"幫我查悠遊卡今年的進單預算。"*

1.  **Input Adapter:** 將字串封裝為 `HumanMessage`。
2.  **Intent Router:**
    *   提取實體: `["悠遊卡"]`
    *   提取時間: `["今年"]` (轉換為 2025 日期範圍)
    *   提示: `"投資金額"` (Investment Budget)
    *   路由至: `DataAnalyst`
3.  **Data Analyst:**
    *   **Call 1:** `resolve_entity(keyword="悠遊卡")`
        *   *結果:* 找到 Client ID 123 ("悠遊卡股份有限公司")。狀態: `exact_match`。
    *   **Call 2:** `query_investment_budget(client_ids=[123], start_date="2025-01-01", ...)`
        *   *結果:* 回傳 50 筆原始預算資料。
    *   **Call 3:** `pandas_processor(operation="groupby_sum", groupby_col="campaign_name", sum_col="budget")`
        *   *結果:* 回傳一個依活動匯總預算的 Markdown 表格。
    *   **Final Answer:** Agent 顯示表格並加上文字摘要回應使用者。