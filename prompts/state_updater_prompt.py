from langchain_core.prompts import PromptTemplate

STATE_UPDATER_PROMPT = PromptTemplate.from_template("""
# 任務
使用者從你提供的「候選清單 (Candidates)」中選擇了一個或多個項目。
你的任務是找出使用者選了哪個，並根據候選清單中的 `filter_type` 資訊，將其歸類到正確的過濾欄位。

# 候選清單 (Memory)
{candidate_values}

# 使用者回覆
{user_input}

# 格式化指令
{format_instructions}
""")
