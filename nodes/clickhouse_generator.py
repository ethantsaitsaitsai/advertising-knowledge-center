from schemas.state import AgentState
from config.llm import llm
from prompts.clickhouse_generator_prompt import CLICKHOUSE_GENERATOR_PROMPT
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from datetime import datetime, timedelta
import re
from utils.formatter import split_date_range


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
    Optimized with Partition Pruning logic and Batching.
    """
    sql_result = state.get("sql_result")
    sql_result_columns = state.get("sql_result_columns")

    if not sql_result or not sql_result_columns:
        return {"clickhouse_sql": "", "clickhouse_sqls": []}

    # 1. Robust Column Index Finding (Case-Insensitive)
    col_map = {col.lower(): i for i, col in enumerate(sql_result_columns)}

    idx_cmpid = col_map.get("cmpid", -1)
    # Fallback: if cmpid is missing, try 'id' but verify it's not ad_format_type_id
    if idx_cmpid == -1:
        idx_id = col_map.get("id", -1)
        idx_fmt_id = col_map.get("ad_format_type_id", -1)
        if idx_id != -1 and idx_id != idx_fmt_id:
             idx_cmpid = idx_id

    idx_ad_format_type_id = col_map.get("ad_format_type_id", -1)

    if idx_cmpid == -1 and idx_ad_format_type_id == -1:
        print("[ClickHouse Generator] Warning: No 'cmpid' or 'ad_format_type_id' found in SQL result.")
        return {"clickhouse_sql": "", "clickhouse_sqls": []}

    # Identify Date Columns flexibly
    idx_start = -1
    idx_end = -1
    has_dates = False
    
    date_start_keywords = ["start_date", "start_time", "campaign_start"]
    date_end_keywords = ["end_date", "end_time", "campaign_end"]
    
    for kw in date_start_keywords:
        if kw in col_map:
            idx_start = col_map[kw]
            break
            
    for kw in date_end_keywords:
        if kw in col_map:
            idx_end = col_map[kw]
            break
            
    if idx_start != -1 and idx_end != -1:
        has_dates = True

    # 2. Prepare Data (Truncate if necessary)
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

    all_ids = cmpid_list + ad_format_type_id_list
    if not all_ids:
        return {"clickhouse_sql": "", "clickhouse_sqls": []}
    
    cmpid_list_str = ", ".join(map(str, set(cmpid_list))) if cmpid_list else ""
    ad_format_type_id_list_str = ", ".join(map(str, set(ad_format_type_id_list))) if ad_format_type_id_list else ""

    # 3. Prepare Global Dates (Smart Calculation)
    filters = state.get("extracted_filters", {})
    global_start = filters.get("date_start")
    global_end = filters.get("date_end")

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

    if not global_start or not global_end:
        today = datetime.now()
        if not global_end: global_end = today.strftime("%Y-%m-%d")
        if not global_start: global_start = (today - timedelta(days=7)).strftime("%Y-%m-%d")

    # --- Batching Logic Start ---
    intervals = split_date_range(global_start, global_end)
    first_interval = intervals[0]

    # 4. Get Dimensions for Grouping Logic
    raw_analysis_needs = state.get('analysis_needs')
    if hasattr(raw_analysis_needs, 'model_dump'):
        analysis_needs = raw_analysis_needs.model_dump()
    elif hasattr(raw_analysis_needs, 'dict'):
        analysis_needs = raw_analysis_needs.dict()
    elif isinstance(raw_analysis_needs, dict):
        analysis_needs = raw_analysis_needs
    else:
        analysis_needs = {}
        
    dimensions_list = analysis_needs.get("dimensions", [])
    dimensions_str = ", ".join(dimensions_list)

    # 5. LLM Generation
    prompt = PromptTemplate.from_template(CLICKHOUSE_GENERATOR_PROMPT)
    chain = prompt | llm | StrOutputParser()

    response = chain.invoke({
        "cmpid_list": cmpid_list_str,
        "ad_format_type_id_list": ad_format_type_id_list_str,
        "date_start": first_interval[0],
        "date_end": first_interval[1],
        "dimensions": dimensions_str # Pass dimensions to prompt
    })

    base_sql = clean_sql_output(response)
    clickhouse_sqls = []

    if len(intervals) == 1:
        clickhouse_sqls.append(base_sql)
    else:
        for start, end in intervals:
            new_sql = base_sql.replace(first_interval[0], start).replace(first_interval[1], end)
            clickhouse_sqls.append(new_sql)

    return {
        "clickhouse_sql": clickhouse_sqls[0], 
        "clickhouse_sqls": clickhouse_sqls
    }
