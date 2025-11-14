import os
from typing import Literal

from dotenv import load_dotenv
from langchain.messages import AIMessage
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_community.utilities import SQLDatabase
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

# Load environment variables from .env file
load_dotenv()


def main():
    # Check if OPENAI_API_KEY is set
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        print("Error: Please set OPENAI_API_KEY in your .env file.")
        return

    # Create database connection URI using mysql-connector-python
    try:
        db_uri = (
            f"mysql+mysqlconnector://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
            f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
        )
    except Exception as e:
        print(
            "Error: Could not read full database connection info from .env file. "
            "Please check if DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME are set."
        )
        print(f"Detailed error: {e}")
        return

    # 1. Create LangChain SQLDatabase object
    db = SQLDatabase.from_uri(db_uri, include_tables=["test_cue_list"])

    # 2. Define the LLM
    llm = ChatOpenAI(model="gpt-4-turbo", temperature=0, openai_api_key=openai_api_key)

    # 3. Create the SQL toolkit and tools
    toolkit = SQLDatabaseToolkit(db=db, llm=llm)
    tools = toolkit.get_tools()

    # 4. Define the graph's nodes

    # Get schema tool and create a ToolNode for it
    get_schema_tool = next(tool for tool in tools if tool.name == "sql_db_schema")
    get_schema_node = ToolNode([get_schema_tool], name="get_schema")

    # Run query tool and create a ToolNode for it
    run_query_tool = next(tool for tool in tools if tool.name == "sql_db_query")
    run_query_node = ToolNode([run_query_tool], name="run_query")

    # Node to list tables
    def list_tables(state: MessagesState):
        list_tables_tool = next(tool for tool in tools if tool.name == "sql_db_list_tables")
        tool_call = {
            "name": "sql_db_list_tables",
            "args": {},
            "id": "tool_call_list_tables",
            "type": "tool_call",
        }
        tool_call_message = AIMessage(content="", tool_calls=[tool_call])
        tool_message = list_tables_tool.invoke(tool_call)
        response = AIMessage(f"可用的資料表: {tool_message.content}")
        return {"messages": [tool_call_message, tool_message, response]}

    # Node to force the model to call the get_schema tool
    def call_get_schema(state: MessagesState):
        llm_with_tools = llm.bind_tools([get_schema_tool], tool_choice="any")
        response = llm_with_tools.invoke(state["messages"])
        return {"messages": [response]}

    # System prompt for query generation
    generate_query_system_prompt = f"""
    你是一個旨在與 SQL 資料庫互動的代理。
    根據輸入問題，建立一個語法正確的 {db.dialect} 查詢來執行，
    然後查看查詢結果並返回答案。
    除非使用者指定了希望獲得的範例數量，否則請始終將查詢限制為最多 5 個結果。
    最終答案請務必使用繁體中文回答。

    你可以根據相關欄位對結果進行排序，以返回資料庫中最有趣的範例。
    永遠不要查詢特定表格的所有欄位，只查詢與問題相關的欄位。

    請勿對資料庫執行任何 DML 陳述式（INSERT、UPDATE、DELETE、DROP 等）。
    """

    # Node to generate the SQL query
    def generate_query(state: MessagesState):
        system_message = {"role": "system", "content": generate_query_system_prompt}
        llm_with_tools = llm.bind_tools([run_query_tool])
        response = llm_with_tools.invoke([system_message] + state["messages"])
        return {"messages": [response]}

    # System prompt for query checking
    check_query_system_prompt = f"""
    你是一位注重細節的 SQL 專家。
    請仔細檢查 {db.dialect} 查詢是否有常見錯誤。
    如果發現任何錯誤，請重寫查詢。如果沒有錯誤，
    只需重現原始查詢即可。
    檢查完畢後，你將呼叫適當的工具來執行查詢。
    """

    # Node to check the query
    def check_query(state: MessagesState):
        system_message = {"role": "system", "content": check_query_system_prompt}
        tool_call = state["messages"][-1].tool_calls[0]
        user_message = {"role": "user", "content": tool_call["args"]["query"]}
        llm_with_tools = llm.bind_tools([run_query_tool], tool_choice="any")
        response = llm_with_tools.invoke([system_message, user_message])
        response.id = state["messages"][-1].id
        return {"messages": [response]}

    # 5. Define the graph's conditional logic
    def should_continue(state: MessagesState) -> Literal[END, "check_query"]:
        last_message = state["messages"][-1]
        if not last_message.tool_calls:
            return END
        else:
            return "check_query"

    # 6. Build the graph
    builder = StateGraph(MessagesState)
    builder.add_node("list_tables", list_tables)
    builder.add_node("call_get_schema", call_get_schema)
    builder.add_node("get_schema", get_schema_node)
    builder.add_node("generate_query", generate_query)
    builder.add_node("check_query", check_query)
    builder.add_node("run_query", run_query_node)

    builder.add_edge(START, "list_tables")
    builder.add_edge("list_tables", "call_get_schema")
    builder.add_edge("call_get_schema", "get_schema")
    builder.add_edge("get_schema", "generate_query")
    builder.add_conditional_edges("generate_query", should_continue)
    builder.add_edge("check_query", "run_query")
    builder.add_edge("run_query", "generate_query")

    agent = builder.compile()

    # 7. Interactive command-line loop
    print("歡迎使用 Text-to-SQL 助理 ！")
    print("輸入 'exit' 結束程式。")

    while True:
        user_input = input("\n您的問題：")
        if user_input.lower() == "exit":
            break
        try:
            # Use the agent to process user input
            events = agent.stream(
                {"messages": [("user", user_input)]},
                stream_mode="values",
            )
            for event in events:
                if "messages" in event:
                    event["messages"][-1].pretty_print()

        except Exception as e:
            print(f"\nAn error occurred: {e}")


if __name__ == "__main__":
    main()
