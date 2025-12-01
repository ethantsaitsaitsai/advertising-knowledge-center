from typing import List, Optional
from langchain.tools import tool
from utils.rag_service import RagService

@tool
def search_ambiguous_term(keyword: str, type_filter: Optional[str] = None) -> List[dict]:
    """
    Uses RAG to search for ambiguous terms across brands, agencies, campaigns, industries, and keywords.
    Returns a list of candidates with their types and source columns.
    
    Args:
        keyword: The term to search for.
        type_filter: Optional. If provided (e.g., 'agencies', 'brands', 'campaign_names'), 
                     restricts search to that specific entity type.
    """
    rag = RagService()
    # Use default top_k (20) and score_threshold (0.80) from RagService
    results = rag.search(keyword, type_filter=type_filter)
    
    candidates = []
    for res in results:
        candidates.append({
            "value": res["value"],
            "source": res.get("source", res.get("source_col")), 
            "table": res["table"],
            "filter_type": res["filter_type"],
            "score": res["score"]
        })
        
    return candidates
