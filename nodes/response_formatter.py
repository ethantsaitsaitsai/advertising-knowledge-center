from schemas.state import GraphState
from config.llm import llm
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import AIMessage


def response_formatter_node(state: GraphState) -> GraphState:
    """
    Formats the SQL query result into a natural language response using an LLM.
    """
    print("---RESPONSE FORMATTER---")
    sql_result = state.get("sql_result", "No result available.")
    messages = state["messages"]

    # Define a prompt for the LLM to format the response
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a helpful assistant. Based on the SQL query result, provide a concise and clear natural language answer to the user's original question. If the result is empty or an error, state that clearly."),
        ("user", "Original question: {original_question}\nSQL Result: {sql_result}")
    ])

    # Extract the original question from the messages
    original_question = ""
    for msg in messages:
        if msg.type == "human":
            original_question = msg.content
            break

    if not original_question:
        original_question = "The user's question is not available in the history."

    # Create a chain to format the response
    response_chain = prompt | llm

    try:
        formatted_response = response_chain.invoke({
            "original_question": original_question,
            "sql_result": sql_result
        }).content
        print(f"Formatted Response: {formatted_response}")
        messages.append(AIMessage(content=formatted_response))
        return {"messages": messages}
    except Exception as e:
        error_message = f"Error formatting response: {e}"
        print(error_message)
        messages.append(AIMessage(content=f"Error: {error_message}"))
        return {"messages": messages}
