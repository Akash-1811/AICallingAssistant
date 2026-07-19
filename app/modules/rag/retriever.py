import time
from typing import Any, List, Optional

from sentence_transformers import CrossEncoder

from app.core.config import settings
from app.core.loggin import get_logger
from app.core.telemetry import get_tracer
from app.modules.rag.models import RetrievedChunk
from app.services.embedding_service import EmbeddingService
from app.services.qdrant_service import QdrantService

logger = get_logger(__name__)

_LOCATION_QUERY_WORDS = frozenset(
    {
        "where", "located", "location", "address", "area", "near", "landmark",
        "connectivity", "kahan", "कहाँ", "कहां", "लोकेशन", "पता",
    }
)


def _keyword_overlap(query: str, text: str) -> float:
    qs = set(query.lower().split())
    ts = set(text.lower().split())
    if not qs:
        return 0.0
    return len(qs & ts) / len(qs)


def _metadata_rank_adjustment(chunk: RetrievedChunk) -> float:
    """Prefer answer/pitch passages over stored customer questions."""
    meta = chunk.metadata or {}
    if not meta:
        return 0.0
    intent = str(meta.get("intent") or "").lower()
    if intent.endswith("_query") or intent.endswith("_doubt"):
        return -0.15
    if any(
        intent.endswith(suffix)
        for suffix in ("_answer", "_handle", "_pitch", "_response", "_justification")
    ):
        return 0.1
    return 0.0


def _chunk_from_payload(r: Any) -> Optional[RetrievedChunk]:
    payload = r.payload or {}
    text = payload.get("text")
    if not text:
        return None
    raw_id = payload.get("id")
    chunk_id = str(raw_id) if raw_id is not None else None
    meta = payload.get("metadata")
    if meta is not None and not isinstance(meta, dict):
        meta = {}
    return RetrievedChunk(
        text=text,
        chunk_id=chunk_id,
        vector_score=float(getattr(r, "score", 0.0) or 0.0),
        metadata=meta or {},
    )


class RAGRetriever:

    def __init__(self):
        self.embedder = EmbeddingService()
        self.qdrant = QdrantService()
        self._reranker: Optional[CrossEncoder] = None

    def _get_reranker(self) -> CrossEncoder:
        if self._reranker is None:
            self._reranker = CrossEncoder(settings.RERANKER_MODEL)
        return self._reranker

    def _hybrid_scored_chunks(
        self,
        query: str,
        results: List[Any],
    ) -> List[RetrievedChunk]:
        w = settings.HYBRID_KEYWORD_WEIGHT
        scored: List[tuple[float, RetrievedChunk]] = []
        for r in results:
            payload = r.payload or {}
            text = payload.get("text")
            if not text:
                continue
            base = float(getattr(r, "score", 0.0) or 0.0)
            if w > 0:
                kw = _keyword_overlap(query, text)
                combined = (1.0 - w) * base + w * kw
            else:
                combined = base
            ch = _chunk_from_payload(r)
            if ch:
                combined += _metadata_rank_adjustment(ch)
                scored.append((combined, ch))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [c for _, c in scored]

    def retrieve(
        self,
        query: str,
        *,
        recall_k: Optional[int] = None,
        top_k: Optional[int] = None,
        reranker_min_words: Optional[int] = None,
    ) -> List[RetrievedChunk]:
        tracer = get_tracer()
        with tracer.start_as_current_span("rag.retrieve") as span:
            recall = recall_k if recall_k is not None else settings.RECALL_K
            limit = top_k if top_k is not None else settings.TOP_K
            min_words = (
                reranker_min_words
                if reranker_min_words is not None
                else settings.RERANKER_MIN_WORDS
            )
            span.set_attribute("recall_k", recall)
            span.set_attribute("top_k", limit)
            # The embedding model is multilingual — Hindi/Marathi queries search the
            # English KB directly, no translation step.
            search_query = query.strip() or query
            span.set_attribute("retrieval.search_query_len", len(search_query))
            t0 = time.perf_counter()
            with tracer.start_as_current_span("rag.embed_query"):
                t_embed = time.perf_counter()
                vector = self.embedder.embed(search_query)
                embed_ms = (time.perf_counter() - t_embed) * 1000.0
            with tracer.start_as_current_span("rag.qdrant_search"):
                t_qdrant = time.perf_counter()
                results = self.qdrant.search(vector, limit=recall)
                qdrant_ms = (time.perf_counter() - t_qdrant) * 1000.0
            t_hybrid = time.perf_counter()
            chunks = self._hybrid_scored_chunks(search_query, results)
            hybrid_ms = (time.perf_counter() - t_hybrid) * 1000.0
            if not chunks:
                span.set_attribute("result.count", 0)
                logger.info(
                    "RAG retrieve timings | qlen=%d embed=%.0fms qdrant=%.0fms hybrid=%.0fms total=%.0fms chunks=0",
                    len(search_query),
                    embed_ms,
                    qdrant_ms,
                    hybrid_ms,
                    (time.perf_counter() - t0) * 1000.0,
                )
                return []

            query_words = len(search_query.split())
            has_location_intent = bool(
                set(search_query.lower().split()) & _LOCATION_QUERY_WORDS
            )
            # Skip reranker for very short queries — unless the turn is clearly about location.
            skip_reranker = (
                not settings.USE_RERANKER
                or len(chunks) == 1
                or (query_words < min_words and not has_location_intent)
            )
            if skip_reranker:
                out = chunks[:limit]
                span.set_attribute("result.count", len(out))
                span.set_attribute("reranker.skipped", True)
                logger.info(
                    "RAG retrieve timings | qlen=%d embed=%.0fms qdrant=%.0fms hybrid=%.0fms rerank=skipped total=%.0fms chunks=%d",
                    len(search_query),
                    embed_ms,
                    qdrant_ms,
                    hybrid_ms,
                    (time.perf_counter() - t0) * 1000.0,
                    len(out),
                )
                return out

            try:
                with tracer.start_as_current_span("rag.rerank"):
                    t_rerank = time.perf_counter()
                    reranker = self._get_reranker()
                    texts = [c.text for c in chunks]
                    pairs = [[search_query, t] for t in texts]
                    scores = reranker.predict(pairs)
                    for c, s in zip(chunks, scores):
                        c.rerank_score = float(s)
                    ranked = sorted(zip(scores, chunks), key=lambda x: x[0], reverse=True)
                    out = [c for _, c in ranked[:limit]]
                    rerank_ms = (time.perf_counter() - t_rerank) * 1000.0
                span.set_attribute("result.count", len(out))
                logger.info(
                    "RAG retrieve timings | qlen=%d embed=%.0fms qdrant=%.0fms hybrid=%.0fms rerank=%.0fms total=%.0fms chunks=%d",
                    len(search_query),
                    embed_ms,
                    qdrant_ms,
                    hybrid_ms,
                    rerank_ms,
                    (time.perf_counter() - t0) * 1000.0,
                    len(out),
                )
                return out
            except Exception as e:
                span.record_exception(e)
                logger.warning("Reranker failed, using hybrid/vector order: %s", e)
                out = chunks[:limit]
                span.set_attribute("result.count", len(out))
                logger.info(
                    "RAG retrieve timings | qlen=%d embed=%.0fms qdrant=%.0fms hybrid=%.0fms rerank=failed total=%.0fms chunks=%d",
                    len(search_query),
                    embed_ms,
                    qdrant_ms,
                    hybrid_ms,
                    (time.perf_counter() - t0) * 1000.0,
                    len(out),
                )
                return out
