from schemas.state import AgentState
from tools.search_db import search_ambiguous_term
from typing import Dict, Any


def entity_search_node(state: AgentState) -> Dict[str, Any]:
    """
    Searches for each ambiguous term across multiple predefined columns in the database
    and aggregates the unique candidates for clarification.
    """
    ambiguous_terms = state.get("ambiguous_terms", [])
    if not ambiguous_terms:
        return {}

    all_candidates = []
    # Use a set to keep track of seen candidates to avoid duplicates
    seen_candidates = set()

    # Iterate over all ambiguous terms provided by the slot_manager
    for item in ambiguous_terms:
        # Determine term and scope based on item type (str or ScopedTerm/dict)
        if isinstance(item, str):
            term = item
            scope = None
        elif hasattr(item, "term") and hasattr(item, "scope"):
            term = item.term
            scope = item.scope
        elif isinstance(item, dict):
            term = item.get("term")
            scope = item.get("scope")
        else:
            continue # Skip unknown types

        print(f"Searching for ambiguous term '{term}' with scope '{scope}'...")
        
        # Invoke the tool with both keyword and type_filter
        results = search_ambiguous_term.invoke({"keyword": term, "type_filter": scope})
        
        for candidate in results:
            # Create a unique identifier for the candidate (e.g., a tuple of its values)
            # This prevents adding the exact same item from different searches
            candidate_tuple = (candidate.get('value'), candidate.get('source'))
            if candidate_tuple not in seen_candidates:
                all_candidates.append(candidate)
                seen_candidates.add(candidate_tuple)

    print(f"Found unique candidates: {all_candidates}")

    # Update the state with the aggregated, unique candidates
    return {"candidate_values": all_candidates}