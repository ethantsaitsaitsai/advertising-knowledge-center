# DataFusion Budget 聚合邏輯分析報告

## 1. 問題背景

DataFusion 需要處理兩種不同粒度的數據聚合：
1. **Pre-Aggregation**: 當SQL返回包含 Segment_Category 的多行數據時，需要合併相同 (campaign, format) 的行
2. **Re-Aggregation**: 根據用戶請求的維度（dimensions），進一步聚合數據

關鍵問題：**這兩個階段對 budget 的處理策略不一致**
- Pre-Agg 使用 `MAX`
- Re-Agg 使用 `SUM`

## 2. 當前實現分析

### 2.1 Pre-Aggregation (Line 130-167)

**觸發條件**: 檢測到 Segment_Category 列

**Group Keys**: `cmpid`, `ad_format_type_id`, 以及其他非數值維度

**Budget 處理** (Line 159-160):
```python
if 'budget' in col.lower():
    agg_dict_pre[col] = 'max'
```

**設計意圖**:
- 假設 SQL 已經正確計算了 budget（使用 pcd.budget 並 GROUP BY format）
- 同一個 (cmpid, ad_format_type_id) 的多行 budget 應該相同
- 使用 MAX 是為了"去重"而不是聚合

### 2.2 Re-Aggregation (Line 335-361)

**Group Keys**: 用戶請求的維度（如 Agency, Campaign_Name 等）

**Budget 處理** (Line 340-344):
```python
if 'budget' in col_lower or 'sum' in col_lower:
    if col not in group_cols and col not in agg_dict:
        merged_df[col] = pd.to_numeric(merged_df[col], errors='coerce').fillna(0)
        agg_dict[col] = 'sum'
```

**設計意圖**:
- 將不同 formats 的 budget 加總
- 例如：Campaign A 有 Banner(100) 和 Video(200)，總預算 = 300

## 3. 場景測試

### 場景 1: AUDIENCE 查詢（有 Ad_Format 維度）

**SQL 返回** (使用修復後的優化版模板):
```
cmpid | ad_format_type_id | Segment_Category | Budget_Sum
101   | 1                 | A; B; C          | 100
101   | 2                 | A; B; C          | 150
```

**Pre-Agg 執行**:
- 檢測到 Segment_Category ✅
- Group by (cmpid, ad_format_type_id)
- 每組只有 1 行，MAX(100) = 100 ✅
- **結果**: 不變（2行）

**User Request**: "顯示所有活動的預算"（不要求 format 維度）

**Re-Agg 執行**:
- Group by (cmpid) or (campaign_name)
- Budget: SUM(100 + 150) = 250 ✅
- **結果**: 正確

**結論**: ✅ 在正確的 SQL 下，MAX + SUM 組合正確

---

### 場景 2: AUDIENCE 查詢（舊的簡化版，已修復）

**舊 SQL 返回** (問題版本):
```
cmpid | Segment_Category | Budget_Sum
101   | A; B; C          | 300  ← 錯誤！(100 × 3 segments)
```

**Pre-Agg 執行**:
- 檢測到 Segment_Category ✅
- Group by (cmpid)
- 只有 1 行，MAX(300) = 300 ❌
- **問題**: MAX 無法修復 SQL 層面的錯誤

**新 SQL 返回** (修復後):
```
cmpid | Segment_Category | Budget_Sum
101   | A; B; C          | 100  ← 正確
```

**結論**: ✅ 修復 SQL 後問題解決

---

### 場景 3: 異常情況 - SQL 返回不一致的 budget

**假設 SQL 錯誤返回**:
```
cmpid | ad_format_type_id | Segment_Category | Budget_Sum
101   | 1                 | A                | 100
101   | 1                 | B                | 120  ← 同一個 format 卻有不同 budget？
101   | 1                 | C                | 110
```

**Pre-Agg 執行**:
- Group by (cmpid, ad_format_type_id)
- Budget: MAX(100, 120, 110) = 120
- **問題**:
  - 丟失了數據 (100 和 110 被忽略)
  - 無法檢測異常
  - 靜默失敗

**如果使用 SUM**:
- Budget: SUM(100 + 120 + 110) = 330
- **問題**:
  - 錯誤地加總了應該相同的值
  - 但至少會產生明顯異常的數字，容易被發現

**結論**: ⚠️ MAX 可能掩蓋數據異常

## 4. 核心問題分析

### 問題 1: Pre-Agg 的 MAX 假設可能不成立

**假設**: 同一個 (cmpid, ad_format_type_id) 的所有行的 budget 值相同

**風險**:
1. 如果 SQL 有 bug，返回不一致的值，MAX 會靜默丟失數據
2. 無法檢測到數據質量問題

### 問題 2: MAX 和 SUM 的語義不一致

**Pre-Agg**: 用 MAX 表示"這些值應該相同，取任意一個"
**Re-Agg**: 用 SUM 表示"將不同組的值加總"

這兩種語義混合可能導致混淆。

## 5. 改進建議

### 建議 1: 添加 Budget 一致性驗證（高優先級）

在 Pre-Agg 階段，檢查同一組的 budget 是否一致：

```python
# In Pre-Aggregation section (after Line 154)
if 'budget' in col.lower():
    # Check consistency before aggregating
    def budget_agg_with_check(x):
        unique_vals = x.dropna().unique()
        if len(unique_vals) > 1:
            variance = x.std() / x.mean() if x.mean() > 0 else 0
            if variance > 0.01:  # 1% threshold
                print(f"⚠️ WARNING: Budget inconsistency detected for column '{col}'")
                print(f"   Values: {unique_vals}, Mean: {x.mean():.2f}, Std: {x.std():.2f}")
        return x.max()  # Still use max, but with warning

    agg_dict_pre[col] = budget_agg_with_check
```

### 建議 2: 添加三階段 Budget 總計驗證（高優先級）

在 data_fusion.py 的 Line 110, 253, 368 已經有 DEBUG 日誌，添加驗證邏輯：

```python
# After Line 368, add validation
if raw_budget_total > 0 and agg_budget_total > 0:
    budget_diff_pct = abs(agg_budget_total - raw_budget_total) / raw_budget_total * 100

    # Tolerance based on query level
    tolerance = 5  # 5% for most queries
    query_level = state.get('query_level', 'strategy')
    if query_level == 'execution' and 'ad_format_type_id' in final_df.columns:
        tolerance = 10  # Higher tolerance for format-level queries (due to potential rounding)

    if budget_diff_pct > tolerance:
        warning = (
            f"⚠️ Budget Consistency Warning:\n"
            f"   Raw SQL Total: {raw_budget_total:,.0f}\n"
            f"   Post-Agg Total: {agg_budget_total:,.0f}\n"
            f"   Difference: {budget_diff_pct:.1f}% (Tolerance: {tolerance}%)\n"
            f"   Possible causes: SQL duplication, incorrect GROUP BY, or Cartesian product"
        )
        debug_logs.append(warning)
        print(f"DEBUG [DataFusion] {warning}")
```

### 建議 3: 改進 Pre-Agg 邏輯（中優先級）

根據數據特性決定聚合策略：

```python
if 'budget' in col.lower():
    def smart_budget_agg(x):
        """
        Smart aggregation for budget:
        - If all values are same: return that value (de-duplication)
        - If values differ: return max with warning
        """
        unique_vals = x.dropna().unique()
        if len(unique_vals) == 0:
            return 0
        elif len(unique_vals) == 1:
            return unique_vals[0]  # All same, perfect
        else:
            # Values differ - potential issue
            max_val = x.max()
            min_val = x.min()
            if (max_val - min_val) / max_val > 0.01:  # > 1% difference
                print(f"⚠️ Budget variance detected: min={min_val}, max={max_val}")
            return max_val  # Conservative: use max

    agg_dict_pre[col] = smart_budget_agg
```

## 6. 測試計劃

### 測試 1: 驗證修復後的 AUDIENCE 查詢
```python
# 測試無 Ad_Format 的 Audience 查詢
query = "顯示所有活動的受眾分類和預算"
# 預期: 使用新的子查詢模板
# 驗證: budget 總和正確
```

### 測試 2: 跨層級 Budget 一致性
```python
queries = {
    'strategy': "顯示所有活動",
    'execution': "顯示所有活動的格式分布",
    'audience': "顯示所有活動的受眾"
}
# 驗證: 三個查詢的 total budget 應該相同
```

### 測試 3: 觸發 Pre-Agg 的場景
```python
# 人工構造包含 Segment_Category 的數據
# 檢查 Pre-Agg 是否正確觸發
# 檢查 budget 聚合是否正確
```

## 7. 結論

| 項目 | 當前狀態 | 風險等級 | 建議 |
|------|---------|---------|------|
| SQL 模板 | ✅ 已修復 | 低 | 無 |
| Pre-Agg MAX 邏輯 | ⚠️ 可能掩蓋異常 | 中 | 添加一致性檢查 |
| Re-Agg SUM 邏輯 | ✅ 正確 | 低 | 無 |
| 三階段驗證 | ⚠️ 僅有日誌 | 中 | 添加自動驗證 |

**總體評估**:
1. 修復 AUDIENCE SQL 模板後，大部分場景應該正確
2. Pre-Agg 的 MAX 邏輯在正確的 SQL 下可以工作，但缺乏防禦性
3. 建議添加驗證機制，提高系統魯棒性
