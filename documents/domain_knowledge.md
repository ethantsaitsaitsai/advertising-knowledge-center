# Domain Knowledge: Ad Tech Logic & Business Rules

**Version:** 1.0
**Last Updated:** 2025-12-11
**Audience:** InsightAgent, DataFusion ETL, Data Engineers

## 1. 跨系統對映 (Cross-System Entity Mapping)

此章節定義 **MySQL (交易資料庫)** 與 **ClickHouse (分析資料庫)** 之間的核心關聯鍵。進行跨庫 Join 或 ETL 時必須嚴格遵守此對照。

| 實體概念 (Entity) | MySQL Table.Column | ClickHouse Column (View) | 關聯性質 | 備註 |
| :--- | :--- | :--- | :--- | :--- |
| **Campaign (活動)** | `one_campaigns.id` | `cmpid` | **1:1** (Core Key) | 分析時最常用的聚合維度。 |
| **Placement (版位/執行單)** | `pre_campaign_detail.pid` | `pid` | **1:1** (Core Key) | ClickHouse 中的事件原子單位。 |
| **Unit (單元)** | `pre_campaign_detail.uid` | `uid` | **1:1** | 通常用於更細的版位識別。 |
| **Client (客戶)** | `cue_lists.client_id` | `client_id` | **1:1** | 經由 Dictionary (`view_pid_attributes`) 關聯。 |
| **Video Creative (影片素材)** | `videos.id` (Inferred) | `vid` | **1:1** | 用於判斷影片秒數 (`video_duration`)。 |
| **Ad Format (廣告形式)** | `ad_format_types.id` | `ad_format_type_id` | **1:1** | |

> **⚠️ DataFusion 注意事項：**
> ClickHouse 的 `summing_ad_format_events_view` 已經透過 Dictionaries 完成了大部分的 Name Mapping。在做基礎報表時，通常不需要回查 MySQL，除非需要取得「預算 (`budget`)」、「KPI 承諾 (`cue_list_budgets`)」或「受眾設定 (`target_segments`)」等靜態資料。

---

## 2. 成效指標公式 (Official Metrics Formulas)

所有報表與 AI 解讀必須使用以下標準公式，嚴禁自創算法。

### 2.1 基礎計數 (Base Counts)
* **Total Impressions (總曝光數)**: `SUM(impression)`
* **Effective Impressions (有效曝光數)**:
    * 邏輯：若 `campaign_type` 為 DSP 相關 (`dsp-creative`)，以 `cv` (Candidate View) 為準；否則以 `impression` 為準。
    * SQL: `SUM(IF(ad_type = 'dsp-creative', cv, impression))`
* **Total Clicks (總點擊數)**: `SUM(bannerClick + videoClick)`
* **Total Engagements (總互動數)**: `SUM(eng)`
    * 定義：包含開啟聲音、暫停、全螢幕、滑鼠懸停特定秒數等互動行為。

### 2.2 衍生指標 (Derived Metrics)

| 指標名稱 | 縮寫 | 公式 (Calculation) | 業務意義 |
| :--- | :--- | :--- | :--- |
| **Click-Through Rate** | **CTR** | `Total Clicks / Effective Impressions` | 衡量廣告吸引點擊的能力。 |
| **View-Through Rate** | **VTR** | `SUM(q100) / Effective Impressions` | **完整觀看率**。衡量影音廣告是否被看完。 |
| **Engagement Rate** | **ER** | `Total Engagements / Effective Impressions` | 衡量使用者與廣告互動的頻率。 |
| **Play Rate** | **-** | `SUM(view3s) / Effective Impressions` | **播放率**。有多少比例的使用者看了至少 3 秒。 |
| **Cost Per Mille** | **CPM** | `(Budget Consumed / Effective Impressions) * 1000` | 每千次曝光成本。 |
| **Cost Per Click** | **CPC** | `Budget Consumed / Total Clicks` | 每次點擊成本。 |

> **💡 InsightAgent 提示：**
> 在計算 VTR 時，分母務必使用 **Effective Impressions**。在某些舊版邏輯中可能會誤用 `view3s` 當分母，這會導致數據虛高 (變成 Completion Rate of Starters)，請務必小心。

---

## 3. 業務解讀與門檻 (Business Interpretation)

當 AI 需要對數據進行「質性描述」時（例如：成效好壞、是否異常），請參考以下基準。

### 3.1 成效基準 (Benchmarks)
*(註：此為通用建議值，實際值需依據 `cue_list_budgets` 中的 `_lb` (Lower Bound) 欄位為準)*

* **CTR (點擊率):**
    * **Display/Banner:** > 0.3% (及格), > 0.5% (優異)
    * **Video:** > 1.0% (及格), > 1.5% (優異)
    * **異常低:** < 0.1% (可能素材有問題或版位錯置)
* **VTR (完整觀看率):**
    * **Non-Skippable (不可略過):** 通常在 70% - 90%。
    * **Skippable/Out-stream:** > 15% (及格), > 30% (優異)。
    * **警示:** 若 VTR 低於 `cue_list_budgets.vtr_lb` 設定的下限，代表違約風險，需標記為 **URGENT**。

### 3.2 預算層級解讀 (Budget Hierarchy Context)
當使用者問「剩多少錢？」時，必須確認對方的角色：

1.  **財務/老闆 (L1)**: 看 `cue_lists.total_budget`。這是營收。
2.  **AM/專案經理 (L2)**: 看 `one_campaigns.budget`。這是波段分配款。
3.  **Ad Ops/系統 (L3)**: 看 `pre_campaign.budget`。**這是系統實際能跑的上限**。
    * *DataFusion 邏輯*: 計算 Pacing (消耗速度) 時，分母請一律使用 **L3 Budget**。

---

## 4. 資料過濾與狀態邏輯 (Filtering & Status Logic)

### 4.1 排除無效數據
在生成報表時，必須強制套用以下過濾條件，以免將垃圾數據計入：

* **MySQL 過濾**:
    * `cue_lists.status` != `archived`, `cancelled` (除非要做歷史分析)
    * `pre_campaign.status` != `trash`, `aborted`, `draft`
* **ClickHouse 過濾**:
    * `plaid != 0` (排除無效版位 Log)
    * `cmpid` 必須存在於 `one_campaigns` (排除孤兒數據)

### 4.2 廣告活動類型 (Campaign Types)
ClickHouse 中的 `campaign_type_name` 是分析的重要維度：

* **`speed` (加速)**: 重點在「快速消耗預算」，CTR/VTR 通常會略低，不用過度警示。
* **`direct` (指定)**: 重點在「特定媒體表現」，需細看 `publisher` 欄位。
* **`dsp` / `programmatic`**: 重點在「受眾精準度」，CPM 通常是浮動的。

---

## 5. 給 InsightAgent 的指令 (Directives for AI)

當你 (AI) 接收到用戶詢問時，請遵循以下思考路徑：

1.  **Intent Classification**:
    * 問「營收/合約」 -> 查詢 `cue_lists` (MySQL)。
    * 問「成效/點擊/曝光」 -> 查詢 `summing_ad_format_events_view` (ClickHouse)。
    * 問「受眾/人群」 -> 查詢 `target_segments` (MySQL)。

2.  **Context Checking**:
    * 查詢成效前，先檢查 `cue_list_budgets` 是否有設定 **KPI 保證 (Guarantee)**。
    * 如果目前的 CTR < `ctr_lb`，你的回答語氣應該是 **"警示 (Warning)"** 而非單純回報數字。

3.  **Data Synthesis**:
    * 不要只給數字。
    * **Bad Example**: "本週 CTR 為 0.8%。"
    * **Good Example**: "本週 CTR 為 0.8%，雖然低於上週的 1.0%，但仍高於合約保證的 0.5% (LB)，成效在安全範圍內。"

---

## 6. 給 DataFusion 的指令 (Directives for Python Code)

* **ETL 頻率**: 建議 ClickHouse View 為即時查詢，但若需與 MySQL `cue_list_budgets` 進行 JOIN 分析，建議每小時 (Hourly) 快取一次 MySQL 的設定檔。
* **ID 處理**: 所有 ID 欄位 (`cmpid`, `pid`) 在 Python 中應視為 `String` 或 `Int64` 處理，避免溢位。
* **Null Handling**: `onead_gift` 或 `external_budget` 若為 Null，請在計算時視為 `0`。