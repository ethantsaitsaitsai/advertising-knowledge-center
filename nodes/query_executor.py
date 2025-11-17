from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import AIMessage, ToolMessage
from schemas.state import GraphState
from config.llm import llm
from config.database import db
from tools.tool_registry import all_tools
from prompts.executor_prompts import query_executor_prompt


def query_executor_node(state: GraphState) -> GraphState:
    """
    Generates and executes a SQL query based on the clarified query.
    """
    print("---QUERY EXECUTOR---")
    clarified_query = state.get("clarified_query", state["query"])
    messages = state["messages"]
    date_filter = state.get("date_filter") or "無"

    # Get database schema
    schema_tool = [tool for tool in all_tools if tool.name == "sql_db_schema"][0]
    schema_info = schema_tool.invoke({"table_names": "test_cue_list"})  # Assuming single table for now

    # Use LLM to generate SQL query
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", query_executor_prompt),
            ("human", "請根據以下資訊生成 SQL 查詢：\n資料庫結構：{schema}\n使用者問題：{query}\n額外的日期過濾條件：{date_filter}\n資料庫類型：{dialect}"),
        ]
    )

    llm_chain = prompt | llm

    generated_sql_query = llm_chain.invoke(
        {
            "schema": schema_info,
            "query": clarified_query,
            "date_filter": date_filter,
            "dialect": db.dialect,
        }
    ).content

    # Clean the generated SQL query
    clean_sql_query = generated_sql_query.strip().replace("```sql", "").replace("```", "").strip()

    # Execute SQL query
    sql_query_tool = [tool for tool in all_tools if tool.name == "sql_db_query"][0]
    sql_result = sql_query_tool.invoke({"query": clean_sql_query})

    messages.append(AIMessage(content=f"生成的 SQL 查詢：{clean_sql_query}"))
    messages.append(ToolMessage(tool_call_id="sql_execution", content=sql_result))

    return {
        "sql_query": clean_sql_query,
        "sql_result": sql_result,
        "current_stage": "query_executor",
        "messages": messages,
    }
