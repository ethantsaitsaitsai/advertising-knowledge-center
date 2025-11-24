from schemas.state import AgentState
from config.llm import llm
from prompts.clickhouse_generator_prompt import CLICKHOUSE_GENERATOR_PROMPT
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from datetime import datetime, timedelta


def clickhouse_generator_node(state: AgentState) -> dict:
    """
    Generates a ClickHouse SQL query to fetch performance data based on cmpid list.
    """
    sql_result = state.get("sql_result")
    sql_result_columns = state.get("sql_result_columns")

    if not sql_result or not sql_result_columns:
        return {"clickhouse_sql": ""}

    try:
        cmpid_index = sql_result_columns.index("cmpid")
        cmpid_list = [row[cmpid_index] for row in sql_result if row[cmpid_index] is not None]
    except (ValueError, IndexError):
        # If 'cmpid' column is not found or index is out of range, return empty.
        return {"clickhouse_sql": ""}

    if not cmpid_list:
        return {"clickhouse_sql": ""}

    # Remove duplicates
    cmpid_list = list(set(cmpid_list))
    # Format for SQL IN clause
    cmpid_list_str = ", ".join(map(str, cmpid_list))

    # Get date range from state or default to last 7 days
    filters = state.get("extracted_filters", {})
    date_start = filters.get("date_start")
    date_end = filters.get("date_end")

    if not date_start or not date_end:
        today = datetime.now()
        date_end = today.strftime("%Y-%m-%d")
        date_start = (today - timedelta(days=7)).strftime("%Y-%m-%d")

    # The prompt is now a string, not a PromptTemplate from the file
    prompt = PromptTemplate.from_template(CLICKHOUSE_GENERATOR_PROMPT)
    chain = prompt | llm | StrOutputParser()

    response = chain.invoke({
        "cmpid_list": cmpid_list_str,
        "date_start": date_start,
        "date_end": date_end
    })

    # Basic cleaning, assuming the model follows instructions well
    # A more robust cleaner can be added if needed, similar to the main sql_generator
    clickhouse_sql = response.strip().replace("```sql", "").replace("```", "").strip()

    return {"clickhouse_sql": clickhouse_sql}
