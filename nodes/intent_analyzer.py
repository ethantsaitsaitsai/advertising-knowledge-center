from schemas.state import GraphState
from config.llm import llm
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers.string import StrOutputParser

def intent_analyzer_node(state: GraphState) -> GraphState:
    """
    Analyzes the user's intent to determine if it's a database query or chitchat.
    """
    print("---INTENT ANALYZER---")
    user_question = state["messages"][-1].content

    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an intent classifier. Your task is to determine if the user's message is a request for data ('query') or just casual conversation ('chitchat'). Respond with only one word: 'query' or 'chitchat'."),
        ("user", "{question}")
    ])
    
    chain = prompt | llm | StrOutputParser()

    try:
        intent = chain.invoke({"question": user_question}).strip().lower()
        print(f"Detected Intent: {intent}")
        
        if intent not in ['query', 'chitchat']:
            # Default to 'query' if the classification is unclear
            intent = 'query'
            print("Classifier output was unclear, defaulting to 'query'.")

        return {"intent": intent}
    except Exception as e:
        print(f"Error in intent analysis: {e}")
        # Default to 'query' on error to be safe
        return {"intent": "query"}
