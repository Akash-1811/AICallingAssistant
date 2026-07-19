"""
Redis-backed RAG answer cache with optional in-process semantic matching.

Design goals:
- Fast path: exact normalized query → Redis GET (shared across workers).
- Paraphrase path: cosine similarity vs a bounded ring of recent query embeddings.
- Freshness: TTL + version prefix + Qdrant collection in the key; skip caching
  ungrounded (empty sources) answers by default so KB updates are not masked.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import threading
import time
from collections import OrderedDict, deque
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings
from app.core.logging import get_logger
from app.rag.query_cleanup import normalize_query, semantic_cache_compatible
from app.rag.embedding_service import EmbeddingService

logger = get_logger(__name__)

# After sort by similarity, only check top-N (each may hit Redis); limits worst-case latency.
_SEMANTIC_MAX_CANDIDATES = 8

_answer_cache_singleton: Optional["AnswerCache"] = None
_answer_cache_init_lock = threading.Lock()


def fingerprint(norm: str) -> str:
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def _cosine(a: List[float], b: List[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


class AnswerCache:
    """
    Thread-safe answer cache: Redis when REDIS_URL is set, else in-process with TTL.

    Semantic ring is process-local (not shared across uvicorn workers); exact keys
    in Redis are shared. For multi-worker semantic hits, raise workers=1 or add
    Redis Stack vector search later.
    """

    def __init__(self, embedder: EmbeddingService) -> None:
        self._embedder = embedder
        self._redis = None
        self._redis_failed = False
        self._lock = threading.Lock()
        self._memory: "OrderedDict[str, Tuple[Dict[str, Any], float]]" = OrderedDict()
        self._semantic_ring: deque[Tuple[str, List[float]]] = deque(
            maxlen=settings.ANSWER_CACHE_SEMANTIC_MAX_ENTRIES
        )

    def _get_redis(self):
        if not settings.REDIS_URL or self._redis_failed:
            return None
        if self._redis is None:
            try:
                import redis

                self._redis = redis.Redis.from_url(
                    settings.REDIS_URL,
                    decode_responses=True,
                    socket_connect_timeout=2.0,
                    socket_timeout=2.0,
                )
                self._redis.ping()
                logger.info("Answer cache: Redis connected")
            except Exception as e:
                logger.warning("Answer cache: Redis unavailable (%s); using memory", e)
                self._redis_failed = True
                self._redis = None
                return None
        return self._redis

    def _redis_key(self, fp: str) -> str:
        return (
            f"{settings.ANSWER_CACHE_REDIS_PREFIX}:v{settings.ANSWER_CACHE_VERSION}:"
            f"{settings.QDRANT_COLLECTION}:{fp}"
        )

    def _should_cache(self, result: Dict[str, Any]) -> bool:
        if result.get("error"):
            return False
        if settings.ANSWER_CACHE_SKIP_EMPTY_SOURCES:
            sources = result.get("sources") or []
            if not sources:
                return False
        return True

    def get(
        self, original_query: str
    ) -> Optional[Tuple[Dict[str, Any], str]]:
        """
        Returns (stored_payload, hit_kind) where hit_kind is 'exact' or 'semantic',
        or None on miss. Payload contains answer + sources only (no from_cache).
        """
        if not settings.ANSWER_CACHE_ENABLED:
            return None
        norm = normalize_query(original_query)
        if len(norm) < 3:
            return None
        fp = fingerprint(norm)

        with self._lock:
            payload = self._get_exact_unlocked(fp)
        if payload is not None:
            return payload, "exact"

        if not settings.ANSWER_CACHE_SEMANTIC_ENABLED:
            return None

        with self._lock:
            ring_empty = not self._semantic_ring
        if ring_empty:
            return None

        try:
            q_emb = self._embedder.embed(norm)
        except Exception as e:
            logger.warning("Answer cache: embed for semantic lookup failed: %s", e)
            return None

        with self._lock:
            candidates = self._semantic_candidates_unlocked(q_emb)
            for fp, sim in candidates:
                payload = self._get_exact_unlocked(fp)
                if payload is None:
                    continue
                cached_norm = payload.get("query_norm")
                if not semantic_cache_compatible(norm, cached_norm):
                    logger.debug(
                        "Answer cache: semantic skip (BHK scope mismatch) sim=%.3f",
                        sim,
                    )
                    continue
                return payload, "semantic"
        return None

    def _semantic_candidates_unlocked(self, q_emb: List[float]) -> List[Tuple[str, float]]:
        """Fingerprints at or above threshold, best similarity first."""
        threshold = settings.ANSWER_CACHE_SEMANTIC_THRESHOLD
        ranked: List[Tuple[str, float]] = []
        for fp, emb in self._semantic_ring:
            sim = _cosine(q_emb, emb)
            if sim >= threshold:
                ranked.append((fp, sim))
        ranked.sort(key=lambda x: -x[1])
        return ranked[:_SEMANTIC_MAX_CANDIDATES]

    def _get_exact_unlocked(self, fp: str) -> Optional[Dict[str, Any]]:
        r = self._get_redis()
        if r:
            try:
                raw = r.get(self._redis_key(fp))
            except Exception as e:
                logger.warning("Answer cache: Redis GET failed: %s", e)
                raw = None
            if raw:
                try:
                    return json.loads(raw)
                except json.JSONDecodeError:
                    logger.warning("Answer cache: corrupt JSON for fp=%s…", fp[:12])
            return None

        now = time.time()
        if fp in self._memory:
            payload, exp = self._memory[fp]
            if now > exp:
                del self._memory[fp]
                return None
            self._memory.move_to_end(fp)
            return dict(payload)
        return None

    def _memory_put(
        self, fp: str, payload: Dict[str, Any], expires_at: float
    ) -> None:
        max_n = settings.ANSWER_CACHE_MAX_MEMORY_ENTRIES
        self._memory[fp] = (payload, expires_at)
        self._memory.move_to_end(fp)
        while len(self._memory) > max_n:
            self._memory.popitem(last=False)

    def set(self, original_query: str, result: Dict[str, Any]) -> None:
        if not settings.ANSWER_CACHE_ENABLED:
            return
        if not self._should_cache(result):
            return
        norm = normalize_query(original_query)
        if len(norm) < 3:
            return
        fp = fingerprint(norm)

        payload = {
            "answer": result["answer"],
            "sources": result.get("sources") or [],
            "query_norm": norm,
        }
        ttl = int(settings.ANSWER_CACHE_TTL_SECONDS)
        raw_json = json.dumps(payload, separators=(",", ":"))

        r = self._get_redis()
        if r:
            try:
                r.setex(self._redis_key(fp), ttl, raw_json)
            except Exception as e:
                logger.warning("Answer cache: Redis SET failed: %s", e)

        try:
            emb = self._embedder.embed(norm)
        except Exception as e:
            logger.debug("Answer cache: embed for ring failed: %s", e)
            emb = None

        with self._lock:
            now = time.time()
            self._memory_put(fp, dict(payload), now + ttl)

            if emb is not None and settings.ANSWER_CACHE_SEMANTIC_ENABLED:
                self._semantic_ring.appendleft((fp, emb))

    def close(self) -> None:
        if self._redis is None:
            return
        try:
            self._redis.close()
        except Exception as e:
            logger.warning("Answer cache: Redis close: %s", e)
        finally:
            self._redis = None


def get_answer_cache(embedder: EmbeddingService) -> AnswerCache:
    global _answer_cache_singleton
    with _answer_cache_init_lock:
        if _answer_cache_singleton is None:
            _answer_cache_singleton = AnswerCache(embedder)
        return _answer_cache_singleton


def close_answer_cache() -> None:
    global _answer_cache_singleton
    with _answer_cache_init_lock:
        if _answer_cache_singleton is not None:
            _answer_cache_singleton.close()
            _answer_cache_singleton = None
