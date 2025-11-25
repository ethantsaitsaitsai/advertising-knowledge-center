import re
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from schemas.state import AgentState
from config.llm import llm
from prompts.sql_generator_prompt import SQL_GENERATOR_PROMPT


def clean_sql_output(text: str) -> str:
    """
    Cleans the SQL output from the LLM, removing Markdown and explanatory text.
    """
    # 1. Attempt to extract Markdown code block (```sql ... ```)
    pattern = r"```sql\s*(.*?)\s*```"
    match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()

    # 2. Attempt to extract a Markdown block without language tag (``` ... ```)
    pattern_plain = r"```\s*(.*?)\s*```"
    match_plain = re.search(pattern_plain, text, re.DOTALL)
    if match_plain:
        return match_plain.group(1).strip()

    # 3. If no Markdown, try to find SELECT ... ;
    # Heuristic: keep the part from the first SELECT to the end
    select_index = text.upper().find("SELECT")
    if select_index != -1:
        return text[select_index:].strip()

    # 4. If no match, return the original stripped text
    return text.strip()


def sql_generator(state: AgentState) -> dict:
    """
    Generates a SQL query based on the new structured filters, analysis needs, and conversation history.
    """
    extracted_filters = state.get("extracted_filters", {})
    analysis_needs = state.get("analysis_needs", {})
    confirmed_entities = state.get("confirmed_entities", [])
    messages = state["messages"]

    prompt = ChatPromptTemplate.from_messages([
        ("system", SQL_GENERATOR_PROMPT),
        MessagesPlaceholder(variable_name="conversation_history"),
        ("user", "篩選條件 (Filters): {filters}\n\n分析指標 (Metrics): {metrics}\n\n\
         使用者已確認的實體 (Confirmed Entities): {confirmed_entities}\n\nSQL 查詢:")
    ])

    chain = prompt | llm

    # 1. 取得原始需求
    all_metrics = analysis_needs.get('metrics', [])
    dimensions = analysis_needs.get('dimensions', [])

    # 2. 定義 MySQL 白名單
    mysql_whitelist = ["Budget_Sum", "AdPrice_Sum", "Insertion_Count", "Campaign_Count"]

    # 3. 過濾 (只留 MySQL 能做的)
    filtered_metrics = [m for m in all_metrics if m in mysql_whitelist]

    # 4. 建立新的 analysis_needs 給 prompt，確保 dimensions 不會遺失
    prompt_analysis_needs = {
        'metrics': filtered_metrics,
        'dimensions': dimensions
    }

    response = chain.invoke({
        "conversation_history": messages,
        "filters": str(extracted_filters),
        "metrics": str(prompt_analysis_needs),  # <--- 傳入包含 dimensions 的新 dict
        "confirmed_entities": str(confirmed_entities)
    })

    # Clean the output before writing to the state
    clean_sql = clean_sql_output(response.content)

    return {"generated_sql": clean_sql}
