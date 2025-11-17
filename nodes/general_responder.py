from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import AIMessage
from schemas.state import GraphState
from config.llm import llm
from prompts.formatter_prompts import general_response_prompt


def general_responder_node(state: GraphState) -> GraphState:
    """
    Generates a general conversational response for non-database queries.
    """
    print("---GENERAL RESPONDER---")
    original_query = state["query"]
    messages = state["messages"]

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", general_response_prompt),
            ("human", "{original_query}"),
        ]
    )
    llm_chain = prompt | llm

    response_content = llm_chain.invoke(
        {
            "original_query": original_query,
        }
    ).content

    messages.append(AIMessage(content=response_content))

    return {
        "formatted_response": response_content,
        "current_stage": "general_responder",
        "messages": messages,
    }
