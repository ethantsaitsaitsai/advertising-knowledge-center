import json
from schemas.state import GraphState
from config.llm import llm
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers.string import StrOutputParser


def ambiguity_detector_node(state: GraphState) -> GraphState:
    """
    Detects potentially ambiguous terms (proper nouns, specific concepts) in the user's query.
    """
    print("---AMBIGUITY DETECTOR---")
    user_question = state["messages"][-1].content

    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a linguistic analysis expert. Your task is to extract potentially ambiguous proper nouns or key terms from the user's question that might need to be looked up in a database. Examples include company names, product names, campaign names, or specific technical terms. Respond with only a JSON-formatted list of strings. For example: [\"永達保險\", \"媒體預算\"]. If no such terms are found, respond with an empty list []."),
        ("user", "{question}")
    ])

    chain = prompt | llm | StrOutputParser()

    try:
        response_str = chain.invoke({"question": user_question})
        # Clean the response to ensure it's valid JSON
        cleaned_response = response_str.strip().replace("```json", "").replace("```", "").strip()
        terms_to_check = json.loads(cleaned_response)

        if not isinstance(terms_to_check, list):
            raise json.JSONDecodeError("Expected a JSON list.", cleaned_response, 0)

        print(f"Detected terms to check: {terms_to_check}")
        return {"terms_to_check": terms_to_check}
    except (json.JSONDecodeError, Exception) as e:
        print(f"Error in ambiguity detector, defaulting to empty list: {e}")
        # If parsing fails, proceed with an empty list to avoid breaking the flow
        return {"terms_to_check": []}
