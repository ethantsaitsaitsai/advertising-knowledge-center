import os
from typing import Literal

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, BaseMessage
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_community.utilities import SQLDatabase
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
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

    # System prompt for the agent
    agent_system_prompt = f"""
    你是一個與 SQL 資料庫互動的 AI Agent。
    你的目標是根據使用者的問題，生成並執行正確的 {db.dialect} 查詢，然後根據查詢結果回答問題。

    **思考過程**:
    1. **分析問題**: 理解使用者的意圖。問題是否需要查詢資料庫？
    2. **選擇工具**:
        - 如果不確定有哪些資料表，請使用 `sql_db_list_tables` 工具。
        - 如果需要了解特定資料表的結構，請使用 `sql_db_schema` 工具。
        - 當你擁有足夠資訊後，使用 `sql_db_query` 來查詢資料庫。
    3. **生成查詢**: 建立語法正確的查詢。
        - 除非使用者指定數量，否則總是限制查詢結果最多為 5 筆。
        - 永遠不要查詢一個資料表的所有欄位 (`SELECT *`)，只查詢與問題相關的欄位。
        - 請勿執行任何 DML 陳述式 (INSERT, UPDATE, DELETE, DROP)。
    4. **回答**: 根據工具執行的結果，用繁體中文總結並回答使用者的問題。

    如果問題與資料庫無關 (例如：打招呼、閒聊)，請直接回答。
    """

    # Create the agent node
    def agent_node(state: MessagesState):
        """Invokes the agent to decide the next action."""
        messages = [("system", agent_system_prompt)] + state["messages"]
        llm_with_tools = llm.bind_tools(tools)
        response = llm_with_tools.invoke(messages)
        return {"messages": [response]}

    # Create the tool node
    tool_node = ToolNode(tools)

    # 5. Define the graph's conditional logic (the router)
    def router(state: MessagesState) -> Literal["tools", END]:
        """
        Inspects the last message to decide the next step.
        If the agent decided to call a tool, routes to the 'tools' node.
        Otherwise, ends the conversation.
        """
        last_message = state["messages"][-1]
        if last_message.tool_calls:
            # The agent decided to call a tool
            return "tools"
        # The agent did not call a tool, so we end the conversation
        return END

    # 6. Build the graph
    builder = StateGraph(MessagesState)

    builder.add_node("agent", agent_node)
    builder.add_node("tools", tool_node)

    builder.add_edge(START, "agent")
    builder.add_conditional_edges(
        "agent",
        router,
        {
            "tools": "tools",
            "__end__": END,
        },
    )
    builder.add_edge("tools", "agent")

    checkpointer = InMemorySaver()
    agent = builder.compile(checkpointer=checkpointer)

    # 7. Interactive command-line loop
    print("歡迎使用 Text-to-SQL 助理 (v2 - Router)！")
    print("輸入 'exit' 結束程式。")

    config = {"configurable": {"thread_id": "1"}}

    while True:
        user_input = input("\n您的問題：")
        if user_input.lower() == "exit":
            break
        try:
            # Use the agent to process user input
            events = agent.stream(
                {"messages": [("user", user_input)]},
                config,
                stream_mode="values",
            )
            for event in events:
                if "messages" in event:
                    # Print the last message in the list
                    event["messages"][-1].pretty_print()

        except Exception as e:
            print(f"\nAn error occurred: {e}")


if __name__ == "__main__":
    main()
