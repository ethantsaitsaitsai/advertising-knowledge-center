from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import AIMessage
from schemas.state import GraphState
from config.llm import llm
from prompts.formatter_prompts import response_formatter_prompt


def response_formatter_node(state: GraphState) -> GraphState:
    """
    Formats the SQL query result into a natural language response.
    """
    print("---RESPONSE FORMATTER---")
    original_query = state["query"]
    sql_result = state["sql_result"]
    messages = state["messages"]

    # Use LLM to format the response
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", response_formatter_prompt),
            ("human", "請根據以下資訊生成回覆：\n原始問題：{original_query}\nSQL 查詢結果：{sql_result}"),
        ]
    )
    llm_chain = prompt | llm

    formatted_response = llm_chain.invoke(
        {
            "original_query": original_query,
            "sql_result": sql_result,
        }
    ).content

    messages.append(AIMessage(content=formatted_response))

    return {
        "formatted_response": formatted_response,
        "current_stage": "response_formatter",
        "messages": messages,
    }
