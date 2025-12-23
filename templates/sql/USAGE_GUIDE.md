# SQL Template 使用指南

## ✅ 測試結果

所有 8 個 SQL templates 已通過測試並可正常使用：

1. ✅ **campaign_basic.sql** - 活動基本資訊
2. ✅ **ad_formats.sql** - 廣告格式明細
3. ✅ **targeting_segments.sql** - 數據鎖定/受眾標籤
4. ✅ **media_placements.sql** - 投放媒體與版位
5. ✅ **product_lines.sql** - 產品線資訊
6. ✅ **budget_details.sql** - 預算細項
7. ✅ **contract_kpis.sql** - 合約承諾 KPI
8. ✅ **execution_status.sql** - 執行狀態與投放控制

## 🚀 快速開始

### 1. 載入 Template

```python
from pathlib import Path
from jinja2 import Template

def load_template(template_name: str, **params):
    """載入並渲染 Jinja2 template"""
    template_path = Path("templates/sql") / template_name

    with open(template_path, 'r', encoding='utf-8') as f:
        template_content = f.read()

    template = Template(template_content)
    sql = template.render(**params)
    return sql
```

### 2. 執行 Template

```python
from config.database import get_mysql_db
from sqlalchemy import text
import pandas as pd

def execute_template(template_name: str, **params) -> pd.DataFrame:
    """執行 template 並返回 pandas DataFrame"""
    sql = load_template(template_name, **params)

    db = get_mysql_db()
    with db._engine.connect() as conn:
        result = conn.execute(text(sql))
        rows = result.fetchall()
        columns = result.keys()

        df = pd.DataFrame(rows, columns=columns)
        return df
```

### 3. 基本使用範例

```python
# 查詢基本資訊
basic_df = execute_template("campaign_basic.sql")

# 查詢特定客戶
basic_df = execute_template(
    "campaign_basic.sql",
    client_names=["客戶名稱"]
)

# 查詢特定 campaign 的格式
campaign_ids = [12345, 67890]
formats_df = execute_template(
    "ad_formats.sql",
    campaign_ids=campaign_ids
)
```

## 📊 完整工作流程範例

### 範例：查詢「某客戶」的格式、數據鎖定、預算

```python
def analyze_client(client_name: str):
    """分析客戶的活動數據"""

    # Step 1: 取得活動 IDs
    print(f"📌 查詢客戶：{client_name}")
    basic_df = execute_template(
        "campaign_basic.sql",
        client_names=[client_name]
    )

    if len(basic_df) == 0:
        print(f"❌ 找不到客戶 '{client_name}' 的活動")
        return None

    print(f"✅ 找到 {len(basic_df)} 個活動")
    campaign_ids = basic_df['campaign_id'].tolist()

    # Step 2: 查詢格式
    print("\n📌 查詢廣告格式...")
    formats_df = execute_template(
        "ad_formats.sql",
        campaign_ids=campaign_ids
    )
    print(f"✅ 找到 {len(formats_df)} 筆格式數據")

    # Step 3: 查詢數據鎖定
    print("\n📌 查詢數據鎖定...")
    segments_df = execute_template(
        "targeting_segments.sql",
        campaign_ids=campaign_ids
    )
    print(f"✅ 找到 {len(segments_df)} 筆受眾數據")

    # Step 4: 查詢預算
    print("\n📌 查詢預算細節...")
    budget_df = execute_template(
        "budget_details.sql",
        campaign_ids=campaign_ids
    )
    print(f"✅ 找到 {len(budget_df)} 筆預算數據")

    # Step 5: Merge 結果
    print("\n📌 合併數據...")
    result_df = basic_df.copy()

    # Merge formats (一對多，需聚合)
    if len(formats_df) > 0:
        formats_agg = formats_df.groupby('campaign_id').agg({
            'format_name': lambda x: ', '.join(x.unique()),
            'platform': lambda x: ', '.join(x.unique())
        }).reset_index()
        result_df = result_df.merge(formats_agg, on='campaign_id', how='left')

    # Merge segments (一對多，需聚合)
    if len(segments_df) > 0:
        segments_agg = segments_df.groupby('campaign_id').agg({
            'segment_name': lambda x: ', '.join(x.dropna().unique()[:5])  # 最多5個
        }).reset_index()
        result_df = result_df.merge(segments_agg, on='campaign_id', how='left')

    # Merge budget (一對一)
    if len(budget_df) > 0:
        result_df = result_df.merge(budget_df, on='campaign_id', how='left')

    print(f"✅ 合併完成！最終數據: {result_df.shape}")
    return result_df

# 使用
result = analyze_client("某客戶名稱")
if result is not None:
    print(result[['campaign_name', 'format_name', 'segment_name', 'campaign_budget']].head())
```

## 🎯 常見使用情境

### 情境 1: 格式分析

```python
# Agent 需求：「客戶X投遞的格式有哪些？」

def get_ad_formats(client_name: str):
    # 1. 取得 campaign_ids
    basic_df = execute_template(
        "campaign_basic.sql",
        client_names=[client_name]
    )
    campaign_ids = basic_df['campaign_id'].tolist()

    # 2. 查詢格式
    formats_df = execute_template(
        "ad_formats.sql",
        campaign_ids=campaign_ids
    )

    # 3. 聚合結果
    summary = formats_df.groupby('format_name').agg({
        'campaign_id': 'count',
        'platform': lambda x: ', '.join(x.unique())
    }).rename(columns={'campaign_id': 'campaign_count'})

    return summary
```

### 情境 2: 預算分析

```python
# Agent 需求：「客戶X的總預算是多少？各層級預算分布？」

def analyze_budget(client_name: str):
    # 1. 取得 campaign_ids
    basic_df = execute_template(
        "campaign_basic.sql",
        client_names=[client_name]
    )
    campaign_ids = basic_df['campaign_id'].tolist()

    # 2. 查詢預算
    budget_df = execute_template(
        "budget_details.sql",
        campaign_ids=campaign_ids
    )

    # 3. 計算總額
    total_contract = budget_df['contract_total_budget'].sum()
    total_campaign = budget_df['campaign_budget'].sum()
    total_execution = budget_df['execution_total_budget'].sum()

    return {
        'L1_合約總預算': total_contract,
        'L2_活動預算': total_campaign,
        'L3_執行預算': total_execution
    }
```

### 情境 3: KPI 達成分析

```python
# Agent 需求：「客戶X的成效承諾是什麼？」

def get_kpi_commitments(client_name: str):
    # 1. 取得 campaign_ids
    basic_df = execute_template(
        "campaign_basic.sql",
        client_names=[client_name]
    )
    campaign_ids = basic_df['campaign_id'].tolist()

    # 2. 查詢 KPI
    kpi_df = execute_template(
        "contract_kpis.sql",
        campaign_ids=campaign_ids
    )

    # 3. Merge campaign name
    result = kpi_df.merge(
        basic_df[['campaign_id', 'campaign_name']],
        on='campaign_id',
        how='left'
    )

    return result[['campaign_name', 'format_name',
                   'ctr_lower_bound', 'ctr_upper_bound',
                   'vtr_lower_bound', 'vtr_upper_bound']]
```

## 🔧 Agent 整合指南

### 在 Agent 中使用

```python
# nodes/data_analyst.py

class DataAnalystNode:
    def __init__(self):
        self.template_loader = TemplateLoader()

    def execute(self, state):
        """根據 supervisor payload 執行 templates"""

        # 從 state 取得需要的 templates
        required_templates = state['supervisor_payload']['templates']
        campaign_ids = state.get('campaign_ids')

        # 執行所有 templates
        results = {}
        for template_name in required_templates:
            df = execute_template(
                template_name,
                campaign_ids=campaign_ids
            )
            results[template_name] = df

        # Merge 結果
        final_df = self.merge_results(results)

        # 更新 state
        state['final_dataframe'] = final_df
        return state

    def merge_results(self, results: dict) -> pd.DataFrame:
        """智能 merge 多個 DataFrame"""
        if 'campaign_basic.sql' not in results:
            raise ValueError("campaign_basic.sql is required")

        base_df = results['campaign_basic.sql']

        for template_name, df in results.items():
            if template_name == 'campaign_basic.sql':
                continue

            # 判斷是否一對多關係
            if template_name in ['targeting_segments.sql', 'ad_formats.sql']:
                # 需要聚合
                # ... (聚合邏輯)
                pass
            else:
                # 直接 merge
                base_df = base_df.merge(df, on='campaign_id', how='left')

        return base_df
```

## ⚠️ 注意事項

### 1. 一對多關係處理

某些 templates 會返回一對多的結果：
- `ad_formats.sql` - 一個 campaign 可能有多個格式
- `targeting_segments.sql` - 一個 campaign 可能有多個受眾標籤
- `media_placements.sql` - 一個 campaign 可能有多個版位

**處理方式：**
```python
# 方案 1: 聚合為字串
segments_agg = segments_df.groupby('campaign_id').agg({
    'segment_name': lambda x: ', '.join(x.unique())
})

# 方案 2: 保留明細，不 merge
# 讓 agent 直接使用明細數據進行分析
```

### 2. 預算層級不可混淆

- L1 (Contract): `contract_total_budget` - 合約總金額
- L2 (Campaign): `campaign_budget` - 活動分配預算
- L3 (Execution): `execution_total_budget` - 執行層級預算

**不可直接加總！** 因為存在預算池、贈送預算等複雜邏輯。

### 3. NULL 值處理

部分欄位可能為 NULL（如 `segment_name`, `format_name`），需要適當處理：
```python
# 填充 NULL
df['segment_name'].fillna('未設定受眾', inplace=True)

# 過濾 NULL
df_filtered = df[df['segment_name'].notna()]
```

## 📈 性能優化

### 1. 限制返回數量

所有 templates 已內建 `LIMIT 100`，避免一次返回過多數據。

### 2. 並行執行

如果需要執行多個獨立的 templates，可以並行執行：
```python
from concurrent.futures import ThreadPoolExecutor

def execute_templates_parallel(template_list, params):
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(execute_template, t, **params): t
            for t in template_list
        }
        results = {futures[f]: f.result() for f in futures}
    return results
```

### 3. 只取需要的欄位

在 merge 前先選擇需要的欄位：
```python
formats_df_lite = formats_df[['campaign_id', 'format_name', 'platform']]
```

## 🧪 測試命令

```bash
# 測試所有 templates 語法
python test_templates.py

# 測試 agent 執行邏輯
python test_agent_templates.py
```

## 📚 參考文檔

- [README.md](./README.md) - Template 功能說明
- [template_index.yaml](./template_index.yaml) - Template 元數據與選擇邏輯
- MySQL Schema: `/docs/mysql_schema_context.md`

---

**最後更新**: 2025-12-23
**測試狀態**: ✅ 全部通過 (8/8)
