from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.messages import AIMessage
from schemas.state import AgentState
from config.llm import llm
from typing import Dict, Any
from collections import defaultdict

# Define the new, more powerful prompt for asking for clarification
ASK_FOR_CLARIFICATION_PROMPT = """
# 角色
你是一位友善且精確的數據助理。你的任務是透過與使用者對話，來澄清他模糊的查詢，確保最終的 SQL 查詢是百分之百正確的。

# 情境
使用者的查詢 "{ambiguous_terms_str}" 比較模糊。經過資料庫搜尋，我們在不同的欄位中找到了以下幾個相關的可能項目：

{formatted_candidates}

同時，我們可能還缺少以下必要的查詢資訊：
{missing_slots}

# 任務
根據以上資訊，生成一個自然、簡潔、且有禮貌的問句，引導使用者完成選擇。

# 指示
1.  **優先處理候選項目**：如果 `formatted_candidates` 有內容，請務必清晰地展示給使用者看，並詢問他們想要查詢的是哪一個或哪幾個。
2.  **引導式提問**：你的問題應該是引導式的，例如：「請問您是指特定專案，還是所有與該品牌相關的資料？」
3.  **處理缺少資訊**：如果 `missing_slots`  أيضاً有內容，請在同一個問句中一併提出。
4.  **語言**：請務必使用繁體中文。

# 範例
"根據您提到的「悠遊卡」，我在資料庫中找到了幾個相關項目：
- 在「品牌廣告主」中，找到了：悠遊卡公司
- 在「廣告案件」中，找到了：2024悠遊卡專案

請問您是想查詢「2024悠遊卡專案」的數據，還是所有「悠遊卡公司」的資料呢？"
"""


def ask_for_clarification_node(state: AgentState) -> Dict[str, Any]:
    """
    When the user's query is incomplete or ambiguous, this node generates follow-up questions
    by formatting structured candidates and presenting them to the user.
    """
    missing_slots = state.get("missing_slots", [])
    ambiguous_terms = state.get("ambiguous_terms", []) # List[ScopedTerm] or List[str]
    candidate_values = state.get("candidate_values", [])

    # Format ambiguous terms for display
    term_strs = []
    for t in ambiguous_terms:
        if isinstance(t, str):
            term_strs.append(f"「{t}")
        elif hasattr(t, 'term'): # ScopedTerm object
            term_strs.append(f"「{t.term}")
        elif isinstance(t, dict): # ScopedTerm as dict
            term_strs.append(f"「{t.get('term')}")
            
    ambiguous_terms_str = ", ".join(term_strs) if term_strs else "不明確的詞彙"

    # If no candidates or missing slots, something is wrong, but have a fallback.
    if not candidate_values and not missing_slots:
        # Fallback: check if we still have ambiguous terms that yielded no candidates
        if ambiguous_terms_str: # Use the formatted string for check
             return {
                "messages": [AIMessage(content=f"關於{ambiguous_terms_str}，我在資料庫中找不到相關資料。請問您是指品牌、代理商還是其他項目？或者您可以提供更準確的名稱。")],
                "expecting_user_clarification": True,
            }
        return {
            "messages": [AIMessage(content="我需要更多資訊，但無法確定要問什麼。可以請您提供更多細節嗎？")],
            "expecting_user_clarification": True,
        }

    # Use a simple prompt for missing slots only if no candidates were found
    if not candidate_values and missing_slots:
        response = f"為了提供準確的數據，請問您想查詢的『{', '.join(missing_slots)}』是？（例如：2024年全年度、上個月、或是具體日期）"
    else:
        # This is the main path for handling structured, ambiguous candidates
        formatted_candidates_str = "暫無相關候選項目。"
        if candidate_values:
            # Group candidates by their source
            grouped_candidates = defaultdict(list)
            for cand in candidate_values:
                # Use a mapping for better display names
                source_display_map = {
                    "brands": "品牌",
                    "advertisers": "品牌廣告主",
                    "campaign_names": "廣告案件名稱",
                    "agencies": "代理商",
                    "industries": "產業",
                    "keywords": "關鍵字"
                }
                # Fallback to raw filter_type if not in map
                ft = cand.get('filter_type', 'unknown')
                source_display = source_display_map.get(ft, ft.replace("_", " ").title())
                grouped_candidates[source_display].append(cand['value'])

            # Format the grouped candidates into a readable string for the prompt
            parts = []
            for source, values in grouped_candidates.items():
                values_str = ", ".join(f"「{v}」" for v in values)
                parts.append(f"- 在「{source}」中，找到了：{values_str}")
            formatted_candidates_str = "\n".join(parts)

        # Use the powerful LLM prompt for the main clarification task
        prompt = PromptTemplate.from_template(ASK_FOR_CLARIFICATION_PROMPT)
        chain = prompt | llm | StrOutputParser()
        response = chain.invoke({
            "ambiguous_terms_str": ambiguous_terms_str,
            "formatted_candidates": formatted_candidates_str,
            "missing_slots": ", ".join(missing_slots) if missing_slots else "無",
        })

    return {
        "messages": [AIMessage(content=response)],
        "expecting_user_clarification": True,
    }