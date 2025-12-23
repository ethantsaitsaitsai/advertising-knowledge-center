# 預算查詢指南

## 📊 預算定義

本系統的預算分為兩種類型，對應不同的業務階段：

### 1. **進單金額 / 投資金額 / 投資量**

**定義**：委刊有記錄且成功拋轉的金額

**數據來源**：`cue_list_budgets.budget`

**狀態過濾**：`cue_lists.status IN ('converted', 'requested')`

**使用 Template**：`investment_budget.sql`

**業務意義**：
- 代表「已簽約」或「已審核通過」的預算
- 財務上視為「應收帳款 (AR)」的基礎
- 用於業務報表、進單統計

---

### 2. **執行金額 / 認列金額**

**定義**：執行中或已結案的金額

**數據來源**：`pre_campaign.budget`

**狀態過濾**：`pre_campaign.status IN ('oncue', 'close') AND pre_campaign.trash = 0`

**使用 Template**：`execution_budget.sql`

**業務意義**：
- 代表「實際執行」的預算
- 財務上視為「營收認列」的基礎
- 用於成效報表、執行追蹤

---

## 🔧 使用方式

### 查詢投資金額（進單金額）

```python
from tools.template_loader import execute_template

# 查詢特定客戶的投資金額
investment_df = execute_template(
    "investment_budget.sql",
    client_names=["客戶名稱"],
    start_date="2024-01-01",
    end_date="2024-12-31"
)

# 返回欄位：
# - campaign_id
# - format_name (格式名稱)
# - investment_amount (投資金額)
# - investment_gift (投資贈送)
# - pricing_model (計價模式)
# - unit_price (單價)
# - guaranteed_volume (保證量)
# - estimated_gross_margin (預估毛利)
```

**特點**：
- ✅ 格式層級明細（一個 campaign 可能有多個格式）
- ✅ 包含計價模式和單價資訊
- ✅ 包含預估毛利

---

### 查詢執行金額（認列金額）

```python
# 查詢特定客戶的執行金額
execution_df = execute_template(
    "execution_budget.sql",
    client_names=["客戶名稱"],
    start_date="2024-01-01",
    end_date="2024-12-31"
)

# 返回欄位：
# - campaign_id
# - execution_id
# - media_name (媒體名稱)
# - execution_amount (執行金額)
# - execution_gift (執行贈送)
# - target_plays (目標播放數)
# - target_reach (目標到達人數)
# - execution_status (執行狀態)
# - execution_start_date, execution_end_date
```

**特點**：
- ✅ 執行單層級明細（一個 campaign 可能有多個執行單）
- ✅ 包含執行狀態和日期
- ✅ 包含目標數量資訊

---

### 查詢預算摘要（整合視圖）

```python
# 查詢特定 campaign 的預算摘要
budget_summary_df = execute_template(
    "budget_details.sql",
    campaign_ids=[12345, 67890]
)

# 返回欄位：
# - campaign_id
# - contract_total_budget (L1: 合約總預算)
# - campaign_budget (L2: 活動預算)
# - total_investment_amount (投資金額總和)
# - total_execution_amount (執行金額總和)
# - budget_gap (預算缺口 = 投資 - 執行)
# - gross_type (Net/Gross)
# - gsp_type (GSP 購買標記)
```

**特點**：
- ✅ 整合投資與執行金額
- ✅ 自動計算預算缺口
- ✅ Campaign 層級聚合（不包含明細）

---

## 📈 使用場景

### 場景 1：投資金額分析（進單報表）

**需求**：查詢某客戶在某期間的投資金額，按格式分組

```python
# 1. 查詢投資金額明細
investment_df = execute_template(
    "investment_budget.sql",
    client_names=["客戶A"],
    start_date="2024-Q1",
    end_date="2024-Q1"
)

# 2. 按格式聚合
format_analysis = investment_df.groupby('format_name').agg({
    'investment_amount': 'sum',
    'campaign_id': 'nunique'
}).rename(columns={'campaign_id': 'campaign_count'})

print(format_analysis)
# Output:
#                investment_amount  campaign_count
# In-Stream 15s      5,000,000            3
# Out-Stream 6s      2,000,000            2
```

---

### 場景 2：執行金額分析（認列報表）

**需求**：查詢某客戶已執行的金額

```python
# 1. 查詢執行金額明細
execution_df = execute_template(
    "execution_budget.sql",
    client_names=["客戶A"]
)

# 2. 按狀態聚合
status_analysis = execution_df.groupby('execution_status').agg({
    'execution_amount': 'sum',
    'execution_id': 'count'
})

print(status_analysis)
# Output:
#          execution_amount  execution_id
# oncue       3,500,000           5
# close       1,200,000           3
```

---

### 場景 3：預算缺口分析

**需求**：查詢投資金額與執行金額的差距

```python
# 1. 查詢預算摘要
budget_summary = execute_template(
    "budget_details.sql",
    campaign_ids=[...]
)

# 2. 分析預算缺口
gap_analysis = budget_summary[
    ['campaign_id', 'total_investment_amount', 'total_execution_amount', 'budget_gap']
]

# 找出缺口過大的 campaigns
large_gap = gap_analysis[gap_analysis['budget_gap'] > 100000]
print(f"發現 {len(large_gap)} 個 campaigns 有較大預算缺口")
```

---

### 場景 4：投資 vs 執行對比

**需求**：同時查詢投資與執行金額，進行對比分析

```python
# 1. 先取得 campaign_ids
basic_df = execute_template("campaign_basic.sql", client_names=["客戶A"])
campaign_ids = basic_df['campaign_id'].tolist()

# 2. 查詢投資金額
investment_df = execute_template("investment_budget.sql", campaign_ids=campaign_ids)

# 3. 查詢執行金額
execution_df = execute_template("execution_budget.sql", campaign_ids=campaign_ids)

# 4. 聚合到 campaign 層級
investment_agg = investment_df.groupby('campaign_id')['investment_amount'].sum()
execution_agg = execution_df.groupby('campaign_id')['execution_amount'].sum()

# 5. 合併分析
comparison = pd.DataFrame({
    'investment': investment_agg,
    'execution': execution_agg
})
comparison['utilization_rate'] = comparison['execution'] / comparison['investment']

print(comparison)
# Output:
#              investment  execution  utilization_rate
# campaign_id
# 12345        1,000,000    800,000           0.80
# 67890        2,000,000  2,100,000           1.05  # 超支
```

---

## ⚠️ 注意事項

### 1. 聚合層級不同

**投資金額** (`investment_budget.sql`):
- 返回**格式層級**明細
- 一個 campaign 可能有多筆（因為有多個格式）
- 需要 `groupby('campaign_id')` 聚合到 campaign 層級

**執行金額** (`execution_budget.sql`):
- 返回**執行單層級**明細
- 一個 campaign 可能有多筆（因為有多個執行單）
- 需要 `groupby('campaign_id')` 聚合到 campaign 層級

**預算摘要** (`budget_details.sql`):
- 返回**campaign 層級**聚合
- 一個 campaign 只有一筆
- 已經聚合好，可直接使用

---

### 2. 狀態過濾的重要性

**投資金額**必須過濾 `status IN ('converted', 'requested')`：
- ✅ `converted` = 已簽約拋轉
- ✅ `requested` = 審核中（也計入進單）
- ❌ `cancelled` = 已取消（不計入）
- ❌ `archived` = 已封存（不計入）

**執行金額**必須過濾 `status IN ('oncue', 'close')` AND `trash = 0`：
- ✅ `oncue` = 投放中
- ✅ `close` = 已結案
- ❌ `draft` = 草稿（尚未執行）
- ❌ `pending` = 等待執行（尚未執行）
- ❌ `trash = 1` = 已刪除

---

### 3. 預算缺口的正常範圍

`budget_gap = total_investment - total_execution`

**正常情況**：
- `budget_gap > 0` → 還有預算未執行（正常）
- `budget_gap ≈ 0` → 預算執行完畢（正常）

**異常情況**：
- `budget_gap < 0` → 執行金額超過投資金額（超支，需檢查）
- `budget_gap >> 0` → 預算執行率過低（可能是執行延遲）

---

## 🔄 三個 Templates 的關係

```
investment_budget.sql          execution_budget.sql
       ↓                              ↓
  投資金額明細                    執行金額明細
  (格式層級)                     (執行單層級)
       ↓                              ↓
       └──────────┬───────────────────┘
                  ↓
         budget_details.sql
              ↓
         預算摘要（整合）
         (campaign 層級)
```

**建議使用順序**：
1. **需要明細** → 使用 `investment_budget.sql` 或 `execution_budget.sql`
2. **需要摘要** → 使用 `budget_details.sql`
3. **需要對比分析** → 兩者都用，然後在 pandas 中 merge

---

## 📚 相關文檔

- [README.md](./README.md) - 所有 templates 總覽
- [USAGE_GUIDE.md](./USAGE_GUIDE.md) - Agent 整合指南
- [template_index.yaml](./template_index.yaml) - Template 元數據

**最後更新**: 2025-12-23
