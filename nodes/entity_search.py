from schemas.state import AgentState
from tools.search_db import search_ambiguous_term
from typing import Dict, Any

def entity_search_node(state: AgentState) -> Dict[str, Any]:
    """
    Searches the database for ambiguous terms to find potential candidates for clarification.
    """
    ambiguous_terms = state.get("ambiguous_terms", [])
    if not ambiguous_terms:
        return {}

    # For simplicity, we handle one ambiguous term at a time.
    term_to_search = ambiguous_terms[0]
    
    # TODO: In a real-world scenario, the column and table could be determined dynamically.
    column_to_search = "廣告案件名稱"
    table_to_search = "cuelist"
    
    print(f"Searching for ambiguous term '{term_to_search}' in {table_to_search}.{column_to_search}...")
    
    candidates = search_ambiguous_term.invoke({
        "keyword": term_to_search,
        "column_name": column_to_search,
        "table_name": table_to_search,
    })
    
    print(f"Found candidates: {candidates}")

    # Update the state with the found candidates
    return {"candidate_values": candidates}
