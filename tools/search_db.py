from typing import List
from langchain.tools import tool
from config.database import db


@tool
def search_ambiguous_term(keyword: str) -> List[dict]:
    """
    跨欄位搜尋模糊詞，並回傳 [值, 來源欄位, 過濾器類型] 的對照表。
    """
    candidates = []

    # 定義要搜的目標欄位
    search_targets = [
        {"col": "品牌", "table": "cuelist", "type": "brands"},
        {"col": "品牌廣告主", "table": "cuelist", "type": "brands"}, # 歸類為 Brand
        {"col": "廣告案件名稱(campaign_name)", "table": "cuelist", "type": "campaign_names"} # 歸類為 Campaign Name
    ]

    for target in search_targets:
        try:
            # 執行 SQL LIKE 搜尋
            query = f"SELECT DISTINCT `{target['col']}` FROM `{target['table']}` WHERE `{target['col']}` LIKE '%%{keyword}%%' LIMIT 3"
            # 假設 db.run 直接回傳 list of strings
            results = db.run(query)

            # db.run 可能回傳一個表示 list 的字串，例如 "['val1', 'val2']"
            # 我們需要安全地解析它
            if isinstance(results, str):
                try:
                    # 使用 ast.literal_eval 安全解析字串
                    import ast
                    parsed_results = ast.literal_eval(results)
                    if isinstance(parsed_results, list):
                        results = parsed_results
                    else:
                        # 如果解析出來不是 list，當作單一元素的 list
                        results = [str(parsed_results)]
                except (ValueError, SyntaxError):
                    # 如果解析失敗，當作單一元素的 list
                    results = [results]

            if not isinstance(results, list):
                results = [str(results)]


            for val in results:
                candidates.append({
                    "value": val,           # e.g., "3D造型悠遊卡FB貼文廣宣"
                    "source_col": target['col'], # e.g., "廣告案件名稱(campaign_name)"
                    "filter_type": target['type'] # 告訴 Agent 這是屬於哪種 filter (brands 或 campaign_names)
                })
        except Exception:
            # 如果查詢失敗，跳過這個 target
            continue

    return candidates
