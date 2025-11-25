from schemas.state import AgentState
from config.llm import llm
from prompts.clickhouse_generator_prompt import CLICKHOUSE_GENERATOR_PROMPT
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from datetime import datetime, timedelta
import re


def clean_sql_output(response: str) -> str:
    """
    A robust function to clean the SQL output from the LLM, following the established pattern in sql_generator.
    It handles markdown blocks, prefixes, and invalid responses.
    """
    # 1. Attempt to extract Markdown code block (```sql ... ```)
    sql_match = re.search(r"```sql(.*?)```", response, re.DOTALL | re.IGNORECASE)
    if sql_match:
        return sql_match.group(1).strip()

    # 2. If not found, try to extract a generic Markdown block (``` ... ```)
    plain_match = re.search(r"```(.*?)```", response, re.DOTALL)
    if plain_match:
        return plain_match.group(1).strip()

    # 3. If no Markdown, find the first "SELECT" and take everything after it.
    select_index = response.upper().find("SELECT")
    if select_index != -1:
        return response[select_index:].strip()
        
    # 4. If "SELECT" is not found at all, return an empty string for safety.
    return ""


def clickhouse_generator_node(state: AgentState) -> dict:
    """
    Generates a ClickHouse SQL query with optimized Partition Pruning logic.
    It builds a specific date range for EACH cmpid to avoid full-table scans.
    Includes robust regex handling to prevent syntax errors like duplicate GROUP BY.
    """
    sql_result = state.get("sql_result")
    sql_result_columns = state.get("sql_result_columns")

    if not sql_result or not sql_result_columns:
        return {"clickhouse_sql": ""}

    # 1. 嘗試解析 MySQL 結果中的 ID 與日期
    has_dates = False
    idx_cmpid = -1
    idx_start = -1
    idx_end = -1
    
    try:
        idx_cmpid = sql_result_columns.index("cmpid")
        # 嘗試尋找可能的開始/結束日期欄位名稱 (根據你的資料庫實際欄位調整)
        try:
            # 常見命名慣例，請確認你的 MySQL 實際回傳名稱
            idx_start = next(i for i, col in enumerate(sql_result_columns) if col in ["start_date", "start_time", "campaign_start"])
            idx_end = next(i for i, col in enumerate(sql_result_columns) if col in ["end_date", "end_time", "campaign_end"])
            has_dates = True
        except StopIteration:
            has_dates = False
            
    except (ValueError, IndexError):
        # cmpid 欄位都沒找到，直接返回
        return {"clickhouse_sql": ""}

    # 2. 準備 cmpid 列表與全域日期
    cmpid_list = [row[idx_cmpid] for row in sql_result if idx_cmpid != -1 and row[idx_cmpid] is not None]
    if not cmpid_list:
        return {"clickhouse_sql": ""}
    
    cmpid_list_str = ", ".join(map(str, set(cmpid_list))) # Use set to remove duplicates

    # 3. 準備全域日期 (給 Prompt 作為備案，或者用於沒有個別日期的情況)
    filters = state.get("extracted_filters", {})
    global_start = filters.get("date_start")
    global_end = filters.get("date_end")

    if not global_start or not global_end:
        today = datetime.now()
        global_end = today.strftime("%Y-%m-%d")
        global_start = (today - timedelta(days=7)).strftime("%Y-%m-%d")

    # 4. 呼叫 LLM 生成初始 SQL
    # 我們讓 LLM 產生一個標準的 SQL，稍後再用 Python 替換掉 WHERE 子句
    prompt = PromptTemplate.from_template(CLICKHOUSE_GENERATOR_PROMPT)
    chain = prompt | llm | StrOutputParser()

    # 這裡傳入 global dates 和 cmpid_list_str，讓 LLM 產生一個格式正確的 SQL
    response = chain.invoke({
        "cmpid_list": cmpid_list_str,
        "date_start": global_start,
        "date_end": global_end
    })

    # 5. 清理 LLM 輸出 (使用我們現有的 robust 函式)
    raw_sql = clean_sql_output(response)
    if not raw_sql:
        return {"clickhouse_sql": ""}

    # =========================================================================
    # 6. [關鍵優化] Partition Pruning - 動態替換 WHERE 子句
    # =========================================================================
    final_sql = raw_sql
    
    if has_dates:
        # 構建精準的條件: (cmpid=1 AND day_local BETWEEN '...' AND '...') OR (...)
        or_clauses = []
        for row in sql_result:
            c_id = row[idx_cmpid]
            s_date = row[idx_start]
            e_date = row[idx_end]

            # 資料清洗與防呆
            if not s_date: s_date = global_start
            if not e_date: e_date = global_end
            
            # 確保是字串格式 (如果是 datetime 物件轉字串)
            if isinstance(s_date, datetime): s_date = s_date.strftime("%Y-%m-%d")
            if isinstance(e_date, datetime): e_date = e_date.strftime("%Y-%m-%d")

            or_clauses.append(f"(`cmpid` = {c_id} AND `day_local` BETWEEN '{s_date}' AND '{e_date}')")
        
        if or_clauses:
            optimized_where = " OR ".join(or_clauses)
            
            # 使用 Lookahead Regex 找出 WHERE 子句的邊界，但不消耗後面的關鍵字
            # 匹配：從 WHERE 開始，直到遇到 GROUP BY, ORDER BY, LIMIT, HAVING 或 字串結束
            where_pattern = r"(WHERE\s+.*?)(?=\s+(?:GROUP\s+BY|ORDER\s+BY|LIMIT|HAVING)|$)"
            
            match = re.search(where_pattern, final_sql, re.DOTALL | re.IGNORECASE)
            
            if match:
                # 替換既有的 WHERE
                # 使用切片 (Slicing) 重組字串，避免 replace 造成的全域替換風險
                start_idx = match.start()
                end_idx = match.end()
                final_sql = final_sql[:start_idx] + f"WHERE ({optimized_where})" + final_sql[end_idx:]
            else:
                # 如果原本沒有 WHERE，則插入到第一個關鍵字之前
                keyword_pattern = r"(?=\s+(?:GROUP\s+BY|ORDER\s+BY|LIMIT|HAVING))"
                split_match = re.search(keyword_pattern, final_sql, re.IGNORECASE)
                if split_match:
                     insert_pos = split_match.start()
                     final_sql = final_sql[:insert_pos] + f"\nWHERE ({optimized_where}) " + final_sql[insert_pos:]
                else:
                     # 什麼關鍵字都沒找到，直接加在最後
                     final_sql = final_sql + f"\nWHERE ({optimized_where})"
                
    # 6. [最後防線] 清理語法錯誤 (Safety Cleanup)
    # 強制移除可能因拼接產生的重複關鍵字
    final_sql = re.sub(r"GROUP\s+BY\s+GROUP\s+BY", "GROUP BY", final_sql, flags=re.IGNORECASE | re.DOTALL)
    final_sql = re.sub(r"WHERE\s+WHERE", "WHERE", final_sql, flags=re.IGNORECASE | re.DOTALL)
    
    # 清理多餘空行
    final_sql = re.sub(r"\n\s*\n", "\n", final_sql).strip()

    return {"clickhouse_sql": final_sql}