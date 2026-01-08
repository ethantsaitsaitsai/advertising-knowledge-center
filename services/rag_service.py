import re
import os
import traceback
from typing import List, Dict, Any, Optional, Union
from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models
from sentence_transformers import SentenceTransformer
from httpx import ConnectTimeout, ConnectError
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class RagService:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RagService, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.host = os.getenv("QDRANT_HOST")
        self.port = int(os.getenv("QDRANT_PORT"))
        self.collection_name = os.getenv("QDRANT_COLLECTION_NAME")
        print(f"🔌 Initializing Qdrant connection to {self.host}:{self.port}...")
        try:
            self.client = QdrantClient(host=self.host, port=self.port, timeout=10)
            # Test connection immediately
            self.client.get_collections()
            print("✅ Qdrant connection established!")
            self._is_connected = True
        except (ConnectTimeout, ConnectError, Exception) as e:
            print(f"⚠️ Failed to connect to Qdrant: {e}")
            print("⚠️ RAG features will be disabled.")
            self._is_connected = False
            self.client = None

        self._model = None
        self._initialized = True

    @property
    def model(self):
        if self._model is None:
            print("🧠 Loading Embedding Model (intfloat/multilingual-e5-base)...")
            self._model = SentenceTransformer('intfloat/multilingual-e5-base')
        return self._model

    @staticmethod
    def fullwidth_to_halfwidth(text: str) -> str:
        fullwidth = "０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ！＂＃＄％＆＇（）＊＋，－．／：；＜＝＞？＠［＼］＾＿｀｛｜｝～"
        halfwidth = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~"
        return text.translate(str.maketrans(fullwidth, halfwidth))

    @classmethod
    def clean_text(cls, text: str) -> str:
        if not text:
            return ""
        text = cls.fullwidth_to_halfwidth(text)

        text = re.sub(r'\s+', ' ', text)
        text = text.strip()
        return text

    def search(self, query: str, top_k: int = 20, score_threshold: float = 0.90, type_filter: Optional[Union[str, List[str]]] = None) -> List[Dict[str, Any]]:
        """
        Search for similar entities in Qdrant with optional type filtering.
        Args:
            query: The search text
            top_k: Max candidates to check (default increased to 20 to capture all potential matches)
            score_threshold: Minimum similarity score (default 0.90 for even higher precision)
            type_filter: Optional filter for 'type' field (str or list of str)
        """
        if not self._is_connected or self.client is None:
            print("⚠️ Skipping RAG search due to connection failure.")
            return []

        cleaned_query = self.clean_text(query)
        if not cleaned_query:
            cleaned_query = query

        print(f"🔍 RAG Search: '{query}' (Cleaned: '{cleaned_query}') | Filter: {type_filter} | Threshold: {score_threshold}")

        try:
            embedding = self.model.encode(cleaned_query).tolist()

            # Construct Filter if type_filter is provided
            query_filter = None
            if type_filter:
                if isinstance(type_filter, list):
                    # OR logic (should match any of the types)
                    query_filter = qdrant_models.Filter(
                        should=[
                            qdrant_models.FieldCondition(
                                key="type",
                                match=qdrant_models.MatchValue(value=t)
                            ) for t in type_filter
                        ]
                    )
                elif type_filter != "all":
                    # AND logic (single type)
                    query_filter = qdrant_models.Filter(
                        must=[
                            qdrant_models.FieldCondition(
                                key="type",
                                match=qdrant_models.MatchValue(value=type_filter)
                            )
                        ]
                    )

            # Execute Search
            if hasattr(self.client, 'search'):
                results = self.client.search(
                    collection_name=self.collection_name,
                    query_vector=embedding,
                    limit=top_k,
                    score_threshold=score_threshold,
                    query_filter=query_filter
                )
            elif hasattr(self.client, 'query_points'):
                response = self.client.query_points(
                    collection_name=self.collection_name,
                    query=embedding,
                    limit=top_k,
                    score_threshold=score_threshold,
                    query_filter=query_filter
                )
                results = response.points
            else:
                print("❌ QdrantClient has neither 'search' nor 'query_points' method.")
                return []

            formatted_results = []
            for hit in results:
                payload = hit.payload
                formatted_results.append({
                    "value": payload.get("text"),
                    "source": payload.get("column"),
                    "table": payload.get("table"),
                    "filter_type": payload.get("type"),
                    "score": hit.score
                })

            print(f"✅ Found {len(formatted_results)} results above threshold {score_threshold}")
            return formatted_results
        except Exception as e:
            print(f"❌ RAG Search failed: {e}")
            traceback.print_exc()
            return []
