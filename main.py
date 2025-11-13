import os

from dotenv import load_dotenv
from langchain_community.agent_toolkits import create_sql_agent
from langchain_community.utilities import SQLDatabase
from langchain_openai import ChatOpenAI
from langchain_core.prompts import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
    MessagesPlaceholder,
)

# 載入 .env 檔案中的環境變數
load_dotenv()


def main():
    # 檢查 OPENAI_API_KEY 是否已設定
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        print("錯誤：請在 .env 檔案中設定 OPENAI_API_KEY。")
        return

    # 建立資料庫連線 URI，使用 mysql-connector-python
    try:
        db_uri = (
            f"mysql+mysqlconnector://\
                {os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
            f"@{os.getenv('DB_HOST')}:\
                {os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
        )
    except Exception as e:
        print("錯誤：無法從 .env 檔案中讀取完整的資料庫連線資訊。\
              請檢查 DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME 是否都已設定。")
        print(f"詳細錯誤：{e}")
        return
    # 1. 建立 LangChain SQLDatabase 物件
    db = SQLDatabase.from_uri(db_uri, include_tables=['test_cue_list'])

    # 2. 定義 LLM
    llm = ChatOpenAI(model="gpt-4-turbo",
                     temperature=0,
                     openai_api_key=openai_api_key)

    # 3. 定義繁體中文的自訂提示
    system_prefix_chinese = """
    你是一個旨在與 SQL 資料庫互動的代理。
    根據輸入問題，建立一個語法正確的 {dialect} 查詢來執行，
    然後查看查詢結果並返回答案。
    你可以根據相關欄位對結果進行排序，以返回資料庫中最有趣的範例。
    永遠不要查詢特定表格的所有欄位，只查詢與問題相關的欄位。
    你可以使用工具與資料庫互動。
    只使用以下工具。
    只使用以下工具返回的資訊來建構你的最終答案。
    在執行查詢之前，你必須驗證你的查詢。
    如果在執行查詢時遇到錯誤，請重新編寫查詢並再次嘗試。
    不要在資料庫上執行任何 DML 語句（INSERT、UPDATE、DELETE、DROP 等）。
    首先，你應該始終查看資料庫中的表格以了解可以查詢的內容。
    不要跳過此步驟。然後，你應該查詢最相關表格的 schema。
    """

    custom_prompt = ChatPromptTemplate.from_messages(
        [
            SystemMessagePromptTemplate.from_template(system_prefix_chinese),
            MessagesPlaceholder(variable_name="chat_history"),
            HumanMessagePromptTemplate.from_template("{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ]
    )

    # 4. 建立 SQL Agent，並傳入自訂提示
    agent_executor = create_sql_agent(
        llm, db=db,
        agent_type="tool-calling",
        verbose=True,
        prompt=custom_prompt  # 傳入自訂提示
    )

    # 5. 命令列互動迴圈
    print("歡迎使用 Text-to-SQL 助手 (SQL Agent 版本)！")
    print("輸入 'exit' 結束程式。")

    while True:
        user_input = input("\n您的問題：")
        if user_input.lower() == "exit":
            break
        try:
            # 使用 agent executor 來處理使用者輸入
            response = agent_executor.invoke(
                {"input": user_input, "chat_history": []}
            )
            print("\n助手回應：")
            print(response["output"])
        except Exception as e:
            print(f"\n發生錯誤：{e}")


if __name__ == "__main__":
    main()
