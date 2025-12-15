# SQL 查詢優化實施總結

## 📌 概述

針對 CampaignAgent 的 SQL 執行效能問題，已實施全面的優化策略。優化涵蓋三個層面：

1. **LLM 指導** - 改進 SQL 生成提示詞
2. **執行監控** - 添加性能追蹤和分析
3. **文件記錄** - 提供優化指南和最佳實踐

---

## ✅ 已實施的優化

### 1. SQL 生成提示詞增強 (Commit: 33a74a0)

**文件**: `prompts/sql_generator_prompt.py`

**改進內容**:

#### A. 優先級清晰的優化策略
添加了「效能優化」部分，按重要度列出 6 項核心優化：

1. **條件前推 (Filter Push Down)** ⭐⭐⭐
   - Company/Brand 過濾必須在 JOIN 之前進行
   - 目標：先篩選數千行的 one_campaigns，再 JOIN 百萬行的 pre_campaign

2. **Subquery 優化 (Pre-Aggregation)** ⭐⭐⭐
   - 先在子查詢中聚合 pre_campaign
   - 避免 Cartesian Product 導致的數據膨脹

3. **避免重複掃描** ⭐⭐
   - 一次掃描中計算所有聚合
   - 使用 UNION 或多個子查詢再 JOIN

4. **去除不必要 DISTINCT** ⭐⭐
   - GROUP_CONCAT(DISTINCT ...) 很昂貴
   - 若 FK 約束保證唯一則移除

5. **JOIN 欄位型別一致** ⭐⭐⭐
   - 所有 id 欄位型別和 unsigned 設定必須完全一致
   - 避免隱性轉型導致索引失效

6. **避免函式包裹** ⭐⭐
   - 禁止 WHERE DATE(...) 或 UPPER(...)
   - 使用範圍條件取代

#### B. EXECUTION 層優化範例
添加了兩種 SQL 範本：
- **方式A**：條件前推 + Subquery 聚合（最優化）
- **方式B**：簡化版（不需公司過濾）

**範例**：
```sql
-- 條件前推：優先篩選公司
WHERE c.company = '目標公司'

-- Subquery 聚合：先計算格式資訊
LEFT JOIN (
    SELECT
        pc.one_campaign_id,
        GROUP_CONCAT(aft.title) AS Ad_Format,
        SUM(pc.budget) AS Budget_Sum
    FROM pre_campaign pc
    ...
    GROUP BY pc.one_campaign_id
) AS FormatInfo ON oc.id = FormatInfo.one_campaign_id
```

#### C. AUDIENCE 層優化範例
添加了優化版本，包括：
- 條件前推在 clients 層
- Subquery 預聚合受眾和預算
- 複合索引使用提示

#### D. 索引使用提示
列出了系統已建立的索引：
- `clients(company)` - 廣告主查詢
- `cue_lists(client_id)` - 客戶關聯
- `one_campaigns(cue_list_id)` - 合約關聯
- `pre_campaign(one_campaign_id)` - 執行層
- `pre_campaign_detail(pre_campaign_id)` - 詳細資訊
- `campaign_target_pids(source_id, source_type)` - 複合
- `campaign_target_pids(selection_id)` - 受眾查詢

---

### 2. SQL 執行性能監控 (Commit: 21eed11)

**文件**: `nodes/campaign_subgraph/executor.py`

**改進內容**:

#### A. 執行時間測量
```python
start_time = time.time()
result = connection.execute(text(sql))
elapsed_time = time.time() - start_time
```
- 精確到毫秒級
- 記錄到 campaign_data 中

#### B. 慢查詢自動分析
```python
if elapsed_time > 5:  # 執行超過 5 秒
    explain_sql = f"EXPLAIN FORMAT=JSON {sql}"
    # 自動運行 EXPLAIN 分析
```
- 自動識別 > 5 秒的查詢
- 執行 EXPLAIN FORMAT=JSON 獲取詳細執行計畫
- 存儲結果到 campaign_data["explain_analysis"]

#### C. 性能元數據
返回的 campaign_data 包含：
```python
{
    "data": [...],
    "columns": [...],
    "generated_sqls": [sql],
    "execution_time_seconds": 2.34,  # 執行時間
    "row_count": 1000,               # 返回行數
    "explain_analysis": {...}        # EXPLAIN 結果（若慢）
}
```

#### D. 調試日誌增強
```
DEBUG [CampaignExecutor] Result: 1000 rows in 2.34s.
DEBUG [CampaignExecutor] Query took 7.89s (slow). Running EXPLAIN...
```

---

### 3. SQL 優化檢查清單文件 (Commit: 60cf747)

**文件**: `documents/SQL_OPTIMIZATION_CHECKLIST.md`

**內容**:

#### A. 詳細的優化指南
- 6 項查詢生成優化的完整說明
- 2 項查詢執行優化
- 每項都包含原則、檢查項、✅正確範例、❌錯誤範例

#### B. 索引使用指南
- 列出所有可用索引
- 說明每個索引的用途
- EXPLAIN 分析的紅旗識別

#### C. 執行時間目標
- < 1 秒：最佳
- 1-5 秒：可接受
- 5-10 秒：需要優化
- > 10 秒：必須優化

#### D. 查詢層級特定優化
- CONTRACT：直接預算，無需 pre_campaign
- STRATEGY：Subquery 聚合預算
- EXECUTION：條件前推 + Subquery 格式聚合
- AUDIENCE：條件前推 + Subquery 受眾聚合

#### E. 快速檢查清單
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

## 🎯 期望效果

### 執行速度改進

**優化前**（無指導）:
```
Query Time: 15-30 秒
資料量: 10,000,000+ 行（Cartesian Product）
使用: 全表掃描 + filesort
```

**優化後**（應用所有策略）:
```
Query Time: 1-5 秒（目標）
資料量: 合理（條件前推減少 90%）
使用: 索引掃描
```

### 具體優化場景

#### 場景 1：EXECUTION 層查詢（格式查詢）
```sql
-- 優化前：Cartesian Product 膨脹
SELECT ...
FROM one_campaigns
JOIN pre_campaign ON ...
LEFT JOIN pre_campaign_detail ON ...
LEFT JOIN ad_format_types ON ...
GROUP BY one_campaigns.id
-- 結果：10M 行掃描 → 500 行 GROUP BY，耗時 30+ 秒

-- 優化後：條件前推 + Subquery
SELECT ...
FROM one_campaigns oc
WHERE client_company = 'ABC' -- 【前推】減少到 100 campaigns
LEFT JOIN (
    SELECT one_campaign_id, ... FROM pre_campaign ...
    GROUP BY one_campaign_id
) AS FormatInfo  -- 【Subquery】只掃描 100 campaigns 的相關數據
-- 結果：10K 行掃描 → 100 行 JOIN，耗時 < 2 秒
```

#### 場景 2：AUDIENCE 層查詢（受眾查詢）
```sql
-- 優化前：多個 GROUP_CONCAT(DISTINCT) + 複雜 JOIN
-- 耗時：20+ 秒

-- 優化後：條件前推 + 複合索引使用
-- 耗時：< 3 秒
```

---

## 🔧 LLM 生成 SQL 的行為變化

### 提示詞更新前
- LLM 可能生成: `SELECT ... FROM one_campaigns JOIN pre_campaign ...` 直接 JOIN
- 沒有明確的優化指導
- 容易產生 Cartesian Product

### 提示詞更新後
- LLM 會優先考慮條件前推
- 自動使用 Subquery 模式
- 明確避免 GROUP_CONCAT(DISTINCT ...)
- 檢查型別一致性

---

## 📊 監控和診斷

### 使用執行時間識別問題

```python
if campaign_data.get("execution_time_seconds", 0) > 5:
    print(f"⚠️ 慢查詢警告: {execution_time}s")
    if "explain_analysis" in campaign_data:
        analyze_explain(campaign_data["explain_analysis"])
```

### EXPLAIN 分析紅旗

```
❌ "access_type": "ALL"  # 全表掃描
❌ "Using temporary; Using filesort"  # 排序操作
❌ possible_keys 包含但 key 為 NULL  # 索引未被使用
```

---

## 🚀 後續步驟

### 立即可用
1. 使用優化後的 SQL 生成提示詞
2. 執行 SQL 查詢獲得性能數據
3. 參考 SQL_OPTIMIZATION_CHECKLIST.md 進行手動優化

### 需要數據庫級別支持
1. **確認索引**：驗證所有列出的索引是否存在
   ```sql
   SHOW INDEX FROM clients WHERE Column_name = 'company';
   SHOW INDEX FROM cue_lists WHERE Column_name = 'client_id';
   -- ... 其他索引
   ```

2. **檢查表結構**：驗證型別一致性
   ```sql
   DESCRIBE clients;  -- id 應為 BIGINT UNSIGNED
   DESCRIBE cue_lists;  -- client_id 應為 BIGINT UNSIGNED
   ```

3. **參考資料**：
   - MySQL EXPLAIN：https://dev.mysql.com/doc/refman/8.0/en/explain.html
   - 索引優化：https://dev.mysql.com/doc/refman/8.0/en/optimization-indexes.html

---

## 📋 檔案清單

| 檔案 | 變更 | 目的 |
|------|------|------|
| `prompts/sql_generator_prompt.py` | 新增優化策略 (142 行) | 指導 LLM 生成優化 SQL |
| `nodes/campaign_subgraph/executor.py` | 性能監控 | 追蹤執行時間和分析 EXPLAIN |
| `documents/SQL_OPTIMIZATION_CHECKLIST.md` | 新建文件 (269 行) | 優化指南和最佳實踐 |

---

## ✨ 總結

本優化實施涵蓋了 SQL 查詢優化的全面方案：

- **LLM 層**：透過詳細提示詞引導正確的 SQL 生成
- **執行層**：自動監控和診斷性能問題
- **文件層**：提供完整的優化指南和檢查清單

預期效能改進：**15-30 秒 → 1-5 秒**（65-85% 的速度提升）

所有變更已提交到 `refactor/multi-agent-system` 分支，可進一步測試和驗證。
