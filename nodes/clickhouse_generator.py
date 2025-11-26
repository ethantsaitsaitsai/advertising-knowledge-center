from schemas.state import AgentState
from config.llm import llm
from prompts.clickhouse_generator_prompt import CLICKHOUSE_GENERATOR_PROMPT
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from datetime import datetime, timedelta
import re


def clean_sql_output(response: str) -> str:
    """
    A robust function to clean the SQL output from the LLM.
    """
    sql_match = re.search(r"```sql(.*?)```", response, re.DOTALL | re.IGNORECASE)
    if sql_match:
        return sql_match.group(1).strip()

    plain_match = re.search(r"```(.*?)```", response, re.DOTALL)
    if plain_match:
        return plain_match.group(1).strip()

    select_index = response.upper().find("SELECT")
    if select_index != -1:
        return response[select_index:].strip()

    return ""


def clickhouse_generator_node(state: AgentState) -> dict:
    """
    Generates a ClickHouse SQL query.
    Truncates input data if too large to prevent Prompt overflow.
    Optimized with Partition Pruning logic.
    """
    sql_result = state.get("sql_result")
    sql_result_columns = state.get("sql_result_columns")

    if not sql_result or not sql_result_columns:
        return {"clickhouse_sql": ""}

    # 1. Try to identify ID and Date columns
    has_dates = False
    idx_cmpid = -1
    idx_start = -1
    idx_end = -1

    try:
        idx_cmpid = sql_result_columns.index("cmpid")
        try:
            idx_start = next(i for i, col in enumerate(sql_result_columns) if col in ["start_date", "start_time", "campaign_start"])
            idx_end = next(i for i, col in enumerate(sql_result_columns) if col in ["end_date", "end_time", "campaign_end"])
            has_dates = True
        except StopIteration:
            has_dates = False
    except (ValueError, IndexError):
        return {"clickhouse_sql": ""}

    # 2. Prepare Data (Truncate if necessary)
    # If SQL Result is huge, we MUST truncate it, otherwise the prompt or the generated SQL will be too long.
    MAX_ROWS = 1000
    
    truncated_result = sql_result
    if len(sql_result) > MAX_ROWS:
        print(f"[ClickHouse Generator] Input too large ({len(sql_result)} rows). Truncating to top {MAX_ROWS}.")
        truncated_result = sql_result[:MAX_ROWS]

    cmpid_list = [row[idx_cmpid] for row in truncated_result if idx_cmpid != -1 and row[idx_cmpid] is not None]
    if not cmpid_list:
        return {"clickhouse_sql": ""}

    cmpid_list_str = ", ".join(map(str, set(cmpid_list))) # Removing duplicates for the IN clause

    # 3. Prepare Global Dates (Fallback)
    filters = state.get("extracted_filters", {})
    global_start = filters.get("date_start")
    global_end = filters.get("date_end")

    if not global_start or not global_end:
        today = datetime.now()
        global_end = today.strftime("%Y-%m-%d")
        global_start = (today - timedelta(days=7)).strftime("%Y-%m-%d")

    # 4. LLM Generation
    prompt = PromptTemplate.from_template(CLICKHOUSE_GENERATOR_PROMPT)
    chain = prompt | llm | StrOutputParser()

    response = chain.invoke({
        "cmpid_list": cmpid_list_str,
        "date_start": global_start,
        "date_end": global_end
    })

    raw_sql = clean_sql_output(response)
    if not raw_sql:
        return {"clickhouse_sql": ""}

    # 5. Partition Pruning Optimization (Injecting custom WHERE)
    final_sql = raw_sql

    if has_dates:
        or_clauses = []
        # Only iterate through the truncated result
        for row in truncated_result:
            c_id = row[idx_cmpid]
            s_date = row[idx_start]
            e_date = row[idx_end]

            if not s_date: s_date = global_start
            if not e_date: e_date = global_end

            if isinstance(s_date, datetime): s_date = s_date.strftime("%Y-%m-%d")
            if isinstance(e_date, datetime): e_date = e_date.strftime("%Y-%m-%d")

            or_clauses.append(f"(`cmpid` = {c_id} AND `day_local` BETWEEN '{s_date}' AND '{e_date}')")

        if or_clauses:
            optimized_where = " OR ".join(or_clauses)
            
            # Find WHERE clause boundary using Lookahead
            where_pattern = r"(WHERE\s+.*?)(?=\s+(?:GROUP\s+BY|ORDER\s+BY|LIMIT|HAVING)|$)"
            match = re.search(where_pattern, final_sql, re.DOTALL | re.IGNORECASE)

            if match:
                start_idx = match.start()
                end_idx = match.end()
                final_sql = final_sql[:start_idx] + f"WHERE ({optimized_where})" + final_sql[end_idx:]
            else:
                keyword_pattern = r"(?=\s+(?:GROUP\s+BY|ORDER\s+BY|LIMIT|HAVING))"
                split_match = re.search(keyword_pattern, final_sql, re.IGNORECASE)
                if split_match:
                    insert_pos = split_match.start()
                    final_sql = final_sql[:insert_pos] + f"\nWHERE ({optimized_where}) " + final_sql[insert_pos:]
                else:
                    final_sql = final_sql + f"\nWHERE ({optimized_where})"

    # 6. Safety Cleanup
    final_sql = re.sub(r"GROUP\s+BY\s+GROUP\s+BY", "GROUP BY", final_sql, flags=re.IGNORECASE | re.DOTALL)
    final_sql = re.sub(r"WHERE\s+WHERE", "WHERE", final_sql, flags=re.IGNORECASE | re.DOTALL)
    final_sql = re.sub(r"\n\s*\n", "\n", final_sql).strip()

    return {"clickhouse_sql": final_sql}