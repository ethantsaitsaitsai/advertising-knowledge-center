from langchain.agents import create_agent
from langchain_core.prompts import PromptTemplate
from tools.tool_registry import all_tools
from config.llm import llm
from config.database import db
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from schemas.state import GraphState
from nodes.sql_constraint_checker import sql_constraint_checker_node
from nodes.sql_executor import sql_executor_node
from nodes.response_formatter import response_formatter_node
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from typing import Literal


# Define the system prompt for the agent
# Its final output should be the raw SQL query string
system_prompt = PromptTemplate.from_template("""
你是一個專業的 SQL 資料庫查詢助理。你的目標是透過與使用者對話和使用工具，最終生成一個語法正確的 SQL 查詢來回答使用者的問題。

**你的思考與行動流程應該如下:**

1.  **分析問題**: 首先，仔細分析使用者最新的問題。
2.  **了解資料庫結構**:
    -   你**必須**先使用 `sql_db_list_tables` 工具來查看資料庫中有哪些可用的資料表。
    -   然後，使用 `sql_db_schema` 工具來獲取相關資料表的欄位資訊。
3.  **檢查模糊點**: 判斷問題中是否有任何模糊不清的詞彙（例如，不明確的品牌、案件名稱等）。
4.  **解決模糊點 (如果有的話)**:
    a.  如果你發現一個模糊的詞彙，你**必須**使用 `find_ambiguous_term_options` 工具來尋找可能的選項。
    b.  在獲得選項後，你**必須**使用 `ask_user_for_clarification` 工具來向使用者提問，並獲取他的回覆。
    c.  根據使用者的回覆，更新你對問題的理解。如果使用者轉換了話題，那就以他的新問題為準。
5.  **生成 SQL 查詢**:
    -   當你確信所有詞彙都已清晰、不再有模糊點時，基於你對資料庫結構的理解，建構一個語法完全正確的 {dialect} SQL 查詢。
    -   **你的最終輸出必須是這個原始的 SQL 查詢字串，而不是自然語言回覆，也不是呼叫任何執行 SQL 的工具。**
    -   永遠只查詢問題相關的欄位，禁止使用 `SELECT *`。
    -   你可以根據相關欄位對結果進行排序，以返回資料庫中最有趣的範例。
    -   **嚴禁**生成任何 DML 陳述式 (INSERT, UPDATE, DELETE, DROP 等) 到資料庫。

**可用的工具有**:
{tools}

**對話歷史**:
{chat_history}

**使用者的問題**:
{input}

**你的思考過程 (請逐步思考，並決定下一步的行動)**:
{agent_scratchpad}
""").partial(dialect=db.dialect)

# Create the agent (LLM with tools)
# This agent's job is to produce SQL or call clarification tools
agent_runnable = create_agent(
    llm,
    all_tools,  # all_tools now only includes clarification/schema tools
    system_prompt=system_prompt.template,
    checkpointer=InMemorySaver(),
)


# Define the agent node for the graph
def agent_node(state: GraphState) -> GraphState:
    """
    Invokes the ReAct agent to decide the next action (tool call or SQL generation).
    """
    result = agent_runnable.invoke(state)
    # The agent's output is either a tool call or a final SQL string
    return {"messages": result["messages"]}


# The tool node executes the tools called by the agent
tool_node = ToolNode(all_tools)


# --- Router Functions ---
def route_agent_output(state: GraphState) -> Literal["tools", "sql_constraint_checker"]:
    """
    Routes the agent's output.
    If it's a tool call, go to tools.
    If it's a final answer (SQL string), go to sql_constraint_checker.
    """
    last_message: BaseMessage = state["messages"][-1]
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tools"
    # Assuming if it's not a tool call, it's the proposed SQL
    return "sql_constraint_checker"


def route_sql_checker_output(state: GraphState) -> Literal["sql_executor", "agent"]:
    """
    Routes based on the SQL constraint checker's output.
    If SQL is safe, go to executor.
    If not safe, go back to agent.
    """
    if state.get("sql_is_safe"):
        return "sql_executor"
    return "agent"  # Loop back to agent for correction


# --- Build the Graph ---
builder = StateGraph(GraphState)

# Add nodes
builder.add_node("agent", agent_node)
builder.add_node("tools", tool_node)
builder.add_node("sql_constraint_checker", sql_constraint_checker_node)
builder.add_node("sql_executor", sql_executor_node)
builder.add_node("response_formatter", response_formatter_node)

# Set entry point
builder.set_entry_point("agent")

# Define edges
builder.add_conditional_edges(
    "agent",
    route_agent_output,
    {
        "tools": "tools",
        "sql_constraint_checker": "sql_constraint_checker",
    },
)
builder.add_edge("tools", "agent")  # After tool execution, go back to agent

builder.add_conditional_edges(
    "sql_constraint_checker",
    route_sql_checker_output,
    {
        "sql_executor": "sql_executor",
        "agent": "agent",  # If SQL is not safe, go back to agent
    },
)
builder.add_edge("sql_executor", "response_formatter")
builder.add_edge("response_formatter", END)

# Compile the graph
graph = builder.compile()
