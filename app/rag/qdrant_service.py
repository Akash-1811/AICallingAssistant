"""
Thin client for the Qdrant vector database — searches the knowledge-base
vectors. Flow position: called by the retriever. (Writing/ingest is done by
app/rag/knowledge.py and app/scripts/ingest_data.py with their own clients.)
"""

from qdrant_client import QdrantClient

from app.core.config import settings


class QdrantService:

    def __init__(self):
        self.client = QdrantClient(settings.QDRANT_URL)

    def search(self, vector, limit: int | None = None):
        return self.client.search(
            collection_name=settings.QDRANT_COLLECTION,
            query_vector=vector,
            limit=limit if limit is not None else settings.RECALL_K,
        )
