from langchain_core.prompts import ChatPromptTemplate
from schemas.state import GraphState
from config.llm import llm
from config.database import db
from tools.tool_registry import all_tools
from prompts.executor_prompts import query_executor_prompt


def sql_generator_node(state: GraphState) -> GraphState:
    """
    Generates a SQL query based on the clarified query and term clarifications.
    """
    print("---SQL GENERATOR---")
    clarified_query = state.get("clarified_query", state["query"])
    date_filter = state.get("date_filter") or "無"
    term_clarifications = state.get("term_clarifications", [])

    # Get database schema
    schema_tool = [tool for tool in all_tools if tool.name == "sql_db_schema"][0]
    schema_info = schema_tool.invoke({"table_names": "test_cue_list"})

    # Use LLM to generate SQL query
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", query_executor_prompt),
            ("human", "請根據以下資訊生成 SQL 查詢：\n資料庫結構：{schema}\n使用者問題：{query}\n已確認的澄清資訊：{term_clarifications}\n額外的日期過濾條件：{date_filter}\n資料庫類型：{dialect}"),
        ]
    )
    llm_chain = prompt | llm

    generated_sql_query = llm_chain.invoke(
        {
            "schema": schema_info,
            "query": clarified_query,
            "term_clarifications": term_clarifications,
            "date_filter": date_filter,
            "dialect": db.dialect,
        }
    ).content

    # Clean the generated SQL query
    clean_sql_query = generated_sql_query.strip().replace("```sql", "").replace("```", "").strip()

    return {
        "generated_sql": clean_sql_query,
        "current_stage": "sql_generator",
    }
