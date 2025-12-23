# SQL Template 使用說明

## 概述

此資料夾包含模組化的 Jinja2 SQL templates，每個 template 負責查詢單一維度的資料。Agent 可根據使用者意圖選擇一個或多個 templates 執行，並透過 `campaign_id` 進行 pandas merge。

## Template 清單

### 1. `campaign_basic.sql`
**功能**: 活動基本資訊
**返回欄位**:
- `campaign_id` (Merge Key)
- `client_name`, `brand`, `contract_name`, `campaign_name`
- `start_date`, `end_date`, `budget`
- `campaign_status`, `contract_status`
- `objective_name`, `agency_name`

**使用時機**:
- 所有查詢的基礎資訊
- 需要客戶、活動名稱時

**範例參數**:
```python
{
    "campaign_ids": [12345, 67890],  # Optional
    "client_names": ["悠遊卡"],
    "start_date": "2024-01-01",
    "end_date": "2024-12-31"
}
```

---

### 2. `ad_formats.sql`
**功能**: 廣告格式明細（從合約層級）
**返回欄位**:
- `campaign_id` (Merge Key)
- `format_name`, `format_type_id`
- `video_seconds`, `platform`
- `frequency_cap`, `media_name`

**使用時機**:
- "投遞的格式是什麼？"
- "有哪些秒數的影片？"
- "PC 和 Mobile 的比例？"

**範例查詢**:
```
"悠遊卡投遞的格式有哪些？"
→ Agent 選擇: campaign_basic.sql + ad_formats.sql
→ Merge on: campaign_id
```

---

### 3. `targeting_segments.sql`
**功能**: 數據鎖定 / 受眾標籤設定
**返回欄位**:
- `campaign_id` (Merge Key)
- `segment_name`, `segment_en_name`
- `segment_category`, `audience_size`
- `logic_type` (Include/Exclude)
- `data_source`, `lookback_days`, `update_type`

**使用時機**:
- "數據鎖定是什麼？"
- "受眾標籤有哪些？"
- "鎖定多少人？"

**範例查詢**:
```
"悠遊卡的數據鎖定條件？"
→ Agent 選擇: campaign_basic.sql + targeting_segments.sql
```

---

### 4. `media_placements.sql`
**功能**: 投放媒體與版位明細
**返回欄位**:
- `campaign_id` (Merge Key)
- `placement_id`, `pid`, `pid_name`
- `media_name`, `ad_type`
- `ad_format_name`, `pricing_model`, `unit_price`
- `budget`, `target_impressions`

**使用時機**:
- "投遞在哪些媒體？"
- "有哪些版位 (Placement)？"
- "各版位的預算和目標數？"

**注意**: 此 template 回傳執行層級 (L4) 資料，可能一個 campaign 對應多筆 placement

---

### 5. `product_lines.sql`
**功能**: 產品線與購買方式
**返回欄位**:
- `campaign_id` (Merge Key)
- `product_line_name`, `product_line_en_name`
- `purchase_way`, `purchase_way_desc`

**使用時機**:
- "買的是什麼產品線？"
- "是保量購買還是競價？"

**購買方式說明**:
- `Reserved (保量)`: 保證庫存
- `Bidding (競價)`: RTB 競價
- `Sponsorship (包版)`: 獨佔版位

---

### 6. `budget_details.sql`
**功能**: 預算細項（含總預算、贈送、外購等）
**返回欄位**:
- `campaign_id` (Merge Key)
- **L1 合約層**: `contract_total_budget`, `contract_external_budget`, `contract_onead_gift`
- **L2 活動層**: `campaign_budget`, `currency_id`, `exchange_rate`
- **L3 執行層**: `execution_total_budget`, `execution_onead_gift`
- `gross_type`, `gsp_type`

**使用時機**:
- "格式投資金額是多少？"
- "總預算多少？有多少是贈送的？"
- "外購預算佔比？"

**預算層級說明**:
```
L1 (Contract)  → 應收帳款（財務認列）
L2 (Campaign)  → 執行分配預算
L3 (Execution) → 系統扣款上限
L4 (Placement) → 版位虛擬限額
```

---

### 7. `contract_kpis.sql`
**功能**: 合約承諾 KPI（CTR, VTR, CVR, ER 的上下限）
**返回欄位**:
- `campaign_id` (Merge Key)
- `format_name`
- `ctr_lower_bound`, `ctr_upper_bound`
- `vtr_lower_bound`, `vtr_upper_bound`
- `cvr_lower_bound`, `cvr_upper_bound`
- `er_lower_bound`, `er_upper_bound`
- `guaranteed_count`, `pricing_model`, `unit_price`

**使用時機**:
- "保證的成效是多少？"
- "CTR / VTR 的承諾範圍？"
- "各格式的 KPI 目標？"

**注意**: 同一個 campaign 可能有多個格式，每個格式有不同的 KPI 承諾

---

### 8. `execution_status.sql`
**功能**: 執行狀態與投放控制設定
**返回欄位**:
- `campaign_id` (Merge Key)
- `execution_id`, `status`, `status_desc`
- `priority`, `frequency_cap`
- `delivery_strategy`, `publisher_speed`
- `inventory_types`, `url_filter_type`
- `target_devices`, `weather_conditions`
- `execution_start_date`, `execution_end_date`

**使用時機**:
- "投放狀態是什麼？"
- "有設定頻率控制嗎？"
- "投放策略是平均還是加速？"
- "有黑白名單嗎？"

---

## 使用流程

### Step 1: Agent 根據意圖選擇 Templates

```python
# 範例：使用者問 "悠遊卡投遞的格式、成效、數據鎖定，格式投資金額"
selected_templates = [
    "campaign_basic.sql",       # 基本資訊
    "ad_formats.sql",           # 格式
    "targeting_segments.sql",   # 數據鎖定
    "budget_details.sql",       # 投資金額
    "contract_kpis.sql"         # 成效承諾
]
```

### Step 2: 執行多個 Templates

```python
from jinja2 import Template
import pandas as pd

results = {}
for template_name in selected_templates:
    # 讀取 template
    with open(f"templates/sql/{template_name}") as f:
        template = Template(f.read())

    # 渲染 SQL（傳入參數）
    sql = template.render(
        campaign_ids=[12345, 67890],  # 從前一步驟取得
        client_names=["悠遊卡"]
    )

    # 執行查詢
    df = execute_mysql_query(sql)
    results[template_name] = df
```

### Step 3: Pandas Merge

```python
# 從 campaign_basic 開始
base_df = results["campaign_basic.sql"]

# 依序 merge 其他 dataframes
for template_name in ["ad_formats.sql", "targeting_segments.sql", ...]:
    df = results[template_name]
    base_df = base_df.merge(
        df,
        on='campaign_id',
        how='left'  # 或 'outer' 根據需求
    )

# 處理一對多關係（例如：一個 campaign 有多個格式）
# 可使用 groupby + agg
aggregated = base_df.groupby(['campaign_id', 'campaign_name']).agg({
    'format_name': lambda x: ', '.join(x.unique()),
    'segment_name': lambda x: ', '.join(x.unique()),
    'budget': 'first',  # 預算取第一筆（避免重複計算）
    ...
})
```

### Step 4: 回傳給使用者

```python
# 格式化輸出
final_result = aggregated.to_dict('records')
# 或轉成自然語言回應
```

---

## 設計原則

### ✅ 單一職責
每個 template 只負責一個維度（格式/鎖定/預算/...），不做複雜 JOIN

### ✅ 必有 Merge Key
所有 template 都返回 `campaign_id`，部分還有 `placement_id`

### ✅ 包含 Lookup Join
避免只返回 ID，直接 join 出名稱（如 `ad_format_types.name`）

### ✅ 支援過濾參數
- `campaign_ids`: 指定要查詢的活動（必要時）
- `client_names`: 客戶名稱過濾
- `start_date`, `end_date`: 日期範圍

### ✅ 可組合性
任意組合多個 templates，透過 pandas merge 整合

---

## 常見查詢範例

### 範例 1: "悠遊卡投遞的格式和預算"
```python
templates = [
    "campaign_basic.sql",
    "ad_formats.sql",
    "budget_details.sql"
]
# Merge on: campaign_id
```

### 範例 2: "悠遊卡的數據鎖定和受眾規模"
```python
templates = [
    "campaign_basic.sql",
    "targeting_segments.sql"
]
# 從 targeting_segments 可以取得 audience_size
```

### 範例 3: "悠遊卡各格式的 KPI 承諾"
```python
templates = [
    "campaign_basic.sql",
    "ad_formats.sql",
    "contract_kpis.sql"
]
# Merge 後可以看到每個格式的 CTR/VTR 保證範圍
```

### 範例 4: "悠遊卡投放在哪些媒體，各媒體的預算？"
```python
templates = [
    "campaign_basic.sql",
    "media_placements.sql"
]
# 注意：media_placements 是 L4 層級，會有多筆
# 需要 groupby(['campaign_id', 'media_name']).agg({'budget': 'sum'})
```

---

## 注意事項

### ⚠️ 一對多關係
某些 templates 會返回多筆資料（例如：一個 campaign 有多個格式、多個受眾標籤）

**解決方案**:
```python
# 方案 1: 字串聚合
df.groupby('campaign_id').agg({
    'format_name': lambda x: ', '.join(x.unique())
})

# 方案 2: 保留明細，由 Agent 決定如何呈現
# 例如：「悠遊卡使用了 In-Stream 6秒 和 Out-Stream 15秒 兩種格式」
```

### ⚠️ 預算加總陷阱
不同層級的預算不可直接加總：
- `contract_total_budget` (L1) ≠ SUM(`campaign_budget`) (L2)
- `campaign_budget` (L2) ≠ SUM(`execution_budget`) (L3)

**原因**:
- L1 包含外購和內部成本
- L2 可能有追加預算
- L3 可能有共用預算池 (`same_budget_pool_symbol`)

### ⚠️ 狀態過濾
根據查詢意圖選擇狀態：
- **投資/進單**: `cue_lists.status IN ('converted', 'requested')`
- **執行中**: `pre_campaign.status IN ('oncue', 'booked')`
- **已結案**: `pre_campaign.status = 'closed'`

---

## 擴展指南

### 新增 Template 的步驟

1. **確定查詢維度**: 這個 template 負責什麼資訊？（例如：素材、轉換追蹤）

2. **設計返回欄位**:
   - 必須包含 `campaign_id`
   - 包含 lookup join 的名稱欄位
   - 避免過多計算邏輯

3. **定義參數**:
   - `campaign_ids` (通常是必要參數)
   - 其他過濾條件

4. **撰寫 SQL**:
   - 從核心表開始 (通常是 `one_campaigns` 或 `pre_campaign`)
   - LEFT JOIN 相關的 lookup 表
   - 加上 Jinja2 條件過濾

5. **更新此 README**: 說明使用時機和範例

---

## Troubleshooting

### Q: Merge 後資料筆數暴增？
A: 檢查是否有笛卡爾積。例如：一個 campaign 有 3 個格式 × 2 個受眾標籤 = 6 筆資料。需要使用 `groupby` 聚合。

### Q: 某些 campaign 查不到格式資訊？
A: 可能該 campaign 沒有設定 `cue_list_ad_formats`。使用 `LEFT JOIN` 和 `how='left'` merge 可避免遺失。

### Q: 預算數字對不上？
A: 確認你查的是哪一層級的預算：
- L1 (Contract): `cue_lists.total_budget`
- L2 (Campaign): `one_campaigns.budget`
- L3 (Execution): `pre_campaign.budget`

---

## 聯絡資訊

如有問題或建議新增 templates，請聯絡開發團隊。
