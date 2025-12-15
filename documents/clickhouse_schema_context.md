# Technical Documentation: Ad Performance Analytics (ClickHouse)

## 1\. 系統架構概述

此部分描述廣告系統的 **OLAP (Online Analytical Processing)** 層。
所有的廣告事件 (Impression, Click, View) 經由 Ad Server 產生後，透過 Kafka 串流進入 ClickHouse。為了查詢效能，我們不將廣告活動設定（如活動名稱、客戶名稱）直接寫入事件流，而是透過 **ClickHouse Dictionaries** 即時關聯 MySQL 中的設定資料。

### 資料流向 (Data Pipeline)

1.  **MySQL**: 儲存合約與設定 (`one_campaigns`, `pre_campaign_detail`)。
2.  **Dictionaries**: ClickHouse 定期從 MySQL 同步 Metadata (如 `view_pid_attributes`)。
3.  **Kafka**: 接收 Ad Server 的原始 Log (`summing_ad_formats`)。
4.  **ClickHouse View**: `summing_ad_format_events_view` 將 Log 與 Dictionaries 結合，產出可讀的寬表。

-----

## 2\. 核心視圖：`summing_ad_format_events_view`

此 View 是數據分析的主要入口，它將底層的 `pid` (Placement ID) 轉換為具體的業務維度。

### 2.1 維度豐富化 (Enrichment via Dictionaries)

系統大量使用 `dictGet` 函數從 `view_pid_attributes` 字典獲取資訊。這意味著如果 MySQL 中的活動名稱修改，ClickHouse 查詢結果會即時或準即時更新，無需重洗歷史數據。

| ClickHouse 欄位 | 來源字典 Key | 對應 MySQL 資料表 (推測) | 說明 |
| :--- | :--- | :--- | :--- |
| `pid` | (Raw Event) | `pre_campaign_detail.pid` | **版位 ID** (事件的核心關聯鍵) |
| `uid` | `uid` | `pre_campaign_detail.uid` | 單元 ID |
| `plaid` | `plaid` | - | 平台 ID / Placement ID |
| `cmpid` | `cmpid` | `one_campaigns.id` | **活動 ID** (Campaign ID) |
| `client_id` | `client_id` | `cue_lists.client_id` | 客戶 ID |
| `product_line_id`| `product_line_id`| `cue_product_lines.id` | 產品線 ID |
| `ad_format_type_id`| `ad_format_type_id`| `ad_format_types.id` | 廣告形式 ID |

### 2.2 關鍵邏輯定義 (Business Logic Definitions)

在 View 的定義中，包含了幾個寫死的業務邏輯轉換：

#### A. Campaign Type Mapping (活動類型定義)

系統透過 `multiIf` 將數值型的 `campaign_type` 轉換為可讀字串。這定義了廣告的**投放模式**。

  * `speed` (2, 6, 3): 加速投放 / 不指定媒體。
  * `direct` (1, 5): 指定媒體投放 (Direct Buy)。
  * `ron` (4): Run of Network (全網投放)。
  * `external` (7): 外部流量採購。
  * `dsp` (8) / `dsp-creative` (9): 程式化購買 / DSP 素材。
  * `superdsp` (11): 進階 DSP 投放。

#### B. Video Duration Logic (影片秒數判定)

影片長度的判定有優先順序：

1.  優先查詢 **素材表** (`view_material_videos` - 對應 MySQL `videos` 表)。
2.  若素材未定義，則查詢 **版位設定** (`view_pid_attributes` - 對應 MySQL `pre_campaign_detail` 設定)。

<!-- end list -->

```sql
if(dictGetInt32(..., 'video_duration', vid) = 0, 
   dictGetInt32(..., 'video_duration', pid), 
   dictGetInt32(..., 'video_duration', vid))
```

#### C. Device Type Logic (裝置判定)

透過 `os` (作業系統) 與 `brd` (瀏覽器/品牌) 判斷裝置類型：

  * **1 (Desktop)**: `is_desktop = 1` (來自 `brd = '^'`)
  * **2 (iOS)**: `is_ios = 1`
  * **3 (Android)**: `is_android = 1`
  * **0 (Unknown)**: 其他

-----

## 3\. 成效指標聚合 (Metric Aggregation)

根據提供的 SQL 查詢，以下是成效報表的計算邏輯。這是產生給客戶報表 (Report) 的核心算法。

### 3.1 基礎指標

  * **Total Impressions (`total_impressions`)**:
      * `SUM(impression)`
      * 標準的曝光計數。
  * **Total Clicks (`total_clicks`)**:
      * `SUM(bannerClick + videoClick)`
      * 合併計算 Banner 點擊與 Video 點擊。
  * **Views / Quartiles**:
      * `SUM(q100)`: 完整觀看數 (100% 完成)。
      * `SUM(view3s)`: 觀看滿 3 秒數 (通常作為計費標準或有效觀看門檻)。

### 3.2 進階指標：有效曝光 (Effective Impressions)

這是一個特殊的商業邏輯，用於處理不同來源的計數標準差異。

```sql
SUM(CASE 
    WHEN `ad_type` = 'dsp-creative' THEN `cv` 
    ELSE `impression` 
END) AS `effective_impressions`
```

  * **一般廣告**: 使用 `impression` (廣告渲染成功) 作為有效曝光。
  * **DSP 廣告 (`dsp-creative`)**: 使用 `cv` (Candidate View / 候選曝光) 作為有效曝光。
      * *背景知識*: 在 RTB/DSP 環境中，有時會在「競價成功」或「準備投遞」時記錄 `cv`，因為外部 DSP 的 Impression 定義可能與內部 Ad Server 不同，需以此進行正規化。

### 3.3 互動指標 (Engagement)

  * **Total Engagements**: `SUM(eng)`
      * 包含滑鼠互動、開啟聲音、展開全螢幕等定義在 `eng` 事件中的總和。

### 3.4 衍生指標 (Derived Metrics)

以下指標必須在 SQL 中動態計算：

  * **CTR (Click-Through Rate)**:
      * `(SUM(bannerClick + videoClick) / SUM(CASE WHEN ad_type = 'dsp-creative' THEN cv ELSE impression END)) * 100`
      * 公式: `Total Clicks / Effective Impressions * 100`
  * **VTR (View-Through Rate)**:
      * `(SUM(q100) / SUM(CASE WHEN ad_type = 'dsp-creative' THEN cv ELSE impression END)) * 100`
      * 公式: `Total Q100 Views / Effective Impressions * 100`
  * **ER (Engagement Rate)**:
      * `(SUM(eng) / SUM(CASE WHEN ad_type = 'dsp-creative' THEN cv ELSE impression END)) * 100`
      * 公式: `Total Engagements / Effective Impressions * 100`

-----

## 4\. 查詢過濾條件範例 (Where Clause Context)

SQL 範例中展示了報表生成的常見過濾模式：

1.  **時間區間**: `day_local BETWEEN 'Start' AND 'End'` (利用 Partition Key 進行索引過濾)。
2.  **Campaign 過濾**: `cmpid IN (...)` (鎖定特定的 `one_campaigns.id`)。
3.  **格式過濾**: `ad_format_type_id IN (...)` (只計算特定格式，如排除非標準版位)。

-----

## 5\. MySQL 與 ClickHouse 對照表

此表總結了前幾份文件 (MySQL) 與此文件 (ClickHouse) 的欄位對應關係。

| 概念層級 | MySQL Table | MySQL Column | ClickHouse View Column | 備註 |
| :--- | :--- | :--- | :--- | :--- |
| **活動 (Campaign)** | `one_campaigns` | `id` | `cmpid` | |
| | `one_campaigns` | `name` | `campaign_name` | 經由 Dictionary |
| **執行單 (Placement)** | `pre_campaign_detail` | `pid` | `pid` | 核心 Key |
| | `pre_campaign_detail` | `uid` | `uid` | |
| **客戶 (Client)** | `cue_lists` | `client_id` | `client_id` | 經由 Dictionary |
| **產品與格式** | `cue_product_lines` | `id` | `product_line_id` | |
| | `ad_format_types` | `id` | `ad_format_type_id` | |
| **素材 (Creative)** | `videos` (推測) | `id` | `vid` | 用於查詢 Video Duration |
