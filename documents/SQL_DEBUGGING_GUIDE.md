# SQL 調試和性能分析指南

## 🔍 快速診斷流程

當 SQL 查詢執行緩慢時，按照以下步驟診斷：

### Step 1: 檢查執行時間

```python
# 在 campaign_data 中查看
execution_time = campaign_data.get("execution_time_seconds", 0)

if execution_time > 5:
    print(f"⚠️ 慢查詢: {execution_time:.2f} 秒")
    explain = campaign_data.get("explain_analysis")
```

### Step 2: 分析 EXPLAIN 輸出

系統自動在 > 5 秒時運行 EXPLAIN。查看輸出中的：

```json
{
  "query_block": {
    "select_id": 1,
    "table": {
      "table_name": "one_campaigns",
      "access_type": "range",  // 檢查這個
      "possible_keys": [...],   // 應有的索引
      "key": "idx_cue_list_id",  // 實際使用的索引
      "rows": 1000,             // 掃描行數
      "filtered": 50.0          // 過濾百分比
    }
  }
}
```

---

## 🚩 EXPLAIN 的紅旗信號

### 1. 全表掃描 (ALL)

```
"access_type": "ALL"
```

**問題**: 查詢沒有使用任何索引，掃描了整個表。

**原因**:
- 過濾條件無法使用索引
- 條件中包含函式 (DATE(), UPPER() 等)
- 欄位型別不匹配

**解決方案**:

```sql
-- ❌ 不好：使用函式
WHERE DATE(created_at) = '2024-01-01'

-- ✅ 好：使用範圍條件
WHERE created_at >= '2024-01-01' AND created_at < '2024-01-02'
```

### 2. Temporary & Filesort

```
"using": ["Using temporary", "Using filesort"]
```

**問題**: MySQL 創建了臨時表並執行了磁盤排序，非常慢。

**原因**:
- GROUP BY / ORDER BY 的欄位無法使用索引
- 要排序的數據太大，無法在內存中進行

**解決方案**:

```sql
-- ❌ 可能導致 filesort
SELECT category, SUM(amount) AS total
FROM orders
GROUP BY category
ORDER BY total DESC

-- ✅ 改進：若可能，在 GROUP BY 時即排序
SELECT category, SUM(amount) AS total
FROM orders
GROUP BY category
ORDER BY SUM(amount) DESC
```

### 3. 索引未被使用

```
"possible_keys": ["idx_company"],
"key": null
```

**問題**: 有適合的索引但沒被使用。

**原因**:
- 隱性型別轉換 (INT vs BIGINT)
- 複合索引無法使用（first column missing）
- 優化器判斷全表掃描更快

**解決方案**:

```sql
-- ❌ 型別不匹配（int vs varchar）
WHERE client_id = '123'

-- ✅ 型別一致
WHERE client_id = 123
```

---

## 📊 常見性能問題和解決方案

### 問題 1: Cartesian Product（行數膨脹）

**症狀**:
```
"rows": 10000000  // 預期 1000 行，實際掃描 1000 萬行
```

**原因**:
```sql
-- 一個 campaign (1 行) JOIN 10 個 pre_campaign (10 行)
-- JOIN 100 個 pre_campaign_detail (100 行)
-- = 1 × 10 × 100 = 1000 行
-- 但若沒有正確 GROUP BY，會掃描所有 1000 萬行
```

**解決方案**:

```sql
-- ❌ Cartesian Product
SELECT oc.id, SUM(pcd.amount)
FROM one_campaigns oc
JOIN pre_campaign pc ON oc.id = pc.one_campaign_id
LEFT JOIN pre_campaign_detail pcd ON pc.id = pcd.pre_campaign_id
-- 結果：重複計算

-- ✅ Subquery 方案
SELECT oc.id, DetailInfo.total_amount
FROM one_campaigns oc
LEFT JOIN (
    SELECT pc.one_campaign_id, SUM(pcd.amount) AS total_amount
    FROM pre_campaign pc
    LEFT JOIN pre_campaign_detail pcd ON pc.id = pcd.pre_campaign_id
    GROUP BY pc.one_campaign_id
) DetailInfo ON oc.id = DetailInfo.one_campaign_id
```

### 問題 2: GROUP_CONCAT 超時

**症狀**:
```
"error": "Query execution was interrupted, max_execution_time exceeded"
```

**原因**:
```sql
-- GROUP_CONCAT(DISTINCT ...) 在大數據集上非常慢
GROUP_CONCAT(DISTINCT description SEPARATOR '; ')
-- 每行都要檢查 DISTINCT，性能 O(n²)
```

**解決方案**:

```sql
-- ✅ 方案 A：若資料已唯一，移除 DISTINCT
GROUP_CONCAT(description SEPARATOR '; ')

-- ✅ 方案 B：先去重再 CONCAT
GROUP_CONCAT(DISTINCT target_id SEPARATOR '; ') AS targets
-- 若 target_id 已是 PK，DISTINCT 無意義

-- ✅ 方案 C：LIMIT 結果集大小
GROUP_CONCAT(DISTINCT description SEPARATOR '; ' LIMIT 100)
```

### 問題 3: 多次重複的子查詢掃描

**症狀**:
```
查詢用時 20 秒，但資料量不大
多個 "Table access" 針對同一個表
```

**原因**:
```sql
-- 掃描 pre_campaign 三次
SELECT
    oc.id,
    (SELECT COUNT(*) FROM pre_campaign WHERE one_campaign_id = oc.id) AS cnt,
    (SELECT SUM(budget) FROM pre_campaign WHERE one_campaign_id = oc.id) AS total,
    (SELECT GROUP_CONCAT(...) FROM pre_campaign WHERE one_campaign_id = oc.id)
FROM one_campaigns oc
```

**解決方案**:

```sql
-- ✅ 一次掃描，多個聚合
SELECT
    oc.id,
    PreInfo.cnt,
    PreInfo.total,
    PreInfo.formats
FROM one_campaigns oc
LEFT JOIN (
    SELECT
        one_campaign_id,
        COUNT(*) AS cnt,
        SUM(budget) AS total,
        GROUP_CONCAT(format) AS formats
    FROM pre_campaign
    GROUP BY one_campaign_id
) PreInfo ON oc.id = PreInfo.one_campaign_id
```

---

## 🔧 實用 SQL 調試命令

### 1. 查看查詢執行計畫

```sql
EXPLAIN FORMAT=JSON
SELECT ... FROM ...
```

返回結構化的執行計畫，容易程序化分析。

### 2. 查看索引統計

```sql
-- 查看索引是否存在
SHOW INDEX FROM table_name;

-- 查看特定索引的統計
ANALYZE TABLE table_name;
SHOW STATS FOR TABLE table_name;
```

### 3. 測試執行時間

```sql
-- MySQL 8.0+ 支援
SELECT SQL_NO_CACHE ... FROM ...

-- 查看查詢統計
SHOW SESSION STATUS LIKE 'Handler%';
```

### 4. 檢查表 Lock 和統計信息

```sql
-- 表是否被鎖定
SHOW PROCESSLIST;

-- 更新統計信息
ANALYZE TABLE table_name;
OPTIMIZE TABLE table_name;
```

---

## 📈 性能基準測試

### 設置測試環境

```sql
-- 清空 query cache
RESET QUERY CACHE;

-- 禁用 query cache（測試真實性能）
SET SESSION query_cache_type = OFF;

-- 記錄執行時間
SET PROFILING = 1;
SELECT ... FROM ...;
SHOW PROFILES;
```

### 對比優化前後

```python
# 運行優化前的 SQL
before_time = measure_query_time(unoptimized_sql)

# 運行優化後的 SQL
after_time = measure_query_time(optimized_sql)

# 計算改進百分比
improvement = (before_time - after_time) / before_time * 100
print(f"性能改進: {improvement:.1f}%")
```

---

## 🎯 優化檢查清單（再次提醒）

在應用以上解決方案時，參考快速檢查清單：

### 查詢結構
- [ ] 條件前推：WHERE 子句中的過濾在 JOIN 之前執行
- [ ] Subquery：避免 Cartesian Product，使用子查詢預聚合
- [ ] 無函式：WHERE 條件中無 DATE()、UPPER() 等
- [ ] 型別一致：所有 JOIN 欄位型別和 unsigned 設定一致

### 聚合操作
- [ ] 無重複 DISTINCT：只在必要時使用
- [ ] 單次掃描：相關聚合在同一個 GROUP BY 中完成
- [ ] LIMIT 合理：GROUP_CONCAT 有適當的 LIMIT

### 索引使用
- [ ] EXPLAIN 檢查：access_type 不是 ALL
- [ ] 無 filesort："Using filesort" 不應出現
- [ ] 索引被使用：key 不應為 NULL

### 執行性能
- [ ] 時間目標：< 5 秒為目標
- [ ] 行掃描：不應超過結果集的 100 倍

---

## 🚀 進階優化技巧

### 1. 使用物化視圖（如果支援）

```sql
-- 預計算常用的聚合結果
CREATE MATERIALIZED VIEW campaign_summary AS
SELECT
    one_campaign_id,
    SUM(budget) AS total_budget,
    COUNT(*) AS execution_count,
    GROUP_CONCAT(format) AS formats
FROM pre_campaign
GROUP BY one_campaign_id;

-- 查詢時直接使用物化視圖
SELECT oc.*, cs.* FROM one_campaigns oc
LEFT JOIN campaign_summary cs ON oc.id = cs.one_campaign_id;
```

### 2. 分區表（針對超大表）

```sql
-- 按日期分區 pre_campaign
ALTER TABLE pre_campaign
PARTITION BY RANGE (YEAR(created_at)) (
    PARTITION p2023 VALUES LESS THAN (2024),
    PARTITION p2024 VALUES LESS THAN (2025),
    PARTITION p2025 VALUES LESS THAN MAXVALUE
);
```

### 3. 查詢快取（有限場景）

```sql
-- 對於不經常變化的查詢，啟用快取
SELECT SQL_CACHE ... FROM ...

-- 定期更新快取
RESET QUERY CACHE;
```

---

## 📞 需要幫助？

如果優化後仍然緩慢：

1. **保存 EXPLAIN 輸出**：提供完整的 EXPLAIN FORMAT=JSON 結果
2. **記錄執行統計**：執行時間、掃描行數、返回行數
3. **提供表結構**：DESCRIBE table_name 的輸出
4. **數據量估計**：各表的行數和大小

使用這些信息可以進一步診斷根本原因。

---

## 🔗 參考資源

- [MySQL EXPLAIN 完整指南](https://dev.mysql.com/doc/refman/8.0/en/explain.html)
- [MySQL 索引優化](https://dev.mysql.com/doc/refman/8.0/en/optimization-indexes.html)
- [查詢優化最佳實踐](https://dev.mysql.com/doc/refman/8.0/en/select-optimization.html)
- [使用 EXPLAIN 分析](https://dev.mysql.com/doc/refman/8.0/en/using-explain.html)
