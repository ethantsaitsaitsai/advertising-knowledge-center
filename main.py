import ast
import os
from typing import List, Literal

from dotenv import load_dotenv
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_community.utilities import SQLDatabase
from langchain_core.messages import BaseMessage
from langchain_core.tools import tool
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

    # 3. Define custom tools
    @tool
    def search_ambiguous_term(search_term: str, column_names: List[str]) -> List[str]:
        """
        Searches for an ambiguous term across multiple specified table columns using a LIKE query.
        Use this tool when a user's query contains a potential abbreviation, typo, or partial name
        for a value in the database (e.g., a company or brand name).

        Args:
            search_term: The ambiguous term provided by the user to search for.
            column_names: A list of column names to search within.

        Returns:
            A de-duplicated list of potential matching values found in the database.
        """
        all_matches = set()
        table_name = "test_cue_list"  # Assuming a single table for now
        for column in column_names:
            try:
                # Using f-string for table and column names is generally unsafe,
                # but here we control the table name and the LLM provides the column names
                # from a known schema. Parameters are handled safely by the db.run.
                query = f"SELECT DISTINCT `{column}` FROM `{table_name}` WHERE `{column}` LIKE :search_term"
                results_str = db.run(query, parameters={"search_term": f"%{search_term}%"})
                # The result from db.run is a string representation of a list of tuples, needs parsing.
                # e.g., "[('Result 1',), ('Result 2',)]"
                matches = ast.literal_eval(results_str)
                for match_tuple in matches:
                    if match_tuple and isinstance(match_tuple, tuple):
                        all_matches.add(match_tuple[0])
            except Exception as e:
                # May fail if column doesn't exist or other SQL errors
                print(f"Error searching in column {column}: {e}")
                continue
        return list(all_matches)

    # 4. Create the SQL toolkit and combine tools
    toolkit = SQLDatabaseToolkit(db=db, llm=llm)
    sql_tools = toolkit.get_tools()
    all_tools = sql_tools + [search_ambiguous_term]

    # 5. Define the graph's nodes

    # System prompt for the agent
    agent_system_prompt = f"""
    你是一個專業且謹慎的 AI 資料庫助理，專門與 SQL 資料庫互動。
    你的目標是**完全理解使用者意圖**後，才生成並執行詢。查

    **核心工作流程**:

    1.  **分析與識別模糊詞**:
        - 仔細分析使用者的問題。判斷問題中是否包含任何可能模糊不清的名詞，特別是那些可能對應資料庫中專有名詞（如公司名、品牌名）的詞，例如簡寫、別名或部分名稱。
        - **範例**: 使用者問「綠的」，這可能指的是「綠的國際企業股份有限公司」。

    2.  **澄清模糊詞 (如果需要)**:
        - 如果你識別出模糊詞，**絕對不要**直接用它來查詢。
        - **第一步**: 呼叫 `sql_db_schema` 工具來檢視資料庫結構，找出所有可能包含該名詞的**候選欄位** (例如 `品牌廣告主`, `品牌`, `代理商` 等)。
        - **第二步**: 使用 `search_ambiguous_term` 工具，傳入你找到的候選欄位列表和使用者輸入的模糊詞，進行多欄位模糊搜尋。
        - **第三步**:
            - 如果 `search_ambiguous_term` 找到了可能的匹配項，向使用者提出澄清問題，讓使用者確認。例如：「關於『綠的』，我找到了『綠的國際企業股份有限公司』，請問是這個嗎？」
            - 如果找不到任何匹配項，也請告知使用者。
        - **等待使用者確認後，再進行下一步。**

    3.  **生成與執行最終查詢**:
        - 當所有名詞都**被確認無誤**後，使用 `sql_db_query` 工具來生成並執行一個語法正確、高效的 {db.dialect} 查詢。
        - **查詢原則**:
            - 除非使用者指定，否則總是限制最多 5 筆結果。
            - 永遠只查詢問題相關的欄位，禁止使用 `SELECT *`。
            - 嚴禁執行任何 DML 陳述式 (INSERT, UPDATE, DELETE, DROP)。

    4.  **回答問題**:
        - 根據最終查詢結果，用繁體中文清晰地回答使用者的問題。
        - 如果過程中你進行了澄清，可以在最終答案中說明你是如何確認的。

    如果問題與資料庫無關 (例如：打招呼)，請直接回答。
    """

    # Create the agent node
    def agent_node(state: MessagesState):
        """Invokes the agent to decide the next action."""
        messages = [("system", agent_system_prompt)] + state["messages"]
        llm_with_tools = llm.bind_tools(all_tools)
        response = llm_with_tools.invoke(messages)
        return {"messages": [response]}

    # Create the tool node
    tool_node = ToolNode(all_tools)

    # 6. Define the graph's conditional logic (the router)
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

    # 7. Build the graph
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

    # --- Server Setup ---
    from fastapi import FastAPI
    from langserve import add_routes

    app = FastAPI(
        title="Text-to-SQL Agent Server",
        version="1.0",
        description="A server for the Text-to-SQL LangGraph agent.",
    )

    # Add the routes for the agent to the FastAPI app
    add_routes(app, agent, path="/agent", config_keys=["configurable"])

    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()