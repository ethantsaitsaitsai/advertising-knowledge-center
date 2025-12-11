from nodes.campaign_subgraph.state import CampaignSubState
from tools.search_db import search_ambiguous_term

def search_node(state: CampaignSubState):
    """
    Executes a fuzzy search for the entity.
    Updates internal_thoughts with the result.
    """
    # Ideally, the search term comes from the Router's decision.
    # But since StateGraph passes state, we need to store the router's output in state 
    # OR we re-derive it from the task.
    
    # Let's assume the router stored the decision in a temporary key or we infer it.
    # To keep it simple for LangGraph, let's extract the term from the task 
    # (since the router just decided "we need to search").
    
    task = state["task"]
    # Logic to pick what to search
    term = ""
    if task.filters.get("brands"):
        term = task.filters["brands"][0]
    elif task.filters.get("entities"):
        term = task.filters["entities"][0]
        
    print(f"DEBUG [CampaignSearch] Searching for: {term}")
    
    if not term:
        return {
            "internal_thoughts": ["Search Action: No term found to search."]
        }
        
    suggestions = search_ambiguous_term(term) # Returns a string
    
    thought = f"Search Result for '{term}': {suggestions}"
    print(f"DEBUG [CampaignSearch] {thought}")
    
    return {
        "internal_thoughts": [thought]
    }
