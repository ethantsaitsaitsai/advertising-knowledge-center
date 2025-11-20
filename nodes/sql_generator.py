from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from schemas.state import AgentState
from config.llm import llm
from config.database import db

from pathlib import Path
from prompts.sql_generator_prompt import SQL_GENERATOR_PROMPT
 
def sql_generator(state: AgentState) -> dict:
    """
    Generates a SQL query based on the new structured filters, analysis needs, and conversation history.
    """
    extracted_filters = state.get("extracted_filters", {})
    analysis_needs = state.get("analysis_needs", {})
    confirmed_entities = state.get("confirmed_entities", [])
    messages = state["messages"]
 
    # Get the database schema
    schema = db.get_table_info()
 
    prompt = ChatPromptTemplate.from_messages([
        ("system", SQL_GENERATOR_PROMPT),
        MessagesPlaceholder(variable_name="conversation_history"),
        ("user", "篩選條件 (Filters): {filters}\n\n分析指標 (Metrics): {metrics}\n\n使用者已確認的實體 (Confirmed Entities): {confirmed_entities}\n\nSQL 查詢:")
    ])
 
    chain = prompt | llm
 
    response = chain.invoke({
        "conversation_history": messages,
        "filters": str(extracted_filters),
        "metrics": str(analysis_needs),
        "confirmed_entities": str(confirmed_entities)
    })
 
    sql_query = response.content.strip().replace("```sql", "").replace("```", "").strip()
    
    return {"generated_sql": sql_query}
