from schemas.state import GraphState
from tools.ambiguity_tools import find_ambiguous_term_options
from tools.clarification_tools import ask_user_for_clarification
from langchain_core.messages import AIMessage, ToolMessage
import uuid


def ambiguity_resolver_node(state: GraphState) -> GraphState:
    """
    Resolves ambiguities by finding options for terms and asking the user for clarification if needed.
    """
    print("---AMBIGUITY RESOLVER---")
    terms_to_check = state.get("terms_to_check", [])
    messages = state["messages"]

    if not terms_to_check:
        print("No terms to resolve.")
        return {"clarified_terms": {}}

    ambiguity_found = False
    questions_for_user = []
    clarified_terms = {}

    # Define a default list of columns to search for ambiguous terms
    # In a more advanced setup, this could be dynamically determined.
    columns_to_search = ['品牌廣告主', '品牌', '廣告案件名稱', '代理商', '廣告格式']

    for term in terms_to_check:
        print(f"Checking term: '{term}' in columns: {columns_to_search}")
        # Call the find_ambiguous_term_options tool with the correct arguments
        tool_input = {
            "search_term": term,
            "column_names": columns_to_search
        }
        options = find_ambiguous_term_options.invoke(tool_input)

        if not options:
            # If no options found, assume the term is clear as is
            clarified_terms[term] = term
            print(f"No options found for '{term}', assuming it's clear.")
        elif len(options) == 1:
            # If only one option, assume it's the correct one
            clarified_terms[term] = options[0]['value']
            print(f"One option found for '{term}', assuming '{options[0]['value']}'.")
        else:
            # If multiple options, we have an ambiguity
            ambiguity_found = True
            question = {
                "term": term,
                "options": options
            }
            questions_for_user.append(question)
            print(f"Ambiguity found for '{term}': {options}")

    if ambiguity_found:
        print("Asking user for clarification...")
        # Create a special AIMessage that the main loop will catch to handle clarification
        clarification_request_id = str(uuid.uuid4())
        clarification_message = AIMessage(
            content="I need your help to clarify some terms.",
            additional_kwargs={
                "clarification_request": {
                    "questions": questions_for_user,
                    "id": clarification_request_id
                }
            }
        )
        messages.append(clarification_message)
        return {"messages": messages}
    else:
        # If no ambiguities were found after checking all terms
        print("All terms are clear.")
        return {"clarified_terms": clarified_terms, "messages": messages}
