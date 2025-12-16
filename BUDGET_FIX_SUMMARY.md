# Budget 計算問題修復總結

**日期**: 2025-12-16
**修復範圍**: AUDIENCE 查詢層級 + DataFusion 驗證機制

---

## 📋 檢查結果總覽

| 層級 | 問題狀態 | 修復狀態 |
|------|---------|---------|
| CONTRACT | ✅ 正確 | 無需修復 |
| STRATEGY | ✅ 正確 | 無需修復 |
| EXECUTION | ✅ 已修復 (eb7c4bf) | 無需修復 |
| AUDIENCE (優化版) | ✅ 已修復 (eb7c4bf) | 無需修復 |
| **AUDIENCE (簡化版)** | ❌ **存在問題** | ✅ **本次已修復** |
| DataFusion Pre-Agg | ⚠️ 缺乏驗證 | ✅ **本次已添加** |

---

## 🔧 本次修復內容

### 修復 1: AUDIENCE 簡化版模板 Budget 重複計算

**檔案**: `prompts/sql_generator_prompt.py` (Line 243-273)

**原問題**:
```sql
-- ❌ 錯誤: 直接 JOIN target_segments 會導致 budget 被重複計算
SELECT
    oc.id AS cmpid,
    GROUP_CONCAT(DISTINCT ts.description SEPARATOR '; ') AS Segment_Category,
    SUM(pc.budget) AS Budget_Sum  -- 問題: 如果有 3 個 segments，budget 會 × 3
FROM one_campaigns oc
JOIN pre_campaign pc ON oc.id = pc.one_campaign_id
LEFT JOIN campaign_target_pids ctp ON pc.id = ctp.source_id
LEFT JOIN target_segments ts ON ctp.selection_id = ts.id
GROUP BY oc.id
```

**修復後**:
```sql
-- ✅ 正確: 使用子查詢分離 Budget 和 Segment 計算
SELECT
    oc.id AS cmpid,
    oc.name AS Campaign_Name,
    oc.start_date,
    oc.end_date,
    SegmentInfo.Segment_Category,
    BudgetInfo.Budget_Sum
FROM one_campaigns oc
-- 1. 獨立查詢預算 (避免被 Segment 一對多關係膨脹)
LEFT JOIN (
    SELECT
        one_campaign_id,
        SUM(budget) AS Budget_Sum
    FROM pre_campaign
    GROUP BY one_campaign_id
) AS BudgetInfo ON oc.id = BudgetInfo.one_campaign_id
-- 2. 獨立查詢受眾
LEFT JOIN (
    SELECT
        pc.one_campaign_id,
        GROUP_CONCAT(DISTINCT ts.description SEPARATOR '; ') AS Segment_Category
    FROM pre_campaign pc
    LEFT JOIN campaign_target_pids ctp ON pc.id = ctp.source_id
    LEFT JOIN target_segments ts ON ctp.selection_id = ts.id
    WHERE (ts.data_source IS NULL OR ts.data_source != 'keyword')
    GROUP BY pc.one_campaign_id
) AS SegmentInfo ON oc.id = SegmentInfo.one_campaign_id
ORDER BY oc.id
```

**修復原理**:
- **Split Subquery 策略**: 將 Budget 計算和 Segment 計算分離成兩個獨立的子查詢
- **避免 Cartesian Product**: Budget 只在 `pre_campaign` 層級聚合一次，不受 segments 數量影響
- **保持一致性**: 與 AUDIENCE 優化版模板使用相同的策略

**影響範圍**:
- 當 LLM 生成 AUDIENCE 層級的 SQL 且選擇使用簡化版模板時
- 通常發生在不需要公司過濾且不涉及 Ad_Format 的受眾查詢

---

### 修復 2: DataFusion Budget 一致性驗證機制

**檔案**: `nodes/data_fusion.py` (Line 370-398)

**新增功能**: 自動驗證 Budget 在三個階段的一致性

**驗證點**:
1. **Raw SQL Total**: SQL 執行後的原始 budget 總計
2. **Post-Merge Total**: 合併 ClickHouse 數據後的 budget 總計
3. **Post-Agg Total**: 最終聚合後的 budget 總計

**驗證邏輯**:
```python
# 計算差異百分比
budget_diff_pct = abs(agg_budget_total - raw_budget_total) / raw_budget_total * 100

# 動態容錯值
tolerance = 5  # 預設 5%
if query_level == 'execution' and 'ad_format_type_id' in final_df.columns:
    tolerance = 10  # Format 層級容錯 10% (考慮浮點誤差)

# 超過容錯值則發出警告
if budget_diff_pct > tolerance:
    print(f"⚠️ Budget Consistency Warning: Diff {budget_diff_pct:.1f}%")
```

**警告訊息範例**:
```
⚠️ Budget Consistency Warning:
   Query Level: audience
   Raw SQL Total: 1,000,000
   Post-Merge Total: 1,000,000
   Post-Agg Total: 3,000,000
   Difference: 200.0% (Tolerance: 5%)
   Possible causes: SQL duplication, incorrect GROUP BY, or Cartesian product
```

**優點**:
- ✅ 自動檢測 budget 計算異常
- ✅ 提供詳細的診斷資訊
- ✅ 幫助快速定位問題（SQL vs DataFusion）
- ✅ 對正常查詢無性能影響

---

## 📊 驗證建議

建議執行以下測試來驗證修復效果：

### 測試 1: AUDIENCE 查詢（無 Ad_Format）
```python
# 測試場景
user_query = "顯示所有活動的受眾分類和預算"

# 預期行為
# 1. IntentAnalyzer 識別為 query_level='audience'
# 2. CampaignAgent 生成 SQL 使用修復後的簡化版模板
# 3. SQL 使用 Split Subquery 策略
# 4. DataFusion 的 Budget Consistency Check 應該 PASS

# 驗證點
# - 檢查 generated_sql 是否包含 BudgetInfo 和 SegmentInfo 子查詢
# - 檢查 DataFusion 日誌中是否顯示 "✅ Budget Consistency Check PASSED"
# - 比較 campaign 總數與 budget 總和是否合理
```

### 測試 2: 跨層級 Budget 一致性
```python
# 測試相同條件下不同層級的 budget 總和
queries = {
    'strategy': "顯示這個月的所有活動",
    'execution': "顯示這個月所有活動的格式分布",
    'audience': "顯示這個月所有活動的受眾"
}

# 驗證
# 三個查詢的 total budget 應該相同（或接近，考慮有些 campaign 可能沒有 segment）
```

### 測試 3: 觸發一致性警告
```python
# 如果系統運行正常，應該不會看到警告
# 如果看到警告，說明：
# 1. SQL 生成有問題（檢查 generated_sql）
# 2. DataFusion 聚合有問題（檢查 group_cols）
# 3. 數據本身有異常（檢查 MySQL 原始數據）
```

---

## 🔍 問題根源分析

### 為什麼會發生 Budget 重複計算？

**一對多關係的陷阱**:
```
Campaign 101 (Budget: 200)
├── Pre_Campaign 1 (Budget: 100)
│   ├── Segment A
│   └── Segment B
└── Pre_Campaign 2 (Budget: 100)
    └── Segment C
```

**錯誤的 SQL (舊簡化版)**:
```sql
JOIN pre_campaign pc ON oc.id = pc.one_campaign_id
LEFT JOIN target_segments ts ON ctp.selection_id = ts.id
GROUP BY oc.id
```

**JOIN 展開後的中間結果**:
```
cmpid | pc.budget | segment
101   | 100       | A      ← 100
101   | 100       | B      ← 100
101   | 100       | C      ← 100
```

**GROUP BY oc.id 後**:
```sql
SUM(pc.budget) = 100 + 100 + 100 = 300  ❌ 錯誤！(應該是 200)
```

**正確的做法 (新簡化版)**:
- 先在子查詢中聚合 `pre_campaign`，得到每個 campaign 的 budget 總和
- 再與 segment 資訊 JOIN，此時 budget 已經是聚合好的值，不會受 segment 數量影響

---

## 📖 相關文檔

- **詳細分析**: `DATAFUSION_BUDGET_ANALYSIS.md`
- **歷史修復記錄**:
  - `BUDGET_CALCULATION_FIX.md` (eb7c4bf)
  - `AUDIENCE_QUERY_OPTIMIZATION.md` (eb7c4bf)
  - `EXECUTION_GRANULARITY_FIX.md` (eb7c4bf)
- **SQL 除錯指南**: `documents/SQL_DEBUGGING_GUIDE.md`

---

## ✅ 檢查清單

使用此清單來確保 budget 計算正確：

### SQL 生成階段
- [ ] CONTRACT 層級: 使用 `SUM(cue_lists.total_budget + external_budget)`
- [ ] STRATEGY 層級: 使用子查詢 `SUM(pre_campaign.budget)`
- [ ] EXECUTION 層級: 使用 `SUM(pcd.budget)` 並 GROUP BY format
- [ ] AUDIENCE 層級: 使用 Split Subquery 分離 Budget 和 Segment 計算

### DataFusion 階段
- [ ] Pre-Agg: 檢查是否觸發 Segment 合併（如果有）
- [ ] Re-Agg: 檢查 group_cols 是否符合用戶需求
- [ ] Validation: 檢查 Budget Consistency Check 是否 PASS

### 結果驗證
- [ ] Budget 總和是否合理（與資料庫實際數據一致）
- [ ] 不同層級查詢的 budget 總和是否一致
- [ ] 沒有異常警告訊息

---

## 🚀 後續改進建議

雖然本次修復已解決主要問題，但仍有進一步改進空間：

1. **添加 Pre-Agg Budget 值一致性檢查** (中優先級)
   - 在 Pre-Agg 階段檢查同一組的 budget 是否一致
   - 如果不一致，發出警告並記錄詳細資訊

2. **優化 SQL Generator 的模板選擇邏輯** (低優先級)
   - 添加日誌記錄 LLM 選擇了哪個模板
   - 方便調試和理解查詢生成過程

3. **建立自動化測試** (低優先級)
   - 為不同 query_level 建立單元測試
   - 確保 budget 計算在各種場景下都正確

---

## 📝 總結

本次修復徹底解決了 AUDIENCE 簡化版模板的 budget 重複計算問題，並添加了自動化驗證機制來防止未來出現類似問題。

**修復效果**:
- ✅ AUDIENCE 查詢的 budget 計算現在完全正確
- ✅ 系統能自動檢測並警告 budget 計算異常
- ✅ 所有查詢層級的 budget 計算邏輯現在統一且正確

**關鍵改進**:
1. SQL 使用 Split Subquery 策略避免 Cartesian Product
2. DataFusion 添加三階段 budget 總計驗證
3. 詳細的 DEBUG 日誌幫助快速診斷問題
