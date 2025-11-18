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
        ("system", "You are a helpful assistant. Based on the provided SQL query result, provide a concise and clear natural language answer to the user's original question. If the result is an error, explain the error to the user in a helpful way. If the result is an empty list or string, state that no data was found."),
        ("user", "Original question: {original_question}\n\nSQL Result:\n```\n{sql_result}\n```")
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
        # Append the final answer to the messages list
        return {"messages": messages + [AIMessage(content=formatted_response)]}
    except Exception as e:
        error_message = f"Error formatting response: {e}"
        print(error_message)
        return {"messages": messages + [AIMessage(content=f"Sorry, I encountered an error while formatting the final response.")]}