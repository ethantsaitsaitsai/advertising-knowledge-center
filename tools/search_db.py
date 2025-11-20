import ast
from langchain.tools import tool
from config.database import db


def parse_union_result(result: str) -> list[dict]:
    """
    Parses the string representation of a list of tuples from a UNION query.
    Expected input format example: "[('悠遊卡', 'brand'), ('悠遊卡2024', 'campaign_name')]"
    Returns: [{'value': '悠遊卡', 'source': 'brand'}, ...]
    """
    try:
        # 安全地將字串轉換為 Python list of tuples
        raw_list = ast.literal_eval(result)

        parsed_list = []
        # 處理 DB 回傳可能是單個 tuple 或 list of tuples 的情況
        if isinstance(raw_list, tuple):
            parsed_list.append({"value": raw_list[0], "source": raw_list[1]})
        elif isinstance(raw_list, list):
            for item in raw_list:
                if isinstance(item, tuple) and len(item) >= 2:
                    parsed_list.append({"value": item[0], "source": item[1]})

        return parsed_list
    except (ValueError, SyntaxError, IndexError):
        # Fallback: 如果解析失敗，回傳原始字串以便除錯
        return [{"value": result, "source": "unknown"}]


@tool
def search_ambiguous_term(keyword: str, table_name: str = "cuelist") -> list[dict]:
    """
    Searches for the keyword across multiple predefined columns (brand, agency, campaign, etc.)
    and returns the matches along with their source column.

    Args:
        keyword: The term to search for (e.g., "悠遊卡").
        table_name: The table to search in (default: "cuelist").

    Returns:
        A list of dictionaries: [{'value': 'FoundTerm', 'source': 'column_name'}, ...]
    """

    # 定義要搜尋的目標欄位映射 (Display Name -> Actual DB Column Name)
    # 根據您的需求設定這幾個欄位
    search_targets = {
        "brand": "品牌",
        "advertiser": "品牌廣告主",
        "campaign": "廣告案件名稱(campaign_name)",
        "agency": "代理商"
    }

    queries = []

    # 建構 UNION 查詢
    for source_tag, column_col in search_targets.items():
        # 使用 SELECT DISTINCT 避免重複
        # 並選取第二個欄位作為 source_tag (例如 'brand')
        sub_query = f"""
        SELECT DISTINCT `{column_col}`, '{source_tag}'
        FROM `{table_name}`
        WHERE `{column_col}` LIKE '%%{keyword}%%'
        """
        queries.append(sub_query)

    # 合併所有查詢
    final_query = " UNION ".join(queries)

    # 加上總體限制，避免 Token 爆炸 (每個欄位都可能有結果，這裡限制總回傳數)
    final_query += " LIMIT 20;"

    try:
        # 執行 SQL
        result_str = db.run(final_query)
        # 解析結果
        candidates = parse_union_result(result_str)
        if not candidates:
            return []
        return candidates

    except Exception as e:
        return [{"value": f"Search Error: {str(e)}", "source": "error"}]
