from schemas.state import AgentState
from config.llm import llm
from schemas.search_intent import SearchIntent

SLOT_MANAGER_PROMPT = """
# 角色
你是一位精通 SQL 的廣告數據分析師。
你唯一的任務是將使用者的自然語言查詢轉換為結構化的過濾參數 (SearchIntent)。

# 領域術語表 (Domain Glossary) - 關鍵解釋規則
當使用者提到以下詞彙時，必須依照此規則映射：
- **"格式"**: 指 **廣告格式 (Ad Format)** (如 Video, Banner)，對應 `ad_formats` 欄位。絕非檔案格式。
- **"數據鎖定" / "鎖定"**: 指 **受眾鎖定 (Targeting/Segments)**，對應 `target_segments` 欄位。絕非資料庫鎖。
- **"投資金額" / "預算"**: 映射至 `metrics` 中的 "Budget"。
- **"成效" / "表現"**: 映射至 `metrics` 中的 "Performance"。

# 提取規則
1. **日期處理**: 
   - 若未提及具體時間，務必將 `date_range` 留空，並將 "date_range" 加入 `missing_info`。
   - 支援相對時間轉換 (如 "上個月" -> 計算出具體的 YYYY-MM-DD)。
2. **實體識別**: 
   - 若不確定某個詞是品牌還是產品線，放入 `ambiguous_terms`。
3. **嚴格輸出**: 
   - 僅輸出 JSON，嚴禁廢話。

# 輸入
使用者輸入: {user_input}
"""

def slot_manager_node(state: AgentState):
    """
    Fills slots from the user's query and updates the state with a more structured format.
    """
    last_message = state['messages'][-1]
    user_input = last_message.content if hasattr(last_message, 'content') else last_message['content']
    
    # 綁定新的 Schema
    structured_llm = llm.with_structured_output(SearchIntent)
    
    # 執行提取
    result: SearchIntent = structured_llm.invoke(
        SLOT_MANAGER_PROMPT.format(user_input=user_input)
    )
    
    # 構建更結構化的 State 更新
    # 這裡將 "Raw Slots" 轉換為 "SQL Ready Context"
    return {
        # 將過濾條件集中，方便 SQLGenerator 生成 WHERE 子句
        "extracted_filters": {
            "brands": result.brands,
            "industries": result.industries,
            "ad_formats": result.ad_formats,
            "target_segments": result.target_segments,
            "date_start": result.date_range.start,
            "date_end": result.date_range.end
        },
        
        # 分析需求，方便決定 SELECT 欄位或 Python 分析邏輯
        "analysis_needs": {
            "metrics": result.metrics
        },
        
        # 流程控制用
        "missing_slots": result.missing_info,
        "ambiguous_terms": result.ambiguous_terms
    }


