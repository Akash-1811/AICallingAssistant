import hashlib
from functools import lru_cache
from typing import List

from sentence_transformers import SentenceTransformer

from app.core.config import settings


class EmbeddingService:

    def __init__(self):
        self.model = SentenceTransformer(settings.EMBEDDING_MODEL)
        # Per-instance LRU cache sized from config.
        # We use a module-level cached helper so the cache survives across calls
        # on the same singleton but is scoped to the embedding model name.
        self._embed_cached = _make_cached_embedder(
            self.model, settings.EMBEDDING_CACHE_SIZE
        )

    def embed(self, text: str) -> List[float]:
        return self._embed_cached(text.strip())


def _make_cached_embedder(model: SentenceTransformer, maxsize: int):
    """
    Returns a cached embedding function bound to a specific model instance.
    We hash long texts to keep the LRU key small; short texts are used verbatim.
    The cache key is the normalised text so minor whitespace differences still hit.
    """

    def _cache_key(text: str) -> str:
        if len(text) > 256:
            return hashlib.sha256(text.encode()).hexdigest()
        return text

    cached: dict = {}  # simple bounded dict (LRU via OrderedDict semantics below)
    from collections import OrderedDict
    store: OrderedDict = OrderedDict()

    def embed(text: str) -> List[float]:
        key = _cache_key(text)
        if key in store:
            store.move_to_end(key)
            return store[key]
        vector: List[float] = model.encode(text).tolist()
        store[key] = vector
        if len(store) > maxsize:
            store.popitem(last=False)  # evict oldest
        return vector

    return embed
