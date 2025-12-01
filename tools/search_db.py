from typing import List
from langchain.tools import tool
from utils.rag_service import RagService

@tool
def search_ambiguous_term(keyword: str) -> List[dict]:
    """
    Uses RAG to search for ambiguous terms across brands, agencies, campaigns, industries, and keywords.
    Returns a list of candidates with their types and source columns.
    """
    rag = RagService()
    results = rag.search(keyword, top_k=5)
    
    candidates = []
    for res in results:
        candidates.append({
            "value": res["value"],
            "source": res["source_col"], # Map to 'source' to match entity_search_node expectation
            "table": res["table"],
            "filter_type": res["filter_type"],
            "score": res["score"]
        })
        
    return candidates