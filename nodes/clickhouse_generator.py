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
    idx_ad_format_type_id = -1
    idx_start = -1
    idx_end = -1

    try:
        idx_cmpid = sql_result_columns.index("cmpid")
    except ValueError:
        pass # cmpid might not always be present

    try:
        idx_ad_format_type_id = sql_result_columns.index("ad_format_type_id")
    except ValueError:
        pass # ad_format_type_id might not always be present

    if idx_cmpid == -1 and idx_ad_format_type_id == -1:
        # If neither cmpid nor ad_format_type_id is found, we can't generate a meaningful query
        return {"clickhouse_sql": ""}

    try:
        idx_start = next(i for i, col in enumerate(sql_result_columns) if col in ["start_date", "start_time", "campaign_start"])
        idx_end = next(i for i, col in enumerate(sql_result_columns) if col in ["end_date", "end_time", "campaign_end"])
        has_dates = True
    except StopIteration:
        has_dates = False

    # 2. Prepare Data (Truncate if necessary)
    # If SQL Result is huge, we MUST truncate it, otherwise the prompt or the generated SQL will be too long.
    MAX_ROWS = 1000
    
    truncated_result = sql_result
    if len(sql_result) > MAX_ROWS:
        print(f"[ClickHouse Generator] Input too large ({len(sql_result)} rows). Truncating to top {MAX_ROWS}.")
        truncated_result = sql_result[:MAX_ROWS]

    cmpid_list = []
    ad_format_type_id_list = []

    if idx_cmpid != -1:
        cmpid_list = [row[idx_cmpid] for row in truncated_result if row[idx_cmpid] is not None]
    
    if idx_ad_format_type_id != -1:
        ad_format_type_id_list = [row[idx_ad_format_type_id] for row in truncated_result if row[idx_ad_format_type_id] is not None]

    # Combine all relevant IDs into one list to check if we have anything to query
    all_ids = cmpid_list + ad_format_type_id_list
    if not all_ids:
        return {"clickhouse_sql": ""}
    
    cmpid_list_str = ", ".join(map(str, set(cmpid_list))) if cmpid_list else ""
    ad_format_type_id_list_str = ", ".join(map(str, set(ad_format_type_id_list))) if ad_format_type_id_list else ""

    # 3. Prepare Global Dates (Smart Calculation)
    filters = state.get("extracted_filters", {})
    global_start = filters.get("date_start")
    global_end = filters.get("date_end")

    # If dates are missing from filters, try to derive from SQL result
    if (not global_start or not global_end) and has_dates and truncated_result:
        try:
            if not global_start and idx_start != -1:
                start_vals = [row[idx_start] for row in truncated_result if row[idx_start]]
                if start_vals:
                    min_start = min(start_vals)
                    if isinstance(min_start, datetime):
                        global_start = min_start.strftime("%Y-%m-%d")
                    else:
                        global_start = str(min_start)

            if not global_end and idx_end != -1:
                end_vals = [row[idx_end] for row in truncated_result if row[idx_end]]
                if end_vals:
                    max_end = max(end_vals)
                    if isinstance(max_end, datetime):
                        global_end = max_end.strftime("%Y-%m-%d")
                    else:
                        global_end = str(max_end)
        except Exception as e:
            print(f"[ClickHouse Generator] Error deriving dates: {e}")

    # Final Fallback
    if not global_start or not global_end:
        today = datetime.now()
        if not global_end: global_end = today.strftime("%Y-%m-%d")
        if not global_start: global_start = (today - timedelta(days=7)).strftime("%Y-%m-%d")

    # 4. LLM Generation
    prompt = PromptTemplate.from_template(CLICKHOUSE_GENERATOR_PROMPT)
    chain = prompt | llm | StrOutputParser()

    response = chain.invoke({
        "cmpid_list": cmpid_list_str,
        "ad_format_type_id_list": ad_format_type_id_list_str,
        "date_start": global_start,
        "date_end": global_end
    })

    final_sql = clean_sql_output(response)
    
    return {"clickhouse_sql": final_sql}