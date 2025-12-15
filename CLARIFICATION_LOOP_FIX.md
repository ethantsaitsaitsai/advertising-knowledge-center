# 澄清訊息無限迴圈修復方案

## 🔴 問題描述

當系統發現查詢模糊時，會進入 Supervisor 和 CampaignAgent 之間的無限迴圈：

```
User: "悠遊卡 投遞的格式、成效、數據鎖定 格式投資金額"
  ↓
IntentAnalyzer: is_ambiguous=True (找到多個悠遊卡相關項目)
  ↓
Supervisor: "請詢問使用者想查詢哪個活動"
  ↓
CampaignAgent: ❌ 執行了 SQL 查詢而不是返回澄清訊息
  ↓
Supervisor: 看到 is_ambiguous 仍為 True，再次要求澄清
  ↓
CampaignAgent: 再次執行 SQL
  ↓
[無限迴圈]
```

## 🔍 根本原因

**CampaignAgent 的 Router 沒有正確偵測澄清請求**：

1. **Supervisor 發送的指令**：
   - 「請詢問使用者想查詢的具體活動名稱」
   - 「根據使用者提供的關鍵字，找出最相關的活動」
   - 包含「詢問」、「具體」等關鍵字

2. **Router 的檢測邏輯**（修復前）：
   ```python
   is_clarification_request = any(keyword in instruction_text.lower()
       for keyword in ["澄清", "clarify", "選擇", "choose"])
   ```
   - 只檢查有限的關鍵字
   - 不檢查 `is_ambiguous` 標記
   - 導致 Supervisor 的澄清指令沒被識別

## ✅ 修復方案

### 1. 添加 is_ambiguous 標記到 CampaignTask (Commit: bd6f320)

**檔案**: `schemas/agent_tasks.py`

```python
class CampaignTask(BaseModel):
    ...
    is_ambiguous: Optional[bool] = Field(
        False,
        description="Whether the user intent is ambiguous and requires clarification."
    )
```

**為什麼**：讓 Router 能直接從 Task 中檢查是否需要澄清，不僅依賴指令文字。

### 2. 強化 Router 的澄清偵測 (Commit: bd6f320)

**檔案**: `nodes/campaign_subgraph/router.py`

```python
# 原始邏輯（不完整）
is_clarification_request = task.instruction_text and any(
    keyword in task.instruction_text.lower()
    for keyword in ["澄清", "clarify", "選擇", "choose", "哪一個", "which one"]
)

# 改進後（多層次檢測）
if task.instruction_text:
    instruction_lower = task.instruction_text.lower()

    # Level 1：原始關鍵字
    if any(keyword in instruction_lower
           for keyword in ["澄清", "clarify", "選擇", "choose", "哪一個", "which one"]):
        is_clarification_request = True

    # Level 2：強澄清指標
    elif any(keyword in instruction_lower
             for keyword in ["詢問", "ask", "問", "list", "列出", "options", "具體"]):
        is_clarification_request = True

# Level 3：【最關鍵】檢查 is_ambiguous 標記
if hasattr(task, 'is_ambiguous') and task.is_ambiguous:
    print("DEBUG: is_ambiguous=True -> treating as clarification")
    is_clarification_request = True
```

**為什麼**：
- 多層次檢測提高準確度
- `is_ambiguous=True` 是最明確的澄清信號
- Router 無法執行忽略的檢測

### 3. 傳遞 is_ambiguous 到 CampaignTask (Commit: bd6f320)

**檔案**: `nodes/supervisor_subgraph/validator.py`

```python
if user_intent:
    decision_payload["is_ambiguous"] = user_intent.is_ambiguous
```

**為什麼**：確保 is_ambiguous 標記在整個流程中傳播，從 IntentAnalyzer → Supervisor → CampaignAgent。

### 4. 添加調試日誌 (Commit: 247288d)

**檔案**: `nodes/campaign_node_wrapper.py`

```python
print(f"DEBUG [CampaignNode] is_ambiguous: {task.is_ambiguous}")
```

**為什麼**：提供可見性，方便診斷旗幟是否正確傳播。

---

## 📊 修復後的流程

```
User: "悠遊卡 投遞的格式、成效、數據鎖定 格式投資金額"
  ↓
IntentAnalyzer
  ├─ 搜尋 "悠遊卡" → 10 個結果
  ├─ 設置 is_ambiguous = True ✅
  └─ 要求澄清
  ↓
Supervisor
  ├─ 看到 is_ambiguous = True
  ├─ 生成澄清指令
  └─ 傳遞 is_ambiguous = True 到 CampaignTask
  ↓
CampaignAgent
  ├─ 接收 task.is_ambiguous = True ✅
  ├─ Router 檢測：
  │   ├─ 指令文字包含「詢問」、「具體」等 ✅
  │   ├─ is_ambiguous = True ✅
  │   └─ 是澄清請求！
  └─ 返回澄清訊息（不執行 SQL）✅
  ↓
ResponseSynthesizer
  ├─ 檢測到 name="CampaignAgent"
  ├─ 傳遞澄清訊息給使用者
  └─ 設置 clarification_pending = True
  ↓
User 看到清楚的澄清訊息，輸入回答
  ↓
User Response: "我要查詢品牌部分的悠遊卡"
  ↓
Supervisor (下次迭代)
  ├─ 檢測 clarification_pending = True
  ├─ 看到最後訊息是 HumanMessage
  └─ 路由回 IntentAnalyzer
  ↓
IntentAnalyzer (重新分析)
  ├─ 解析使用者回答
  ├─ 提取「品牌部分的悠遊卡」
  ├─ 搜尋驗證
  └─ 設置 is_ambiguous = False ✅
  ↓
Supervisor (下次迭代)
  ├─ 看到 is_ambiguous = False ✅
  ├─ 允許執行 SQL
  └─ 正常查詢
  ↓
最終結果 ✅
```

---

## 🔧 驗證修復

### 1. 檢查 is_ambiguous 傳播

在 debug 日誌中查看：
```
DEBUG [CampaignNode] is_ambiguous: True  ← 應該看到這個
DEBUG [CampaignRouter] Logic: Clarification request detected
```

### 2. 檢查澄清訊息返回

查詢模糊時，應該看到：
```
DEBUG [CampaignRouter] is_ambiguous=True in task -> treating as clarification request
DEBUG [CampaignRouter] Logic: Clarification request detected -> FINISH
```

不應該看到：
```
DEBUG [CampaignExecutor] Executing: SELECT ...  ← 這表示執行了 SQL
```

### 3. 測試完整流程

```
1️⃣ 提出模糊查詢
   → 應看到澄清訊息（不是 SQL 結果）

2️⃣ 回答澄清問題
   → 應看到實際查詢結果

3️⃣ 不應該無限迴圈
```

---

## 🎯 關鍵改進

| 改進點 | 效果 |
|------|------|
| **is_ambiguous 標記** | 明確信號，不依賴字串匹配 |
| **多層檢測** | 關鍵字 + 旗幟 + 指令分析 |
| **完整傳播** | IntentAnalyzer → Supervisor → CampaignAgent |
| **調試日誌** | 可診斷旗幟流轉 |

---

## 📝 Commits

- `bd6f320`: 主要修復（is_ambiguous 標記、Router 強化、Validator 傳播）
- `247288d`: 調試日誌增強

---

## 🚀 後續驗證

建議執行以下測試案例：

### Test Case 1：澄清訊息正確返回
```
Input: "悠遊卡 成效"
Expected: 澄清訊息列出 5 個選項
Not Expected: SQL 結果
```

### Test Case 2：澄清回答正確處理
```
Input: "我要查詢品牌部分的悠遊卡"
Expected: 返回悠遊卡品牌的成效數據
Not Expected: 無限迴圈或重複澄清
```

### Test Case 3：單一結果直通
```
Input: "Nike 成效"（假設只有 1 個 Nike）
Expected: 直接返回結果
Not Expected: 澄清訊息
```

---

## 💡 設計思想

修復遵循「**分層防禦**」原則：

1. **第一層**（IntentAnalyzer）：設置 is_ambiguous 旗幟
2. **第二層**（Supervisor）：傳播旗幟到下一層
3. **第三層**（CampaignAgent Router）：
   - 檢查旗幟（最可靠）
   - 檢查指令關鍵字（次要）
   - 依賴字串匹配（最弱）

即使某一層檢測失敗，其他層也能捕捉澄清請求，防止迴圈。
