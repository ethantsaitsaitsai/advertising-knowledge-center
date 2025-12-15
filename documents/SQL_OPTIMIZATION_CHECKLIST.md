# SQL 優化檢查清單 (SQL Optimization Checklist)

本文件列出在生成和執行 SQL 查詢時應遵循的優化策略。

## 📋 查詢生成優化

### 1. 條件前推 (Filter Push Down) ⭐⭐⭐ 最高優先級

**原則**: Company / Brand 過濾必須在 JOIN 之前進行，減少後續的數據量。

**檢查項**:
- [ ] WHERE 子句中包含 `clients.company = '...'` 過濾
- [ ] 該過濾在第一個 JOIN clients 之後立即執行
- [ ] 不要在 pre_campaign 之後才過濾（此時已經膨脹了）

**範例 (✅ 正確)**:
```sql
FROM one_campaigns oc
JOIN cue_lists cl ON oc.cue_list_id = cl.id
JOIN clients c ON cl.client_id = c.id
WHERE c.company = 'ABC公司'  -- 【立即過濾】
LEFT JOIN pre_campaign pc ON oc.id = pc.one_campaign_id
```

**範例 (❌ 錯誤)**:
```sql
FROM one_campaigns oc
JOIN pre_campaign pc ON oc.id = pc.one_campaign_id  -- 膨脹成百萬行
JOIN cue_lists cl ON oc.cue_list_id = cl.id
JOIN clients c ON cl.client_id = c.id
WHERE c.company = 'ABC公司'  -- 太晚
```

---

### 2. Subquery 優化 (Pre-Aggregation) ⭐⭐⭐

**原則**: 先在子查詢中聚合大型表，再與主表 JOIN，避免 Cartesian Product。

**檢查項**:
- [ ] 當需要關聯 `pre_campaign` 時，使用子查詢先聚合
- [ ] 子查詢中計算 `SUM(budget)` / `GROUP_CONCAT` 等
- [ ] 子查詢按 `one_campaign_id` 分組
- [ ] 主查詢 LEFT JOIN 子查詢結果

**範例 (✅ 推薦)**:
```sql
SELECT
    oc.id AS cmpid,
    oc.name AS Campaign_Name,
    BudgetInfo.Budget_Sum
FROM one_campaigns oc
LEFT JOIN (
    SELECT
        one_campaign_id,
        SUM(budget) AS Budget_Sum
    FROM pre_campaign
    GROUP BY one_campaign_id
) AS BudgetInfo ON oc.id = BudgetInfo.one_campaign_id
```

**範例 (❌ 避免)**:
```sql
SELECT
    oc.id AS cmpid,
    oc.name AS Campaign_Name,
    SUM(pc.budget) AS Budget_Sum
FROM one_campaigns oc
JOIN pre_campaign pc ON oc.id = pc.one_campaign_id
LEFT JOIN pre_campaign_detail pcd ON pc.id = pcd.pre_campaign_id
-- ... 更多 JOIN
GROUP BY oc.id  -- Cartesian Product 膨脹
```

---

### 3. 避免重複掃描 Pre_Campaign ⭐⭐

**原則**: 若有多個以 pre_campaign 為基礎的聚合需求（格式、受眾、預算），應一次性計算。

**檢查項**:
- [ ] 不存在多個獨立的 pre_campaign JOIN
- [ ] 所有聚合在同一個子查詢中完成
- [ ] 若必須分離，使用 UNION 或多個子查詢再 JOIN

**範例 (✅ 推薦)**:
```sql
SELECT
    oc.id AS cmpid,
    SegmentInfo.Segment_Category,
    SegmentInfo.Budget_Sum,
    SegmentInfo.Ad_Format
FROM one_campaigns oc
LEFT JOIN (
    SELECT
        pc.one_campaign_id,
        GROUP_CONCAT(ts.description) AS Segment_Category,
        GROUP_CONCAT(aft.title) AS Ad_Format,
        SUM(pc.budget) AS Budget_Sum
    FROM pre_campaign pc
    LEFT JOIN pre_campaign_detail pcd ON pc.id = pcd.pre_campaign_id
    LEFT JOIN ad_format_types aft ON pcd.ad_format_type_id = aft.id
    LEFT JOIN campaign_target_pids ctp ON pc.id = ctp.source_id
    LEFT JOIN target_segments ts ON ctp.selection_id = ts.id
    GROUP BY pc.one_campaign_id
) AS SegmentInfo ON oc.id = SegmentInfo.one_campaign_id
```

---

### 4. 去除不必要的 DISTINCT ⭐⭐

**原則**: `GROUP_CONCAT(DISTINCT ...)` 很昂貴，若資料已保證唯一則移除。

**檢查項**:
- [ ] 檢查 FK 約束是否保證唯一性
- [ ] 若預先在子表層級去重，移除 DISTINCT
- [ ] 使用 `GROUP_CONCAT(...)` 替代 `GROUP_CONCAT(DISTINCT ...)`

**範例 (✅ 推薦)**:
```sql
-- 若 ad_format_types.id 已保證唯一（FK 約束）
SELECT
    pc.one_campaign_id,
    GROUP_CONCAT(aft.title SEPARATOR '; ') AS Ad_Format  -- 移除 DISTINCT
FROM pre_campaign pc
LEFT JOIN pre_campaign_detail pcd ON pc.id = pcd.pre_campaign_id
LEFT JOIN ad_format_types aft ON pcd.ad_format_type_id = aft.id
GROUP BY pc.one_campaign_id
```

---

### 5. JOIN 欄位型別一致性 ⭐⭐⭐

**原則**: 所有 id / *_id 欄位的型別和 unsigned 設定必須完全一致。

**檢查項**:
- [ ] 檢查 Schema 中所有 id 欄位的類型（INT / BIGINT）
- [ ] 確認是否都是 UNSIGNED
- [ ] 在 ON 子句中使用完全相同的類型
- [ ] 避免隱性轉型（可能導致索引失效）

**範例 (✅ 正確)**:
```sql
-- clients.id 是 BIGINT UNSIGNED
-- cue_lists.client_id 是 BIGINT UNSIGNED
JOIN clients c ON cl.client_id = c.id  -- 類型完全匹配
```

**範例 (❌ 錯誤)**:
```sql
-- clients.id 是 BIGINT UNSIGNED
-- cue_lists.client_id 是 INT (不同類型！)
JOIN clients c ON cl.client_id = c.id  -- 隱性轉型，索引可能失效
```

---

### 6. 避免 JOIN 條件中使用函式 ⭐⭐

**原則**: 直接使用欄位進行 JOIN，避免函式包裹導致索引失效。

**檢查項**:
- [ ] WHERE 條件不使用 `DATE()`, `YEAR()`, `MONTH()` 等函式
- [ ] 日期比較使用範圍條件（>= 和 <）
- [ ] 字串比較不使用 `UPPER()`, `LOWER()`, `CONCAT()` 等

**範例 (✅ 推薦)**:
```sql
WHERE one_campaigns.start_date >= '2024-01-01'
  AND one_campaigns.start_date < '2024-01-02'
```

**範例 (❌ 避免)**:
```sql
WHERE DATE(one_campaigns.start_date) = '2024-01-01'  -- 函式包裹，索引失效
```

---

## 🔍 查詢執行優化

### 7. 確認索引使用

**系統已建立的索引**:
- `clients(company)` - 廣告主快速查詢
- `cue_lists(client_id)` - 客戶關聯
- `one_campaigns(cue_list_id)` - 合約關聯
- `pre_campaign(one_campaign_id)` - 執行層關聯
- `pre_campaign_detail(pre_campaign_id)` - 詳細資訊
- `campaign_target_pids(source_id, source_type)` - 複合索引
- `campaign_target_pids(selection_id)` - 受眾查詢

**檢查方法**:
```sql
EXPLAIN FORMAT=JSON SELECT ...
```

查看是否出現以下紅旗：
- ❌ `"access_type": "ALL"` - 全表掃描
- ❌ `"Using temporary; Using filesort"` - 排序操作
- ❌ 預期的索引在 `possible_keys` 中但不在 `key` 中

---

### 8. 執行時間監控

**目標**:
- ✅ < 1 秒：最佳
- ✅ 1-5 秒：可接受
- ⚠️ 5-10 秒：需要優化
- ❌ > 10 秒：必須優化

**優化步驟**:
1. 運行 EXPLAIN 分析
2. 檢查是否遵循上述 1-6 項優化
3. 驗證索引是否被使用
4. 考慮添加缺失的索引
5. 如必要，使用查詢快取或物化視圖

---

## 📊 查詢層級特定優化

### CONTRACT 層 (cue_lists)
- [ ] 索引: `clients(company)` 用於 WHERE 過濾
- [ ] 不需 pre_campaign JOIN（除非需要執行細節）
- [ ] 預算直接來自 `cue_lists.total_budget`

### STRATEGY 層 (one_campaigns)
- [ ] 索引: `cue_lists(client_id)` 用於 JOIN
- [ ] 使用子查詢聚合 pre_campaign 預算
- [ ] 按 one_campaign_id 分組

### EXECUTION 層 (pre_campaign)
- [ ] 【條件前推】在 clients 層過濾
- [ ] 【Subquery】在子查詢中聚合 pre_campaign_detail
- [ ] 使用 GROUP_CONCAT 壓縮格式列表

### AUDIENCE 層 (target_segments)
- [ ] 【條件前推】在 clients 層過濾
- [ ] 【Subquery】在子查詢中聚合受眾
- [ ] 使用複合索引 `campaign_target_pids(source_id, source_type)`

---

## 🚀 快速檢查清單

在生成 SQL 時，使用此清單快速驗證：

```
☐ 條件前推：company 過濾在 clients JOIN 後立即執行
☐ Subquery：pre_campaign 聚合在子查詢中
☐ 無重複：不存在多個 pre_campaign JOIN
☐ 無 DISTINCT：移除不必要的 DISTINCT
☐ 型別一致：所有 id 欄位型別完全匹配
☐ 無函式：WHERE 條件中無 DATE()、UPPER() 等
☐ 執行時間 < 5 秒
☐ EXPLAIN 顯示索引使用
```

---

## 📚 參考

- [MySQL EXPLAIN 解讀](https://dev.mysql.com/doc/refman/8.0/en/explain.html)
- [MySQL 索引優化](https://dev.mysql.com/doc/refman/8.0/en/optimization-indexes.html)
- [子查詢優化](https://dev.mysql.com/doc/refman/8.0/en/subquery-optimization.html)
