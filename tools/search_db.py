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
        # The rag_service returns keys: value, source, table, filter_type, score
        candidates.append({
            "value": res["value"],
            # Map the 'source' from rag_service directly to 'source' here.
            # In rag_service.py, the key is 'source' (mapped from payload['column']).
            "source": res.get("source", res.get("source_col")), 
            "table": res["table"],
            "filter_type": res["filter_type"],
            "score": res["score"]
        })
        
    return candidates
