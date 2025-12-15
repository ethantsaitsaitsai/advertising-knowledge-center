from nodes.campaign_subgraph.state import CampaignSubState
from tools.search_db import search_ambiguous_term

def search_node(state: CampaignSubState):
    """
    Executes a fuzzy search for the entity.
    Updates internal_thoughts with the result.
    """
    task = state["task"]
    # Logic to pick what to search
    # We prefer 'brands' as it's the most common "Entity" bucket
    term = ""
    if task.filters.get("brands"):
        term = task.filters["brands"][0]
    elif task.filters.get("entities"):
        term = task.filters["entities"][0]
    # Fallback: check if 'campaign_names' has something
    elif task.filters.get("campaign_names"):
        term = task.filters["campaign_names"][0]
        
    print(f"DEBUG [CampaignSearch] Searching for: {term}")
    
    if not term:
        return {
            "internal_thoughts": ["Search Action: No term found to search."],
            "search_results": []
        }
        
    suggestions = search_ambiguous_term(term) # Returns a list of strings
    
    thought = f"Search Result for '{term}': {suggestions}"
    print(f"DEBUG [CampaignSearch] {thought}")
    
    return {
        "internal_thoughts": [thought],
        "search_results": suggestions
    }