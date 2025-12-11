### 技術文件：廣告系統資料庫 Schema

#### 1\. 資料表：`cue_lists` (排期表 / 委刊單主表)

**用途描述**：
此表為系統的核心資料表，記錄每一筆廣告專案（Campaign/Order）的主要資訊，包含客戶、代理商、預算分配、走期以及審核狀態。每一筆 `cue_lists` 代表一份完整的媒體排期計畫。

| 欄位名稱 (Column) | 資料型態 | 必填 | 預設值 | 說明 (Description) & 備註 |
| :--- | :--- | :--- | :--- | :--- |
| `id` | INT | Y | AUTO | **主鍵 (Primary Key)**<br>排期表唯一識別碼。 |
| `client_id` | INT | Y | - | **直客/廣告主 ID**<br>關聯至 Client 資料表 (Foreign Key)。 |
| `agency_id` | INT | N | NULL | **代理商 ID**<br>關聯至 Agency 資料表。若為直客案則可能為 Null。 |
| `sales_id` | INT | Y | - | **業務負責人 ID**<br>負責此專案的 Sales。 |
| `campaign_name` | VARCHAR | N | NULL | **活動名稱**<br>廣告活動的顯示名稱。 |
| `start_date` | DATE | N | NULL | **走期開始日** |
| `end_date` | DATE | N | NULL | **走期結束日** |
| `status` | VARCHAR | N | NULL | **目前狀態**<br>例如：`active`, `paused`, `archived` 等。 |
| `before_archived_status`| VARCHAR | N | 'draft'| **封存前狀態**<br>記錄被封存或刪除前的最後狀態，預設為草稿。 |
| `is_confidential` | TINYINT(1)| N | 0 | **是否保密**<br>1=保密專案, 0=一般專案。 |
| `serial_number` | INT | N | 0 | **流水號**<br>用於內部行政或對帳的編號。 |
| `main_cue_list_id` | INT | N | NULL | **主排期表 ID**<br>若此單為追加預算或子單，可能關聯回原始主單。 |
| **預算與財務相關** | | | | |
| `total_budget` | INT | N | 0 | **總預算 (Total Budget)** |
| `external_budget` | INT | N | 0 | **外部採購預算**<br>指撥給第三方媒體 (非自家庫存) 的預算。 |
| `material_fee` | INT | N | 0 | **素材製作費** |
| `material_fee_gift` | INT | N | 0 | **素材製作費 (贈送)**<br>不向客戶請款的素材製作成本。 |
| `gross_type` | INT | N | 1 | **毛利類型 (Gross Type)**<br>定義營收認列方式 (例如：Net/Gross 結算)。 |
| `gsp_buy` | TINYINT(1)| N | 1 | **GSP 購買標記**<br>可能指 Guaranteed Service Protocol 或特定購買模式。 |
| `guoran_discount` | INT | N | 0 | **果實/特定折扣金額**<br>(推測 `guoran` 為特定產品線或公司名)。 |
| `onead_gift` | INT | N | 0 | **OneAD 配送/贈送額度**<br>自家媒體贈送的預算值。 |
| `external_gift` | INT | N | 0 | **外部配送/贈送額度** |
| **異動與審核記錄** | | | | |
| `ad_request_version` | INT | N | 1 | **需求版本號**<br>當需求變更時遞增。 |
| `ad_request_date` | DATETIME | N | NULL | **需求提出時間** |
| `main_ad_request_one_campaign_id`| INT | N | NULL | **主 Campaign ID**<br>對應到廣告投遞伺服器 (Ad Server) 上的 Campaign ID。 |
| `budget_update_reason` | TEXT | N | NULL | **預算變更原因** |
| `cancel_reason` | TEXT | N | NULL | **取消原因** |
| `notes` | TEXT | N | NULL | **備註** |
| `created_at` | DATETIME | Y | - | **建立時間** |
| `updated_at` | DATETIME | Y | - | **更新時間** |
| **特殊設定** | | | | |
| `publisher_speed` | TINYINT(1)| N | 0 | **媒體加速投放**<br>是否開啟加速消耗預算模式。 |
| `publisher_speed_media_id`| INT | N | NULL | **加速投放指定媒體 ID** |
| `customer_account_operation`| TINYINT(1)| N | 0 | **客戶自行操作**<br>1=客戶自操 (Self-serve), 0=代操 (Managed)。 |

**索引 (Indices)**：

  * `PK`: `id`
  * `IDX`: `client_id` (依客戶查詢)
  * `IDX`: `agency_id` (依代理商查詢)
  * `IDX`: `sales_id` (依業務查詢)
  * `IDX`: `start_date`, `client_id` (複合索引：用於查詢特定客戶在特定日期的排期)

-----

#### 2\. 名詞解釋 (Glossary)

在此章節定義 Schema 中出現的廣告業專有名詞：

  * **Cue List (排期表/委刊單)**：
    廣告活動的執行合約或計畫表。包含了走期、預算、鎖定條件以及預計購買的版位資訊。

  * **Agency (代理商)**：
    代表廣告主進行媒體採購的廣告公司。在資料庫中，若 `agency_id` 存在，表示此單是透過代理商下單；若為 NULL，通常表示為直客 (Direct Client)。

  * **GSP (Guaranteed Service Protocol / Buy)**：
    *(需確認實際業務定義)* 在此上下文中，通常指「保證型購買」或特定的銷售協議，代表庫存或成效是有被保證的，而非 RTB (競價) 模式。

  * **OneAD Gift (內部配送/贈送)**：
    指媒體方 (OneAD) 額外贈送給客戶的曝光預算或價值，通常不計入向客戶請款的總金額 (`Total Budget`)，但在系統內部需記錄成本或庫存消耗。

  * **External Budget (外部預算)**：
    指該 Cue List 中，預計花費在非自家媒體聯盟（例如：Google Ads, Meta, 或其他第三方 DSP）的採購金額。

  * **Gross Type**：
    財務認列名詞。通常區分報價是包含代理商佣金的「Gross Price」還是實拿的「Net Price」。

  * **Publisher Speed (加速投放)**：
    一種廣告投放策略設定。當開啟時，系統會盡可能快速地消耗預算或爭取曝光 (ASAP mode)，而非平均分配在走期內 (Smooth mode)。

-----

#### 2\. 資料表：`one_campaigns` (廣告活動執行設定)

**用途描述**：
此表對應實際在廣告投遞系統中的 Campaign 層級。它繼承了 `cue_lists` 的部分財務資訊，但更多了投遞控制參數（如：頻率控制、優化目標、優先權、DSP 狀態）。一個 `cue_list` (委刊單) 可能對應一個或多個 `one_campaigns` (例如：分不同波段或不同策略執行)。

| 欄位名稱 (Column) | 資料型態 | 必填 | 預設值 | 說明 (Description) & 備註 |
| :--- | :--- | :--- | :--- | :--- |
| `id` | INT | Y | AUTO | **主鍵** |
| `cue_list_id` | INT | N | NULL | **所屬排期表 ID**<br>Foreign Key，關聯回 `cue_lists`。 |
| `user_id` | INT | N | NULL | **建立/負責使用者**<br>關聯至 Users 表。 |
| `name` | VARCHAR | Y | - | **活動名稱**<br>通常對應 Ad Server 上顯示的 Campaign Name。 |
| `start_date` | DATE | Y | - | **走期開始日** |
| `end_date` | DATE | Y | - | **走期結束日** |
| `closed_date` | DATE | N | NULL | **結案日期**<br>實際關閉活動的日期。 |
| `status` | VARCHAR | Y | 'normal' | **活動狀態**<br>系統內部狀態 (normal, deleted 等)。 |
| `superdsp_status` | VARCHAR | N | 'draft' | **DSP 同步狀態**<br>記錄與 SuperDSP (投遞核心) 的同步狀態 (如：draft, active, syncing)。 |
| `is_approved` | TINYINT(1)| N | 0 | **審核狀態**<br>是否已通過審核可上線。 |
| `is_test` | TINYINT(1)| N | 0 | **測試單標記** |
| **投遞策略與目標** | | | | |
| `objective_id` | INT | N | 1 | **優化目標 ID**<br>例如：1=CPM, 2=CPC, 3=CPV 等目標設定。 |
| `priority` | INT | N | NULL | **投遞優先權**<br>決定廣告搶量的優先順序 (1-10 或更高)。 |
| `freq` | INT | N | NULL | **頻率控制 (Frequency Cap)**<br>限制單一使用者看到的次數 (例如：3次/天)。 |
| `daily_ad_req_cap` | INT | N | NULL | **每日請求上限**<br>限制每日最大的 Ad Request 數量。 |
| `is_programmatic` | TINYINT(1)| N | 1 | **程式化購買**<br>標記是否走 Programmatic 渠道。 |
| `programmatic_demand_id`| INT | N | NULL | **程式化需求方 ID**<br>若對接外部 Demand Source，記錄其 ID。 |
| `publisher_speed` | TINYINT(1)| N | 0 | **加速投放模式**<br>繼承或覆寫 cue\_lists 的設定。 |
| `category_id` | INT | N | NULL | **產業類別 (主)** |
| `sub_category_id` | INT | N | NULL | **產業類別 (子)** |
| `one_category_id` | INT | N | NULL | **OneAD 分類 ID**<br>關聯至 `one_categories` 表。 |
| `product_category_id` | INT | N | NULL | **產品類別 ID** |
| **財務與幣別** | | | | |
| `budget` | INT | Y | 0 | **執行預算**<br>此 Campaign 分配到的預算。 |
| `currency` | INT | N | 2 | **幣別 ID**<br>例如：1=USD, 2=TWD (推測)。 |
| `exchange_rate` | DECIMAL | N | 30.0 | **匯率**<br>鎖定該 Campaign 的匯率基準。 |
| `gsp_buy` | INT | N | 1 | **GSP 購買類型**<br>這裡用 INT，可能比 cue\_lists 的 tinyint 有更多狀態。 |
| `guoran_discount` | FLOAT | N | 0 | **折扣率/金額** |
| **多型關聯 (Polymorphic)**| | | | |
| `one_campaign_advertiser_type`| VARCHAR| N | NULL | **廣告主類型**<br>例如："Client", "Agency" (用於多型關聯)。 |
| `one_campaign_advertiser_id` | INT | N | NULL | **廣告主 ID** |
| `one_campaign_entity_type` | VARCHAR | N | NULL | **實體類型**<br>擁有此 Campaign 的實體類型。 |
| `one_campaign_entity_id` | INT | N | NULL | **實體 ID** |
| **報表與其他** | | | | |
| `report_denominator` | VARCHAR | N | 'impression\_count' | **報表分母基準**<br>計算 CTR/VTR 時的分母 (如：impression\_count vs request\_count)。 |
| `voucher_num` | VARCHAR | N | NULL | **憑證/優惠券號碼** |
| `insertion_order_id` | INT | N | NULL | **IO 單號 ID**<br>對應外部或傳統系統的 IO ID。 |
| `updated_at` | DATETIME | N | NULL | **更新時間** |

**索引 (Indices)**：

  * `PK`: `id`
  * `FK`: `cue_list_id` -\> `cue_lists`
  * `FK`: `user_id` -\> `users`
  * `FK`: `one_category_id` -\> `one_categories`
  * `IDX`: `objective_id` (依優化目標查詢)
  * `IDX`: `voucher_num`
  * `IDX`: `currency`
  * `IDX`: `end_date` (查詢即將結束或執行中的活動)
  * `Composite Index`: 廣告主多型索引 (`advertiser_type`, `advertiser_id`)、實體多型索引 (`entity_type`, `entity_id`)

-----

#### 2.1 新增名詞解釋 (Glossary Update)

在此章節補充 `one_campaigns` 出現的新名詞：

  * **One Campaign (執行活動)**：
    相較於 `Cue List` 是財務與合約層面的「訂單」，`One Campaign` 是技術與執行層面的「活動」。它包含了實際投放給受眾的設定參數（如：頻率、優先權、分類）。

  * **Objective (優化目標)**：
    指該次廣告活動的主要 KPI 目標。常見的 ID 對應可能為：CPM (每千次曝光成本)、CPC (每次點擊成本)、CPV (每次觀看成本) 等。系統會根據此目標進行演算法優化。

  * **Frequency Cap (頻率控制 / Freq)**：
    限制同一位使用者（Unique User/Device）在特定時間內看到該廣告的次數上限，避免過度曝光造成使用者反感。

  * **Polymorphic Association (多型關聯)**：
    資料庫設計模式的一種。透過 `_type` 和 `_id` 兩個欄位，讓 Campaign 可以動態歸屬於不同的資料表（例如：有時候直接歸屬於 `Clients`，有時候歸屬於 `Agencies` 或其他實體），而不需要為每個關聯建立獨立的欄位。

  * **SuperDSP Status**：
    紀錄此活動在 DSP (Demand-Side Platform) 端的同步狀態。當在本地資料庫建立活動後，通常需要經過 API 推送到 DSP 進行實際投放，此欄位用於追蹤該推送流程（草稿 -\> 同步中 -\> 已上線）。

  * **Programmatic (程式化購買)**：
    指透過自動化系統（如 RTB 實時競價）進行媒體版位採購的模式，而非傳統的人工排期購買。

  * **Insertion Order (IO)**：
    傳統廣告業術語，即「委刊單」。在本系統中可能作為與舊系統或外部系統對接的單號 (`insertion_order_id`)。

-----

#### 3\. 資料表：`pre_campaign` (媒體企劃 / 預定明細)

**用途描述**：
此表位於 `one_campaigns` 之下或與其平行，通常用於「媒體企劃 (Planning)」階段或作為「執行明細 (Line Item)」。
它詳細記錄了針對特定媒體、裝置或受眾的購買條件、預估成效（如 Reach, TRPs）以及技術設定（如黑白名單、地區鎖定）。此表資料量較大，涵蓋了從預售試算到實際執行的細部參數。

| 欄位名稱 (Column) | 資料型態 | 必填 | 預設值 | 說明 (Description) & 備註 |
| :--- | :--- | :--- | :--- | :--- |
| `id` | INT | Y | AUTO | **主鍵** |
| `one_campaign_id` | INT | N | NULL | **所屬活動 ID**<br>Foreign Key，關聯回 `one_campaigns`。 |
| `mediaid` | VARCHAR | N | NULL | **媒體 ID / 版位 ID**<br>指定投放的媒體或版位代碼。 |
| `medianame` | VARCHAR | N | NULL | **媒體名稱** |
| `start_date` | VARCHAR | N | NULL | **開始日期** (這裡用 String 存，可能包含非標準日期格式) |
| `end_date` | VARCHAR | N | NULL | **結束日期** |
| `status` | VARCHAR | N | NULL | **狀態**<br>如：booked, pending, closed, trash 等。 |
| `booked` | TINYINT | N | 0 | **是否已預定** |
| `campaign_type` | INT | N | 1 | **活動類型** |
| `type` | VARCHAR | N | NULL | **類型標記**<br>可能區分 Video, Banner 或其他形式。 |
| **預算與成效指標 (KPIs)**| | | | |
| `budget` | INT | N | 0 | **預算** |
| `onead_gift` | INT | N | 0 | **贈送預算** |
| `uniprice` | DECIMAL | N | NULL | **單價**<br>CPM/CPC/CPV 單價。 |
| `play_times` | INT | N | 0 | **預估播放次數/曝光數** |
| `ta_universe` | INT | N | 0 | **TA 母體數**<br>目標受眾的總人口數。 |
| `ta_one_plus_reach` | INT | N | 0 | **1+ Reach (到達人數)**<br>接觸過至少 1 次的 TA 人數。 |
| `ta_three_plus_reach`| INT | N | 0 | **3+ Reach**<br>接觸過至少 3 次的 TA 人數。 |
| `tarps` | DECIMAL | N | 0.000 | **TA GRPs/TRPs**<br>總收視點/總曝光點數。 |
| `avg_freq` | DECIMAL | N | 0.000 | **平均頻率** |
| `ta_ratio` | DECIMAL | N | 0.000 | **TA 濃度 (Composition)** |
| `cprp` | TINYINT | N | 0 | **CPRP 購買模式**<br>Cost Per Rating Point (每收視點成本)。 |
| **行動端專屬指標** | | | | |
| `mobile_ta_one_plus_reach`| INT | N | 0 | **Mobile 1+ Reach** |
| `mobile_tarps` | DECIMAL | N | 0.000 | **Mobile TRPs** |
| `device_distribution`| DECIMAL | N | 0.5 | **裝置配比**<br>例如 PC vs Mobile 的預算或流量分配。 |
| **投遞技術設定 (Targeting)**| | | | |
| `superdsp_pack_id` | INT | N | NULL | **DSP 包版 ID**<br>對應 DSP 的 Package 設定。 |
| `inventory_types` | TEXT | N | NULL | **庫存類型**<br>例如：App, Web, Video 等。 |
| `blacklist_urls` | TEXT | N | NULL | **網址黑名單** |
| `whitelist_urls` | TEXT | N | NULL | **網址白名單** |
| `superdsp_regions` | TEXT | N | NULL | **鎖定區域** |
| `superdsp_cities` | TEXT | N | NULL | **鎖定城市** |
| `weather_conditions` | VARCHAR | N | NULL | **天氣鎖定**<br>根據天氣觸發廣告 (例如：下雨天才投)。 |
| `target_devices` | TEXT | N | NULL | **鎖定裝置** |
| `isp_include` | TINYINT | N | NULL | **ISP 鎖定**<br>包含/排除特定電信商。 |
| `priority` | INT | N | 10 | **優先權** |
| `freq` | INT | N | NULL | **頻率控制** |
| `deliver_strategy` | INT | N | 0 | **投放策略**<br>例如：平均投放、前快後慢等。 |
| `pacing_status` | TINYINT | N | 0 | **配速控制狀態** |
| `cct_enable` | TINYINT | N | 1 | **CCT 開啟**<br>(可能指 Click/Conversion Control Technology 或特定優化開關)。 |
| **流程管理** | | | | |
| `sales_id` | INT | N | NULL | **負責業務** |
| `creator_id` | INT | N | NULL | **建立者** |
| `editor_id` | INT | N | NULL | **最後編輯者** |
| `booked_at` | DATETIME | N | NULL | **預定時間** |
| `closed` | DATETIME | N | NULL | **結案時間** |
| `is_finished_account_receivable`| TINYINT| N | 0 | **AR (應收帳款) 完成**<br>財務流程標記。 |
| `merge_to_pre_campaign_id`| INT | N | NULL | **合併至 ID**<br>若此單被合併，指向新的主單 ID。 |

**索引 (Indices)**：

  * `PK`: `id`
  * `IDX`: `mediaid`
  * `FK`: `one_campaign_id` -\> `one_campaigns`
  * `IDX`: `campaign_type`, `status` (常用過濾條件)
  * `IDX`: `ad_request_comment_id`
  * `IDX`: `merge_to_pre_campaign_id` (追蹤合併關係)

-----

#### 3.1 新增名詞解釋 (Glossary Update)

在此章節補充 `pre_campaign` 出現的媒體企劃與技術名詞：

  * **Pre-Campaign (前測/企劃單)**：
    相對於 `One Campaign` 是正式執行的「活動」，`Pre-Campaign` 通常指在規劃階段的「試算單」或「媒體預定單」。它可以詳細計算不同媒體組合下的預估成效 (Reach, TRP)，確認無誤後再轉為正式投放設定。在此系統中，它也可能直接作為執行時的細項設定 (Line Item)。

  * **TRPs (Target Rating Points / 目標收視點)**：
    廣告總收視點。計算公式為：`Reach% (到達率) * Frequency (平均頻率)`。這是傳統電視廣告常用的指標，但在數位影音廣告中也被用來衡量對特定目標受眾 (TA) 的總曝光強度。

  * **TA (Target Audience / 目標受眾)**：
    廣告活動意圖觸及的特定人群（例如：25-44歲女性）。

      * `ta_universe`: 該族群的總人口數。
      * `ta_ratio`: 投放媒體中該族群的佔比（濃度）。

  * **Reach (到達率/人數)**：

      * `1+ Reach`: 在走期內，至少看過廣告一次的不重複人數。
      * `3+ Reach`: 在走期內，至少看過廣告三次的不重複人數（通常視為有效溝通的門檻）。

  * **Pacing (配速)**：
    控制廣告預算或曝光在走期內消耗速度的機制。確保廣告不會在第一天就跑完，也不會到最後一天還有大量預算沒花完。

  * **Blacklist / Whitelist (黑/白名單)**：

      * `blacklist_urls`: 禁止廣告投遞的網址或網域（品牌安全保護）。
      * `whitelist_urls`: 僅允許廣告投遞的指定網址或網域（包版或指定購買）。

  * **Weather Targeting (天氣鎖定)**：
    一種情境式行銷技術。系統串接氣象 API，根據當地即時天氣（如：氣溫、降雨機率）決定是否投遞廣告。例如：下雨時投遞雨具或外送廣告。

  * **CCT (Click/Conversion Optimization)**：
    *(推測)* 可能指 Click-Through Control 或類似技術，用於優化點擊率或確保點擊品質的演算法開關。

-----

### 技術文件：廣告系統資料庫 Schema (續)

#### 4\. 資料表：`pre_campaign_detail` (投放執行明細 / 版位設定)

**用途描述**：
此表為媒體計畫的最底層執行單位。它定義了具體的廣告版位 (Placement)、廣告形式 (Ad Format)、以及針對該版位的技術規格與成效指標（如：保證的點擊率 CTR 或完整觀看率 VTR）。
一筆 `pre_campaign` (媒體計畫) 可以包含多筆 `pre_campaign_detail` (例如：同時購買 PC 版位與 Mobile 版位，或不同尺寸的素材)。

| 欄位名稱 (Column) | 資料型態 | 必填 | 預設值 | 說明 (Description) & 備註 |
| :--- | :--- | :--- | :--- | :--- |
| `id` | INT | Y | AUTO | **主鍵** |
| `pre_campaign_id` | INT | N | NULL | **所屬媒體計畫 ID**<br>Foreign Key，關聯回 `pre_campaign`。 |
| `one_campaign_id` | INT | N | NULL | **所屬活動 ID**<br>資料正規化冗餘欄位，方便快速查詢。 |
| `media_id` | INT | N | NULL | **媒體 ID**<br>系統內部的媒體編號。 |
| `mediaid` | VARCHAR | N | NULL | **媒體代碼 (String)** |
| `uid` | VARCHAR | Y | - | **單元 ID (Unit ID)**<br>廣告版位單元識別碼。 |
| `pid` | VARCHAR | Y | - | **版位 ID (Placement/Position ID)**<br>對接 Ad Server 或 Publisher 的具體版位代碼。 |
| `pid_name` | VARCHAR | N | NULL | **版位名稱** |
| `start_date` | VARCHAR | N | NULL | **開始日期** |
| `end_date` | VARCHAR | N | NULL | **結束日期** |
| `enable` | TINYINT | N | 1 | **啟用狀態** |
| **廣告形式與規格** | | | | |
| `ad_type` | VARCHAR | N | NULL | **廣告類型**<br>字串代碼，如 'video', 'banner'。 |
| `sub_ad_type_id` | INT | N | NULL | **子廣告類型 ID** |
| `ad_format_type_id` | INT | N | NULL | **廣告形式 ID**<br>定義具體展現形式 (如：In-Read, Banner, Overlay)。 |
| `flv_second` | INT | N | 0 | **影片秒數** |
| `banner_size` | INT | N | 0 | **Banner 尺寸**<br>可能對應特定尺寸 ID 或面積。 |
| `video_id` | INT | N | NULL | **影片素材 ID**<br>關聯至 Video 素材表。 |
| `addon_id` | INT | N | NULL | **互動模組 ID**<br>使用的特殊互動功能或外掛。 |
| `bypass_second` | INT | N | NULL | **略過秒數**<br>幾秒後可略過廣告。 |
| **計價與成效設定** | | | | |
| `pricing_model_id` | INT | N | NULL | **計價模式 ID**<br>關聯 `pricing_models` (如 CPM, CPV, CPC)。 |
| `uniprice` | DECIMAL | N | 0.000 | **單價 (Unit Price)** |
| `onead_price` | INT | N | NULL | **OneAD 內部成本/底價** |
| `budget` | INT | N | NULL | **分配預算** |
| `play_times` | BIGINT | N | 0 | **目標播放數** (Video 適用) |
| `impression` | INT | N | 0 | **目標曝光數** (Display 適用) |
| `impression_uniprice`| DECIMAL | N | 0.000 | **曝光單價** |
| `cpv_complete` | INT | N | 0 | **CPV 完成定義**<br>定義 CPV 計價的觸發點。 |
| `same_budget_pool_symbol`| VARCHAR| N | NULL | **共用預算池代號**<br>擁有一樣 Symbol 的 Detail 共享同一筆預算上限。 |
| **優化指標 (KPIs)** | | | | |
| `click_rate` | DECIMAL | N | 0.0000 | **預估/目標 CTR** |
| `min_click_rate` | FLOAT | N | 0 | **保證最低 CTR** |
| `max_click_rate` | FLOAT | N | 0 | **最高 CTR 限制** |
| `completion_rate` | DECIMAL | N | 0.0000 | **預估/目標 VTR (完整觀看率)** |
| `min_completion_rate` | FLOAT | N | 0 | **保證最低 VTR** |
| `max_completion_rate` | FLOAT | N | 0 | **最高 VTR 限制** |
| `monitor` | TINYINT | N | 0 | **第三方監測**<br>是否埋設第三方 Tracking code。 |
| **其他屬性** | | | | |
| `pack_id` | INT | N | NULL | **打包販售 ID (Package)**<br>若此版位屬於某個 Package。 |
| `pack_source` | VARCHAR | N | NULL | **Package 來源** |
| `location` | VARCHAR | Y | 'tw' | **投放地區** |
| `category_id` | INT | N | NULL | **分類 ID** |
| `product_info_id` | INT | N | NULL | **產品資訊 ID** |
| `daily_freq_cap` | DECIMAL | N | 0 | **每日頻率上限** |
| `notice_by_mail` | INT | N | 0 | **郵件通知設定**<br>可能指走期快結束或預算快用完的通知閾值。 |

**索引 (Indices)**：

  * `PK`: `id`
  * `FK`: `pricing_model_id` -\> `pricing_models`
  * `IDX`: `media_id`
  * `IDX`: `video_id`
  * `IDX`: `pid` (重要：查詢特定版位效能)
  * `IDX`: `pack_id`
  * `IDX`: `sub_ad_type_id`, `ad_format_type_id` (查詢特定形式廣告)
  * `Composite`: `pre_campaign_id`, `ad_type` (查詢某計畫下的特定類型廣告)
  * `Composite`: `media_id`, `start_date`, `end_date` (查詢媒體檔期衝突)

-----

#### 4.1 新增名詞解釋 (Glossary Update)

在此章節補充 `pre_campaign_detail` 出現的執行與技術名詞：

  * **PID (Placement ID / Position ID)**：
    版位識別碼。在數位廣告中，代表網頁或 APP 上的一個具體廣告區塊。這是對接 Ad Server 時最重要的參數，決定廣告會出現在哪裡。

  * **Pricing Model (計價模式)**：
    定義廣告費用的計算方式。

      * `CPM`: Cost Per Mille (每千次曝光成本)。
      * `CPC`: Cost Per Click (每次點擊成本)。
      * `CPV`: Cost Per View (每次觀看成本，通常用於影音)。

  * **VTR (View-Through Rate / Completion Rate)**：
    完整觀看率。計算公式為 `完整觀看次數 / 廣告開始播放次數`。這是衡量影音廣告內容吸引力與受眾品質的關鍵指標。

      * `min_completion_rate`: 部分專案會向客戶「保證」最低觀看率，若未達標可能需補量。

  * **Budget Pool (預算池 / Same Budget Pool Symbol)**：
    一種彈性的預算控制機制。當多個 Detail (例如：PC 版位與 Mobile 版位) 擁有一樣的 `same_budget_pool_symbol` 時，它們會共用同一筆總預算，系統會根據成效自動將預算分配給表現較好的版位，而不需硬性規定各版位的預算上限。

  * **Package / Pack (打包販售)**：
    將多個不同媒體或版位的流量打包成一個商品進行販售（例如：「女性時尚包」可能包含多個美妝網站的版位）。

  * **Bypass Second (略過秒數)**：
    常見於影音廣告（如 YouTube TrueView），指廣告播放幾秒後，使用者可以點擊「略過廣告」按鈕。

-----

### 技術文件：廣告系統資料庫 Schema (續)

#### 5\. 資料表：`target_segments` (受眾標籤 / 目標客群定義)

**用途描述**：
此表位於數據管理層 (DMP/CDP)，用於定義與管理「目標受眾 (Target Audience)」。
它記錄了如何篩選使用者的規則（例如：造訪過某網站、特定性別），以及該受眾包的目前規模 (`oneid_qty`) 和生命週期設定。這些 Segment 會被 `pre_campaign` 或 `one_campaigns` 引用，作為投放鎖定的依據。

| 欄位名稱 (Column) | 資料型態 | 必填 | 預設值 | 說明 (Description) & 備註 |
| :--- | :--- | :--- | :--- | :--- |
| `id` | INT | Y | AUTO | **主鍵** |
| `segment_id` | VARCHAR(36)| Y | - | **受眾 UUID**<br>系統全域唯一的受眾識別碼 (通常為 UUID 格式)。 |
| `name` | VARCHAR | N | NULL | **受眾名稱** (中文) |
| `en_name` | VARCHAR | N | NULL | **受眾名稱** (英文) |
| `description` | TEXT | Y | - | **受眾描述**<br>詳細說明此受眾的定義或用途。 |
| `client_id` | INT | N | NULL | **專屬客戶 ID**<br>若有值，表示此受眾為該客戶專用 (First-party data)。 |
| `third_party_company_id`| INT | N | NULL | **第三方數據商 ID**<br>若資料來自外部數據商 (3rd party data)。 |
| `segment_category_id` | INT | N | 0 | **標籤分類 ID**<br>關聯至分類表 (例如：興趣、人口統計、購買意圖)。 |
| **受眾規模與狀態** | | | | |
| `oneid_qty` | INT | N | 0 | **OneID 數量 (受眾規模)**<br>符合此標籤的不重複使用者 ID 總數。 |
| `targeting_status` | TINYINT | Y | 0 | **可投放狀態**<br>是否已準備好供廣告系統鎖定。 |
| `is_urgent` | TINYINT | N | 0 | **緊急運算**<br>標記是否需優先計算此受眾包。 |
| `system` | VARCHAR | N | 'ODM' | **所屬系統**<br>來源系統標記 (如 ODM, DSP 等)。 |
| `qp_enable` | TINYINT | N | 0 | **QP 啟用**<br>(可能指 Query Platform 或快速查詢功能的開關)。 |
| **定義規則 (Rule Definition)**| | | | |
| `data_source` | VARCHAR | N | NULL | **數據來源類型**<br>例如：'URL', 'AppInstalled', 'Keyword'。 |
| `data_value` | TEXT | N | NULL | **數據值**<br>比對的關鍵字或網址。 |
| `operator` | TEXT | N | NULL | **運算邏輯**<br>例如：'contains', 'equals', 'starts\_with'。 |
| `operator_value` | TEXT | N | NULL | **運算數值** |
| `data_source_para` | INT | N | 180 | **回溯天數 (Lookback Window)**<br>定義追溯過去幾天的行為數據 (預設 180 天)。 |
| `user_ids` | TEXT | N | NULL | **使用者 ID 列表**<br>直接存儲的 ID 清單 (通常用於小規模或自訂名單)。 |
| **更新與生命週期** | | | | |
| `continuous_updating` | TINYINT | Y | 0 | **持續更新**<br>是否每日動態更新受眾名單。 |
| `permanent_updating` | TINYINT | N | 0 | **永久更新** |
| `start_date` | DATE | N | NULL | **開始生效日** |
| `end_date` | DATE | N | NULL | **結束生效日** |
| `stop_updating_date` | DATE | N | NULL | **停止更新日**<br>過了此日期後，名單不再變動。 |
| `created_at` | DATETIME | Y | - | **建立時間** |
| `updated_at` | DATETIME | Y | - | **更新時間** |
| `creator` | VARCHAR | N | NULL | **建立者名稱** |
| `comment` | TEXT | N | NULL | **內部備註** |

**索引 (Indices)**：

  * `PK`: `id`
  * `IDX`: `client_id` (快速篩選特定客戶的受眾包)

-----

#### 5.1 新增名詞解釋 (Glossary Update)

在此章節補充 `target_segments` 出現的數據與受眾技術名詞：

  * **Target Segment (受眾標籤/受眾包)**：
    將具有相同特徵（如：都看過汽車網站、都是 25-35 歲女性）的使用者歸類為一個群組。廣告投放時可直接指定此 Segment ID 進行精準打擊。

  * **OneID (統一使用者識別碼)**：
    系統內部的 Unique User ID。由於跨瀏覽器、跨裝置追蹤困難，系統通常會將各種 Cookie ID (如 GAID, IDFA, Web Cookie) 整合歸戶為一個 `OneID`，以此計算真實的受眾規模 (`oneid_qty`)。

  * **Lookback Window (回溯期 / Data Source Parameter)**：
    指系統在撈取數據時，往回追溯的時間範圍。

      * 例如 `data_source_para = 30`，代表只收集「過去 30 天內」有特定行為的使用者。時間太長可能導致興趣不準，太短則受眾規模太小。

  * **ODM (OneAD Data Management)**：
    *(推測)* 內部開發的數據管理平台名稱，負責運算與維護這些受眾標籤。

  * **Continuous Updating (動態/持續更新)**：
    受眾包的一種維護模式。

      * **開啟 (Dynamic)**：每天系統會自動把新符合條件的人加入，把過期的人踢除（滾動式）。
      * **關閉 (Static)**：通常指一次性的名單（如：上傳一包會員 Email），名單固定不變，除非人工重新上傳。

  * **Rule-based Segmentation (規則定義)**：
    透過 `data_source` (來源)、`operator` (運算子)、`data_value` (值) 組成的邏輯來圈選受眾。

      * 範例：`Source: URL` + `Operator: Contains` + `Value: /finance/stock` = 「對股票感興趣的受眾」。

收到，這份檔案非常關鍵！它釐清了系統中最複雜的兩個部分：「預算層級邏輯」與「狀態流轉」。

我將根據這份檔案的內容，為您更新技術文件。這次的更新重點在於：

1.  **補完狀態列舉 (Enums)**：明確定義 `cue_lists` 與 `pre_campaign` 的所有狀態意義。
2.  **新增「預算結構專題」**：因為系統中出現多個 `budget` 欄位，需專門章節解釋 L1\~L4 的資金流向。
3.  **補充廣告事件與術語**：加入檔案中提到的 Event 流程與 ODM 定義。

以下是更新後的技術文件內容：

-----
#### 6\. 核心狀態列舉 (Status Enum Definitions)

根據系統實際數據分佈，定義主要資料表的狀態流轉意義。

**6.1 `cue_lists` (合約/委刊單) 狀態表**
此欄位 (`status`) 代表合約的商業簽署狀態。

| 狀態代碼 (Key) | 說明 (Description) | 業務意義 |
| :--- | :--- | :--- |
| `draft` | **草稿** | 業務正在填寫，尚未送出，不會產生任何執行單。 |
| `requested` | **審核中** | 已送出需求，等待主管或 AM 確認。 |
| `converted` | **已轉單/生效** | 審核通過，正式轉為執行單。這是最主要的活躍狀態 (Active)。 |
| `cancelled` | **取消** | 客戶撤單或未成案。 |
| `archived` | **已封存** | 歷史久遠的舊合約，已歸檔不參與日常運算。 |

**6.2 `pre_campaign` (執行單/投放設定) 狀態表**
此欄位 (`status`) 代表廣告在系統中的實際執行生命週期。

| 狀態代碼 (Key) | 說明 (Description) | 系統行為 |
| :--- | :--- | :--- |
| `draft` | **草稿** | 參數設定中，尚未進入排程。 |
| `requested` | **送審中** | 等待 Ad Ops (營運人員) 確認設定無誤。 |
| `pending` | **等待執行** | 審核已過，但尚未到達 `start_date`，或因素材未齊全而暫停。 |
| `booked` | **已預定** | 資源已鎖定，準備開始投放。 |
| `oncue` | **投放中 (Active)** | 廣告正在線上跑 (Live)，系統會主動發送 Ad Request。 |
| `closed` | **已結案** | 走期結束或預算執行完畢，系統自動關閉。 |
| `aborted` | **中止** | 執行中途被強制停止 (例如：客戶緊急喊卡、素材違規)。 |
| `trash` | **垃圾桶** | 已刪除的無效單。 |

-----

#### 7\. 預算層級架構 (Budget Hierarchy & Logic)

本系統的預算設計分為四個層級 (L1 - L4)，各層級的 `budget` 欄位意義不同，不可混淆。

| 層級 | 資料表 | 預算欄位 | 角色定位 | 定義與用途 |
| :--- | :--- | :--- | :--- | :--- |
| **L1** | `cue_lists` | `total_budget` | **金主 (Accounts Receivable)** | **合約總金額**。<br>代表對客戶的應收帳款，財務認列營收的依據。包含外購成本與自有媒體營收。 |
| **L2** | `one_campaigns` | `budget` | **指揮官 (Allocation)** | **波段分配款**。<br>將總合約金額按時間或策略拆解 (例如：第一波打品牌、第二波打轉換)。通常 `L2 <= L1`。 |
| **L3** | `pre_campaign` | `budget` | **錢包 (System Wallet/Cap)** | **系統執行上限**。<br>這是 Ad Server 實際讀取的扣款上限。不管資金來源為何 (贈送、外購)，流到這裡都視為「可消耗點數」。<br>**注意**：此數值可能已扣除公司利潤 (Margin)，僅代表媒體成本。 |
| **L4** | `pre_campaign_detail` | `budget` | **士兵 (Sub-limit)** | **虛擬限額**。<br>針對特定素材或版位的限制。若設定 `same_budget_pool_symbol`，則多個 Detail 共用 L3 的錢包，此處預算僅為參考上限 (虛胖)，不可直接加總。 |

-----

#### 8\. 名詞解釋補充 (Glossary Update - Advanced)

根據系統架構文檔補充之進階術語：

**Event Tracking (事件追蹤流程)**
當使用者進入媒體時，系統觸發的順序如下：

1.  **`adsrv`**: Ad Server 收到請求，搜尋適合廣告。
2.  **`cv` (Candidate View)**: 決定要顯示哪一支廣告。
3.  **`impression`**: 廣告正式渲染顯示。
4.  **`view`**: 觀看秒數追蹤 (`view2s`, `view3s`, `view5s`, `view10s`, `view30s`)。
5.  **`Click`**: 點擊行為 (區分 `bannerClick`, `videoClick`)。
6.  **`7000`**: 到達廣告主網站 (Landing Page) 後的特定行為代碼。

**Ad Tech Terms**

  * **ODM (Original Design Manufacturer)**：在此系統中指「原廠委託設計代工」模式，即 OneAD 負責技術與數據 (OneID)，但貼上客戶或媒體的品牌進行銷售與服務。
  * **SuperDSP**：系統對接的外部或進階 DSP (Demand-Side Platform) 模組，用於擴充流量採購。
  * **Campaign Target PIDs (Bridge Table)**：
    連接 `pre_campaign` (執行單) 與 `target_segments` (受眾) 的橋樑表。
      * **Source**: 發起端 (通常是 `PreCampaign`)。
      * **Selection**: 被選中的受眾 (通常是 `TargetSegment`)。
      * **Logic**: 決定是「包含 (Include)」還是「排除 (Exclude)」，以及是否開啟「重定向 (Retargeting)」。

這部分非常重要！這三張表 (`cue_list_product_lines`, `cue_list_ad_formats`, `cue_list_budgets`) 補齊了系統中「合約規劃」與「業務報價」的拼圖。

這讓我們能清楚看到一個合約是如何從「選產品」到「定規格」，最後「承諾績效與價格」的。這就是稍早文件提到的 **Level 1.5** 層級。

以下是為您更新的技術文件第六部分：

-----

#### 9\. 合約規劃層級 (Planning & Contract Layer)

此區塊位於 `cue_lists` (合約主表) 之下，`one_campaigns` (執行策略) 之上。
主要用途為記錄業務 (Sales) 與客戶簽訂的詳細購買內容、規格以及承諾的 KPI 區間。此層級資料通常較為靜態，代表「合約條款」。

**層級結構示意：**

> `cue_lists` (總單)
> └── `cue_list_product_lines` (買什麼產品線？)
> ⠀⠀└── `cue_list_ad_formats` (什麼規格/秒數？)
> ⠀⠀⠀⠀└── `cue_list_budgets` (多少錢？保證多少 CTR？)

-----

#### 9.1 資料表：`cue_list_product_lines` (產品線選購)

**用途描述**：
合約的第一層子項目。定義客戶購買了哪些大類的產品線（例如：In-Stream Video, Out-Stream, Display）。

| 欄位名稱 (Column) | 資料型態 | 必填 | 說明 (Description) & 備註 |
| :--- | :--- | :--- | :--- |
| `id` | INT | Y | **主鍵** |
| `cue_list_id` | INT | N | **所屬合約 ID**<br>Foreign Key，關聯至 `cue_lists`。 |
| `cue_product_line_id` | INT | N | **產品線 ID**<br>定義產品大類 (如：Mobile Video, Desktop Banner)。 |
| `purchase_way_id` | INT | N | **購買方式 ID**<br>定義採購模式。例如：1=保證庫存 (Reserved), 2=競價 (Bidding), 3=包版 (Sponsorship)。 |
| `created_at` | DATETIME | Y | **建立時間** |
| `updated_at` | DATETIME | Y | **更新時間** |

**索引 (Indices)**：

  * `FK`: `cue_list_id` -\> `cue_lists`
  * `FK`: `purchase_way_id` -\> `purchase_ways`
  * `FK`: `cue_product_line_id` -\> `cue_product_lines`

-----

#### 9.2 資料表：`cue_list_ad_formats` (廣告規格設定)

**用途描述**：
合約的第二層子項目。針對選定的產品線，定義具體的技術規格與物理屬性（如：秒數、平台、格式）。

| 欄位名稱 (Column) | 資料型態 | 必填 | 說明 (Description) & 備註 |
| :--- | :--- | :--- | :--- |
| `id` | INT | Y | **主鍵** |
| `cue_list_product_line_id`| INT | N | **所屬產品線 ID**<br>Foreign Key。 |
| `ad_format_type_id` | INT | N | **內部廣告格式 ID**<br>定義展現形式 (如：In-Read, Overlay)。 |
| `external_ad_format_id` | INT | N | **外部/DSP 廣告格式 ID**<br>若為外購流量，對應外部系統的格式 ID。 |
| `video_seconds_option_id` | INT | N | **影片秒數選項 ID**<br>限制影片長度 (如：6s, 15s, 30s)，通常影響定價。 |
| `media_id` | INT | N | **指定媒體 ID**<br>若此規格需綁定特定媒體 (如：Yahoo 首頁)。 |
| `ad_platform` | INT | N | **投放平台**<br>例如：1=PC Web, 2=Mobile Web, 3=App。 |
| `freq` | INT | N | **頻率控制 (合約層)**<br>合約載明的頻次限制 (Frequency Cap)。 |

**索引 (Indices)**：

  * `FK`: `cue_list_product_line_id`
  * `FK`: `ad_format_type_id` -\> `ad_format_types`
  * `FK`: `video_seconds_option_id` -\> `video_seconds_options`
  * `FK`: `external_ad_format_id` -\> `external_ad_formats`

-----

#### 9.3 資料表：`cue_list_budgets` (報價與 KPI 承諾)

**用途描述**：
合約的第三層，也是最關鍵的**報價單 (Quotation Line Item)**。
它記錄了該規格下的預算金額、單價，以及對客戶承諾的**績效保證範圍 (SLA)**。業務在系統輸入這些數據後，後續的執行端 (`pre_campaign`) 需以此為目標進行優化。

| 欄位名稱 (Column) | 資料型態 | 必填 | 說明 (Description) & 備註 |
| :--- | :--- | :--- | :--- |
| `id` | INT | Y | **主鍵** |
| `cue_list_ad_format_id` | INT | N | **所屬規格 ID**<br>Foreign Key。 |
| `pricing_model_id` | INT | N | **計價模式 ID**<br>對應 `pricing_models` (CPM/CPC/CPV)。 |
| **財務資訊** | | | |
| `budget` | INT | N | **項目預算**<br>此單項產品的銷售金額。 |
| `budget_gift` | INT | N | **贈送預算** |
| `uniprice` | DECIMAL | N | **銷售單價** |
| `estimated_gross_margin` | FLOAT | N | **預估毛利**<br>業務端計算利潤用。 |
| `service_fee_pct` | DECIMAL | N | **服務費比例 (%)** |
| **走期與排程** | | | |
| `schedule_dates` | TEXT | N | **預定走期**<br>詳細的日期區間字串。 |
| `material_delivery` | DATE | N | **素材繳交期限** |
| **KPI 績效保證 (SLA)** | | | |
| `ctr_lb` / `ctr_ub` | FLOAT | N | **CTR (點擊率) 下限/上限**<br>Guarantee CTR Lower/Upper Bound。 |
| `vtr_lb` / `vtr_ub` | FLOAT | N | **VTR (觀看率) 下限/上限**<br>影音廣告的完看率保證。 |
| `cvr_lb` / `cvr_ub` | FLOAT | N | **CVR (轉換率) 下限/上限** |
| `er_lb` / `er_ub` | FLOAT | N | **ER (互動率) 下限/上限**<br>Engagement Rate。 |
| `aer_lb` / `aer_ub` | FLOAT | N | **AER (廣告互動率?) 下限/上限**<br>Ad Engagement Rate? (需確認定義)。 |
| `counting` | INT | N | **保證量 (總數)**<br>例如：保證 100萬 次曝光。 |
| `ad_counting` | INT | N | **廣告量?** |
| **其他** | | | |
| `product_category_id` | INT | N | **產品類別** |
| `custom_content` | VARCHAR | N | **自訂內容** |
| `device` | INT | N | **裝置** |

**索引 (Indices)**：

  * `FK`: `cue_list_ad_format_id`
  * `FK`: `pricing_model_id` -\> `pricing_models`

-----

#### 9.4 新增名詞解釋 (Glossary Update - Planning)

在此章節補充合約規劃層的名詞：

  * **Purchase Way (購買方式)**：
    決定流量的採購性質。

      * **Reserved (保量/保庫存)**：傳統媒體買法，先佔住版位。
      * **Bidding (競價)**：透過 RTB 機制競標流量。
      * **Sponsorship (包版)**：獨佔特定時段的特定版位。

  * **UB / LB (Upper Bound / Lower Bound)**：
    指績效指標的「上限」與「下限」。這是 Performance-based 廣告合約的特徵。

      * 例如 `vtr_lb = 0.70` 代表業務向客戶保證：「這波廣告的觀看率絕對不會低於 70%，否則我們補量或賠償。」

  * **Estimated Gross Margin (預估毛利)**：
    系統在報價階段即計算潛在利潤 (`Sales Price - Media Cost`)，讓業務主管決定是否核准該張訂單。

  * **Video Seconds Option (秒數選項)**：
    OneAD 作為影音廣告專精，將影片秒數視為一種「標準化商品規格」（如 6秒、15秒），不同秒數通常對應不同的 `uniprice` 定價策略。

-----
