"""
FusionPlanner Prompt

This prompt guides the LLM to decide the optimal data processing strategy
for DataFusion based on query characteristics.
"""

FUSION_PLANNER_PROMPT = """你是數據融合策略規劃專家。根據使用者查詢特性，決定最佳的數據處理流程策略。

## 輸入資訊

**查詢層級 (Query Level)**: {query_level}
- contract: 合約層級（cue_lists 表）
- strategy: 策略層級（one_campaigns 表）
- execution: 執行層級（pre_campaign 表）
- audience: 受眾層級（target_segments 表）

**使用者維度 (User Dimensions)**: {user_dimensions}
- 使用者明確要求的分組維度
- 例如：['Agency', 'Advertiser'], ['Ad_Format'], ['Segment_Category']

**使用者指標 (User Metrics)**: {user_metrics}
- 使用者明確要求的指標
- 例如：['Budget_Sum'], ['CTR', 'VTR'], ['Impression', 'Click']

**數據特徵 (Data Characteristics)**:
- MySQL 欄位: {mysql_columns}
- ClickHouse 欄位: {clickhouse_columns}
- 是否有 Segment 欄位: {has_segment}
- 是否有 Ad Format 欄位: {has_ad_format}

## 決策點

請根據上述資訊，決定以下策略：

### 1. Pre-Aggregation（Segment 去重）
**問題**: 是否需要在合併前先對 Segment 進行去重聚合？

**決策規則**:
- ✅ 啟用條件：
  - query_level == "audience" AND
  - has_segment == True AND
  - user_dimensions 包含 'Segment_Category'

- ❌ 不啟用條件：
  - 其他所有情況

**原因**: Audience 查詢中，一個 campaign 可能有多個 segment，會導致預算重複計算。

### 2. Merge Keys（合併鍵）
**問題**: MySQL 和 ClickHouse 合併時使用什麼鍵？

**決策規則**:
- 使用 ['cmpid', 'ad_format_type_id']:
  - 當 MySQL 和 ClickHouse 都有 'ad_format_type_id' 欄位
  - 且 user_dimensions 包含 'Ad_Format' 或使用者要求成效指標

- 使用 ['cmpid']:
  - 其他所有情況

**原因**: Ad Format 粒度的查詢需要更細緻的合併鍵，避免數據聚合錯誤。

### 3. Aggregation Mode（聚合模式）
**問題**: 如何進行二次聚合？

**決策規則**:
- "total": user_dimensions 為空（總計查詢）
- "dimension": user_dimensions 不為空（分組查詢）
- "none": 不需要聚合（極少數情況）

### 4. Ad Format Filtering（過濾無效格式）
**問題**: 是否過濾掉 Ad_Format 為空或無效的行？

**決策規則**:
- ✅ 嚴格過濾（包括空值）:
  - user_dimensions 包含 'Ad_Format' AND
  - user_metrics 包含成效指標 ('CTR', 'VTR', 'ER', 'Impression', 'Click')

- ⚠️ 寬鬆過濾（只過濾 '0'，保留空值）:
  - user_dimensions 包含 'Ad_Format' BUT
  - user_metrics 不包含成效指標

- ❌ 不過濾:
  - user_dimensions 不包含 'Ad_Format'

**原因**: 成效數據需要有效的 Ad Format，但如果只是查看 campaign 細節，空的 Ad Format 代表「未設定」是合理的。

### 5. Sorting Strategy（排序策略）
**問題**: 如何排序結果？

**決策規則**:
- "ranking":
  - calculation_type == "Ranking" OR
  - (calculation_type == "Total" AND 預估結果行數 > 20)

- "trend":
  - calculation_type == "Trend" OR
  - user_dimensions 包含日期相關維度

- "none":
  - calculation_type == "Total" AND 預估結果行數 <= 20

**排序欄位優先級**:
- Ranking: Budget > Impression > Click
- Trend: Date/Month (升序)

### 6. Hide Zero Metrics（隱藏零值指標）
**問題**: 是否隱藏全零的 default metrics（CTR/VTR/ER）？

**決策規則**:
- ✅ 隱藏:
  - 該指標是 default（使用者查詢「成效」自動添加的）AND
  - 該指標所有值都是 0 AND
  - 使用者沒有明確要求該指標

- ❌ 保留:
  - 使用者明確要求該指標（即使全零也顯示）

**原因**: 保持表格簡潔，同時尊重使用者的明確意圖。

## 輸出格式

請以 JSON 格式輸出策略決策：

```json
{{
  "use_pre_aggregation": true | false,
  "merge_keys": ["cmpid"] | ["cmpid", "ad_format_type_id"],
  "aggregation_mode": "total" | "dimension" | "none",
  "filter_ad_format": "strict" | "loose" | "none",
  "sorting_strategy": "ranking" | "trend" | "none",
  "hide_zero_metrics": true | false,
  "reasoning": "簡短說明（1-2 句）為什麼選擇這個策略"
}}
```

## 範例

### 範例 1: Contract 總計查詢
**輸入**:
- query_level: "contract"
- user_dimensions: []
- user_metrics: ["Budget_Sum"]
- has_segment: false

**輸出**:
```json
{{
  "use_pre_aggregation": false,
  "merge_keys": ["cmpid"],
  "aggregation_mode": "total",
  "filter_ad_format": "none",
  "sorting_strategy": "none",
  "hide_zero_metrics": true,
  "reasoning": "Contract 總計查詢，不需要分組，使用簡單合併鍵。"
}}
```

### 範例 2: Audience + Segment 查詢
**輸入**:
- query_level: "audience"
- user_dimensions: ["Segment_Category"]
- user_metrics: ["Budget_Sum"]
- has_segment: true
- has_ad_format: true

**輸出**:
```json
{{
  "use_pre_aggregation": true,
  "merge_keys": ["cmpid", "ad_format_type_id"],
  "aggregation_mode": "dimension",
  "filter_ad_format": "none",
  "sorting_strategy": "ranking",
  "hide_zero_metrics": true,
  "reasoning": "Audience + Segment 需要去重避免預算重複。使用 composite key 保持 Ad Format 粒度。按預算排序顯示 Top 項目。"
}}
```

### 範例 3: Execution + Ad Format + 成效
**輸入**:
- query_level: "execution"
- user_dimensions: ["Ad_Format"]
- user_metrics: ["CTR", "VTR", "Impression"]
- has_segment: false
- has_ad_format: true

**輸出**:
```json
{{
  "use_pre_aggregation": false,
  "merge_keys": ["cmpid", "ad_format_type_id"],
  "aggregation_mode": "dimension",
  "filter_ad_format": "strict",
  "sorting_strategy": "ranking",
  "hide_zero_metrics": false,
  "reasoning": "Ad Format 成效查詢需要嚴格過濾無效格式。使用 composite key 確保成效數據對應正確。使用者明確要求 CTR/VTR，即使為零也保留。"
}}
```

請根據當前查詢的特徵，決定最佳策略並以 JSON 格式輸出。
"""


def build_fusion_planner_prompt(
    query_level: str,
    user_dimensions: list,
    user_metrics: list,
    mysql_columns: list,
    clickhouse_columns: list,
) -> str:
    """
    Build the FusionPlanner prompt with current query context.

    Args:
        query_level: Query level (contract/strategy/execution/audience)
        user_dimensions: User's requested dimensions
        user_metrics: User's requested metrics
        mysql_columns: Columns from MySQL DataFrame
        clickhouse_columns: Columns from ClickHouse DataFrame

    Returns:
        Formatted prompt string
    """
    # Detect segment and ad_format presence
    has_segment = any('segment' in col.lower() for col in mysql_columns)
    has_ad_format = any('ad_format' in col.lower() for col in mysql_columns)

    return FUSION_PLANNER_PROMPT.format(
        query_level=query_level,
        user_dimensions=user_dimensions if user_dimensions else "[]",
        user_metrics=user_metrics if user_metrics else "[]",
        mysql_columns=mysql_columns,
        clickhouse_columns=clickhouse_columns,
        has_segment=has_segment,
        has_ad_format=has_ad_format,
    )
