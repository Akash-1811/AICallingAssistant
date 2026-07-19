"""
Thin client for the Qdrant vector database — stores and searches the
knowledge-base vectors. Flow position: called by the retriever.
"""

from qdrant_client import QdrantClient

from app.core.config import settings


class QdrantService:

    def __init__(self):
        self.client = QdrantClient(settings.QDRANT_URL)

    def create_collection(self):
        self.client.recreate_collection(
            collection_name=settings.QDRANT_COLLECTION,
            vectors_config={
                "size": 384,
                "distance": "Cosine",
            },
        )

    def upsert(self, points):
        self.client.upsert(
            collection_name=settings.QDRANT_COLLECTION,
            points=points,
        )

    def search(self, vector, limit: int | None = None):
        lim = limit if limit is not None else settings.RECALL_K
        return self.client.search(
            collection_name=settings.QDRANT_COLLECTION,
            query_vector=vector,
            limit=lim,
        )
