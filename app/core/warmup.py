"""
Eager-load RAG stack at process start so the first realtime turn is not paying
cold-start costs (SentenceTransformer, CrossEncoder, Qdrant round-trip).

Does not change retrieval or generation logic — same models and code paths as
production requests; only runs once before serving traffic.
"""

from __future__ import annotations

import time

from app.core.config import settings
from app.core.logging import get_logger
from app.rag.pipeline import get_rag_pipeline

logger = get_logger(__name__)

# English, >= RERANKER_MIN_WORDS, so production hybrid + rerank path can run when the KB returns hits.
_WARMUP_RETRIEVAL_QUERY = "warmup retrieval test query for apartment pricing"


def warm_rag_stack_sync() -> None:
    """
    Blocking warmup (run via asyncio.to_thread from FastAPI lifespan).
    Logs timing; failures are non-fatal so the API can still boot if Qdrant is down.
    """
    if not settings.RAG_WARMUP_ON_STARTUP:
        logger.info("RAG warmup skipped (RAG_WARMUP_ON_STARTUP=false)")
        return

    t0 = time.perf_counter()
    try:
        pipeline = get_rag_pipeline()

        # Full retrieve path: embed, Qdrant, hybrid, rerank when eligible.
        chunks = pipeline.retriever.retrieve(_WARMUP_RETRIEVAL_QUERY)
        qwords = len(_WARMUP_RETRIEVAL_QUERY.split())

        # retrieve() skips reranker when there are 0 chunks or exactly 1 chunk — but we still
        # want CrossEncoder weights loaded before the first user query.
        explicit_rerank_warmup = False
        if settings.USE_RERANKER:
            ran_rerank_inside_retrieve = (
                len(chunks) >= 2
                and qwords >= settings.RERANKER_MIN_WORDS
            )
            if not ran_rerank_inside_retrieve:
                reranker = pipeline.retriever._get_reranker()
                reranker.predict(
                    [
                        [
                            "warmup query for retrieval",
                            "sample property listing description text",
                        ]
                    ]
                )
                explicit_rerank_warmup = True

        llm_warmup_ms: float | None = None
        if settings.RAG_WARMUP_LLM:
            prov = settings.LLM_PROVIDER.lower().strip()
            has_key = (
                prov == "openai" and bool(settings.OPENAI_API_KEY)
            ) or (prov != "openai" and bool(settings.GEMINI_API_KEY))
            if not has_key:
                logger.debug("LLM warmup skipped (no API key for LLM_PROVIDER)")
            else:
                t_llm = time.perf_counter()
                try:
                    # Grounded path when KB returns hits; otherwise no-context path still warms HTTP/TLS.
                    w_chunks = chunks[: min(2, len(chunks))]
                    pipeline.llm.generate_answer("__warmup__", w_chunks)
                except Exception:
                    logger.exception("LLM warmup failed — first answer may be slower")
                else:
                    llm_warmup_ms = (time.perf_counter() - t_llm) * 1000.0

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        logger.info(
            "RAG warmup finished in %.0f ms (chunks=%d, explicit_rerank_warmup=%s, llm_warmup_ms=%s)",
            elapsed_ms,
            len(chunks),
            explicit_rerank_warmup,
            f"{llm_warmup_ms:.0f}" if llm_warmup_ms is not None else "n/a",
        )
    except Exception:
        logger.exception(
            "RAG warmup failed — first request may be slower until models load"
        )
