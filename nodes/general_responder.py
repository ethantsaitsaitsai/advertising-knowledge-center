from schemas.state import GraphState
from config.llm import llm
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import AIMessage

def general_responder_node(state: GraphState) -> GraphState:
    """
    Generates a conversational response for non-query related inputs.
    """
    print("---GENERAL RESPONDER---")
    user_question = state["messages"][-1].content

    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a friendly and helpful assistant. Respond to the user's message in a conversational manner."),
        ("user", "{question}")
    ])
    
    chain = prompt | llm

    try:
        response = chain.invoke({"question": user_question})
        return {"messages": [AIMessage(content=response.content)]}
    except Exception as e:
        print(f"Error in general responder: {e}")
        error_message = "I'm sorry, I encountered an issue. Could you please rephrase that?"
        return {"messages": [AIMessage(content=error_message)]}
