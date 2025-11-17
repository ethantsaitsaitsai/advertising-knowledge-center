from langchain_core.messages import ToolMessage
from schemas.state import GraphState
from tools.tool_registry import all_tools


def sql_executor_node(state: GraphState) -> GraphState:
    """
    Executes the generated SQL query.
    """
    print("---SQL EXECUTOR---")
    sql_query = state["generated_sql"]
    messages = state["messages"]

    # Execute SQL query
    sql_query_tool = [tool for tool in all_tools if tool.name == "sql_db_query"][0]
    sql_result = sql_query_tool.invoke({"query": sql_query})

    # Append messages to be stored in history
    messages.append(ToolMessage(content=sql_query, tool_call_id="sql_query_generation"))
    messages.append(ToolMessage(content=sql_result, tool_call_id="sql_execution"))

    return {
        "sql_result": sql_result,
        "current_stage": "sql_executor",
        "messages": messages,
    }
