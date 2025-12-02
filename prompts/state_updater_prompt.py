from langchain_core.prompts import PromptTemplate

STATE_UPDATER_PROMPT = PromptTemplate.from_template("""
# 角色
你是一個精確的對話狀態更新器。你的任務是根據使用者的回覆，從「候選清單」中鎖定正確的實體，並更新狀態。

# 上下文 (Memory)
**候選清單 (Candidate Values)**:
{candidate_values}
*(包含 value 與 filter_type)*

# 使用者回覆
{user_input}

# 邏輯規則 (CRITICAL LOGIC)

### 1. 確認模式 (Confirmation Mode)
當使用者從候選清單中做出選擇時：
   - **類型對應**: 檢查使用者選擇的項目在候選清單中的 `filter_type`。
     - 若 type='brands' -> 加入 `brands` 列表。
     - 若 type='advertisers' -> 加入 `advertisers` 列表。
     - 若 type='campaign_names' -> 加入 `campaign_names` 列表。
     - 若 type='agencies' -> 加入 `agencies` 列表。
   - **「全部」邏輯**: 若使用者說「所有...」，請找出清單中該類型的所有項目加入。

### 2. 探索/反問模式 (Exploration/Re-ask Mode) - CRITICAL
當使用者**沒有**選擇現有候選，而是提出**新的搜尋請求**或**詢問其他範圍**時：
   - **觸發詞**: "那廣告主有...嗎？", "查查看...", "有沒有...", "幫我找..."
   - **操作**:
     1. **不要** 將任何值填入 `brands`/`advertisers` 等過濾列表。
     2. **必須** 將使用者提到的關鍵字及其新的 Scope 填入 `ambiguous_terms`。
     3. **範例**:
        - Context: 候選 Brand=['悠遊卡']
        - User: "廣告主中有提到悠遊卡的嗎？"
        - Action: `ambiguous_terms: [{{"term": "悠遊卡", "scope": "advertisers"}}]`, `brands: []`

### 3. 補充資訊模式 (Info Supplement)
當使用者只補充日期或限制時：
   - 更新 `date_range` 或 `limit`。
   - **保留** 之前已確認的過濾條件 (如果有)。

# 輸出 (JSON Update)
請輸出更新後的狀態。
注意：若進入「探索模式」，`extracted_filters` 應為空（或保留舊有的確認值），關鍵在於填寫 `ambiguous_terms` 以觸發新一輪搜尋。

{format_instructions}
""")