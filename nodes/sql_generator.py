from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from schemas.state import AgentState
from config.llm import llm
from config.database import db

def sql_generator(state: AgentState) -> dict:
    """
    Generates a SQL query based on the extracted_slots and conversation history.
    """
    extracted_slots = state["extracted_slots"]
    messages = state["messages"]

    # Get the database schema
    schema = db.get_table_info()

    prompt = ChatPromptTemplate.from_messages([
        ("system", """你是一位精通 MySQL 的 SQL 撰寫大師。你的任務是根據**整段對話**、提取的查詢條件 (slots) 和提供的資料庫結構，生成一個語法完全正確的 MySQL 查詢。

        **資料庫與業務規則:**
        1.  **表格路由 (Table Routing)**:
            *   當問題涉及到 **預算 (`媒體預算`)**、**產業 (`客戶產業類別`)** 或 **品牌 (`品牌`)** 的分析時，**必須**使用 `cuelist` 表格。
            *   當問題涉及到 **執行細節** 或 **活動狀態 (`status`)** 時，才考慮使用 `one_campaigns` 表格。

        2.  **日期處理 (Date Handling)**:
            *   `cuelist` 表格中的 `刊登日期(起)` 欄位是 **字串 (VARCHAR)** 格式。
            *   當需要在 `cuelist` 上進行日期比較或過濾時，你 **必須** 使用 `STR_TO_DATE` 函式將其轉換為日期格式。
            *   **語法**: `STR_TO_DATE(刊登日期(起), '%Y-%m-%d')`

        3.  **欄位定義 (Ambiguity Resolution)**:
            *   當使用者提到「預算」或 "Budget" 時，它 **唯一** 對應的欄位是 `cuelist.媒體預算`。

        4.  **輸出格式**:
            *   你的最終輸出**必須**只有原始的 SQL 查詢字串，不要包含任何其他文字、解釋或 markdown 的 `sql` 標籤。

        **範例:**
        - 使用者問題: "2023上半年電腦業的總預算是多少？"
        - `extracted_slots`: `{{'industry': '電腦', 'date_range': {{'start_date': '2023-01-01', 'end_date': '2023-06-30'}}}}`
        - 你應該生成:
          `SELECT SUM(媒體預算) FROM cuelist WHERE 客戶產業類別 = '電腦' AND STR_TO_DATE(刊登日期(起), '%Y-%m-%d') BETWEEN '2023-01-01' AND '2023-06-30'`
        """),
        MessagesPlaceholder(variable_name="conversation_history"),
        ("user", "資料庫結構:\n{schema}\n\n查詢條件 (Slots): {slots}\n\nSQL 查詢:")
    ])

    chain = prompt | llm

    response = chain.invoke({
        "schema": schema,
        "conversation_history": messages,
        "slots": str(extracted_slots)
    })

    sql_query = response.content.strip().replace("```sql", "").replace("```", "").strip()
    
    return {"generated_sql": sql_query}
