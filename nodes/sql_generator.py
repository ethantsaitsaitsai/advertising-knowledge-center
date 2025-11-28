import re
from datetime import datetime
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from schemas.state import AgentState
from config.llm import llm
from prompts.sql_generator_prompt import SQL_GENERATOR_PROMPT
from utils.formatter import split_date_range


def clean_sql_output(text: str) -> str:
    """
    Cleans the SQL output from the LLM, removing Markdown and explanatory text.
    """
    pattern = r"```sql\s*(.*?)\s*```"
    match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()

    pattern_plain = r"```\s*(.*?)\s*```"
    match_plain = re.search(pattern_plain, text, re.DOTALL)
    if match_plain:
        return match_plain.group(1).strip()

    select_index = text.upper().find("SELECT")
    if select_index != -1:
        return text[select_index:].strip()

    return text.strip()


def sql_generator(state: AgentState) -> dict:
    """
    Generates SQL query(s). Supports batching for long date ranges.
    """
    extracted_filters = state.get("extracted_filters", {})
    analysis_needs = state.get("analysis_needs", {})
    confirmed_entities = state.get("confirmed_entities", [])
    messages = state["messages"]

    prompt = ChatPromptTemplate.from_messages([
        ("system", SQL_GENERATOR_PROMPT),
        MessagesPlaceholder(variable_name="conversation_history"),
        ("user", "篩選條件 (Filters): {filters}\n\n分析指標 (Metrics): {metrics}\n\n         使用者已確認的實體 (Confirmed Entities): {confirmed_entities}\n\nSQL 查詢:")
    ])

    chain = prompt | llm

    # 1. Handle Metrics & Dimensions
    all_metrics = analysis_needs.get('metrics', [])
    dimensions = analysis_needs.get('dimensions', [])
    mysql_whitelist = ["Budget_Sum", "AdPrice_Sum", "Insertion_Count", "Campaign_Count"]
    filtered_metrics = [m for m in all_metrics if m in mysql_whitelist]
    
    prompt_analysis_needs = {
        'metrics': filtered_metrics,
        'dimensions': dimensions
    }

    # 2. Handle Date Ranges & Batching
    date_start = extracted_filters.get("date_start")
    date_end = extracted_filters.get("date_end")
    
    # Default to a safe range if missing (though SlotManager should catch this)
    if not date_start: date_start = "2025-01-01"
    if not date_end: date_end = datetime.now().strftime("%Y-%m-%d")

    intervals = split_date_range(date_start, date_end)
    
    # Use the FIRST interval to generate the template SQL
    first_interval = intervals[0]
    
    # Create a temporary filter for generation
    current_filters = extracted_filters.copy()
    current_filters["date_start"] = first_interval[0]
    current_filters["date_end"] = first_interval[1]

    response = chain.invoke({
        "conversation_history": messages,
        "filters": str(current_filters),
        "metrics": str(prompt_analysis_needs),
        "confirmed_entities": str(confirmed_entities)
    })

    base_sql = clean_sql_output(response.content)
    generated_sqls = []

    # 3. Generate all SQLs via String Replacement
    # We replace the first interval's dates with subsequent intervals
    if len(intervals) == 1:
        generated_sqls.append(base_sql)
    else:
        # Replace logic
        # Note: This assumes the LLM actually used the dates we gave it.
        # If the dates are standard format YYYY-MM-DD, this should work.
        for start, end in intervals:
            new_sql = base_sql.replace(first_interval[0], start).replace(first_interval[1], end)
            generated_sqls.append(new_sql)

    return {
        "generated_sql": generated_sqls[0], # For compatibility / logging
        "generated_sqls": generated_sqls    # The real payload
    }