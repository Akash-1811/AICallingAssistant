"""
The answer engine. For each customer turn: check cache, retrieve the most
relevant knowledge, then one streamed LLM call that both classifies the turn
(question / opener / objection / closing) and writes the reply. The INTENT tag
line is stripped here — the rep only ever sees the spoken lines.
"""
from collections.abc import Callable, Iterator
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.core.telemetry import get_tracer
from app.rag.answer_cache import get_answer_cache
from app.rag.llm_factory import get_llm_service
from app.rag.models import RetrievedChunk
from app.rag.prompts import VALID_LIVE_INTENTS
from app.rag.query_cleanup import build_retrieval_query
from app.rag.retriever import RAGRetriever

logger = get_logger(__name__)

# The LLM tags every live turn; if the tag line is missing or malformed we fall
# back to plain Q&A rather than dropping the turn.
_FALLBACK_INTENT = "question"
# If no newline shows up within this many characters, the model ignored the
# output format — treat the whole stream as the answer.
_INTENT_LINE_MAX_CHARS = 120


def extract_intent(line: str) -> str:
    """
    Parse the tag line of a live response ("INTENT: objection", or just
    "objection" when the prompt already printed the label).

    Example::

        extract_intent(" objection")          # -> "objection"
        extract_intent("INTENT: closing")     # -> "closing"
        extract_intent("something odd")       # -> "question"
    """
    value = line.strip().lower()
    if value.startswith("intent"):
        value = value.split(":", 1)[-1].strip()
    return value if value in VALID_LIVE_INTENTS else _FALLBACK_INTENT


def _sources_payload(chunks: list[RetrievedChunk]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    max_len = settings.SOURCE_EXCERPT_MAX_CHARS
    for c in chunks:
        item: dict[str, Any] = {
            "id": c.chunk_id,
            "excerpt": c.excerpt(max_len),
        }
        if c.vector_score is not None:
            item["vector_score"] = round(c.vector_score, 5)
        if c.rerank_score is not None:
            item["rerank_score"] = round(c.rerank_score, 5)
        if settings.EXPOSE_SOURCE_METADATA_TO_CLIENT and c.metadata:
            item["metadata"] = c.metadata
        out.append(item)
    return out


def _skip_answer_cache_for_session(conversation_context: dict[str, Any] | None) -> bool:
    """Session memory changes optimal wording — avoid stale global cache hits."""
    if not conversation_context:
        return False
    pq = (conversation_context.get("previous_query") or "").strip()
    ps = (conversation_context.get("previous_suggestion") or "").strip()
    return bool(pq or ps)


class RAGPipeline:

    def __init__(self):
        self.retriever = RAGRetriever()
        self.llm = get_llm_service()
        self.realtime_llm = get_llm_service(realtime=True)
        self.answer_cache = get_answer_cache(self.retriever.embedder)

    def _retrieve_chunks(
        self,
        query: str,
        *,
        realtime: bool = False,
        conversation_context: dict[str, Any] | None = None,
        retrieval_query: str | None = None,
    ) -> list[RetrievedChunk]:
        # retrieval_query may merge earlier turns for better recall; the plain
        # query (current turn) is what the LLM is asked to answer.
        search_query = build_retrieval_query(
            retrieval_query or query,
            previous_query=(conversation_context or {}).get("previous_query"),
        )
        recall_k = settings.REALTIME_RECALL_K if realtime else settings.RECALL_K
        top_k = settings.REALTIME_TOP_K if realtime else settings.TOP_K
        reranker_min_words = (
            settings.REALTIME_RERANKER_MIN_WORDS
            if realtime
            else settings.RERANKER_MIN_WORDS
        )
        return self.retriever.retrieve(
            search_query,
            recall_k=recall_k,
            top_k=top_k,
            reranker_min_words=reranker_min_words,
        )

    def run(
        self,
        query: str,
        *,
        conversation_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """REST /ask path: plain grounded Q&A, non-streamed."""
        tracer = get_tracer()
        with tracer.start_as_current_span("rag.pipeline.run") as span:
            span.set_attribute("query.length", len(query))

            skip_sess = _skip_answer_cache_for_session(conversation_context)
            if skip_sess:
                span.set_attribute("answer_cache.skipped_for_session_memory", True)
            use_cache = settings.ANSWER_CACHE_ENABLED and not skip_sess
            if use_cache:
                hit = self.answer_cache.get(query)
                if hit is not None:
                    cached, hit_kind = hit
                    span.set_attribute("cache.hit", True)
                    span.set_attribute("cache.layer", hit_kind)
                    return {
                        "query": query,
                        "answer": cached["answer"],
                        "sources": cached.get("sources") or [],
                        "from_cache": True,
                        "cache_hit": hit_kind,
                    }

            span.set_attribute("cache.hit", False)
            try:
                chunks = self._retrieve_chunks(
                    query, realtime=False, conversation_context=conversation_context
                )
            except Exception as e:
                span.record_exception(e)
                logger.exception("RAG retrieval failed: %s", e)
                return {
                    "query": query,
                    "answer": "Search temporarily unavailable. Please try again.",
                    "sources": [],
                    "error": "retrieval_failed",
                    "from_cache": False,
                }
            span.set_attribute("retrieval.chunk_count", len(chunks))
            try:
                answer = self.llm.generate_answer(
                    query, chunks, conversation_context=conversation_context
                )
            except Exception as e:
                span.record_exception(e)
                logger.exception("LLM generation failed: %s", e)
                return {
                    "query": query,
                    "answer": "I could not generate an answer right now. Please try again.",
                    "sources": _sources_payload(chunks),
                    "error": "llm_failed",
                    "from_cache": False,
                }
            out: dict[str, Any] = {
                "query": query,
                "answer": answer,
                "sources": _sources_payload(chunks),
                "from_cache": False,
            }
            if use_cache:
                self.answer_cache.set(query, out)
            return out

    def stream_live(
        self,
        question: str,
        *,
        retrieval_query: str | None = None,
        conversation_context: dict[str, Any] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> Iterator[dict[str, Any]]:
        """
        Realtime path for one customer turn: retrieve, then stream the LLM's
        intent-tagged response. The tag line is stripped here — clients receive
        only the spoken lines, plus the parsed intent on ``answer_done``.
        """
        def cancelled() -> bool:
            return bool(is_cancelled and is_cancelled())

        skip_sess = _skip_answer_cache_for_session(conversation_context)
        use_cache = settings.ANSWER_CACHE_ENABLED and not skip_sess
        if use_cache:
            hit = self.answer_cache.get(question)
            if hit is not None:
                cached, hit_kind = hit
                answer = cached["answer"]
                yield {
                    "type": "answer_delta",
                    "delta": answer,
                    "text": answer,
                    "from_cache": True,
                    "cache_hit": hit_kind,
                }
                yield {
                    "type": "answer_done",
                    "answer": answer,
                    "intent": _FALLBACK_INTENT,
                    "sources": cached.get("sources") or [],
                    "from_cache": True,
                    "cache_hit": hit_kind,
                }
                return

        try:
            chunks = self._retrieve_chunks(
                question,
                realtime=True,
                conversation_context=conversation_context,
                retrieval_query=retrieval_query,
            )
        except Exception as e:
            logger.exception("Realtime RAG retrieval failed: %s", e)
            yield {
                "type": "answer_done",
                "answer": "Search temporarily unavailable. Please try again.",
                "intent": _FALLBACK_INTENT,
                "sources": [],
                "error": "retrieval_failed",
                "from_cache": False,
            }
            return

        if cancelled():
            return

        intent: str | None = None
        tag_buffer = ""
        full_answer = ""
        try:
            for delta in self.realtime_llm.stream_live(
                question, chunks, conversation_context=conversation_context
            ):
                if cancelled():
                    return
                if not delta:
                    continue

                # Absorb the stream until the INTENT tag line is complete.
                if intent is None:
                    tag_buffer += delta
                    newline = tag_buffer.find("\n")
                    if newline < 0:
                        if len(tag_buffer) < _INTENT_LINE_MAX_CHARS:
                            continue
                        intent, spoken = _FALLBACK_INTENT, tag_buffer
                    else:
                        intent = extract_intent(tag_buffer[:newline])
                        spoken = tag_buffer[newline + 1 :].lstrip()
                    if not spoken:
                        continue
                    delta = spoken

                full_answer += delta
                yield {
                    "type": "answer_delta",
                    "delta": delta,
                    "text": full_answer,
                    "from_cache": False,
                }
        except Exception as e:
            logger.exception("Realtime LLM streaming failed: %s", e)
            yield {
                "type": "answer_done",
                "answer": "I could not generate an answer right now. Please try again.",
                "intent": intent or _FALLBACK_INTENT,
                "sources": _sources_payload(chunks),
                "error": "llm_failed",
                "from_cache": False,
            }
            return

        if cancelled():
            return

        out: dict[str, Any] = {
            "type": "answer_done",
            "answer": full_answer.strip(),
            "intent": intent or _FALLBACK_INTENT,
            "sources": _sources_payload(chunks),
            "from_cache": False,
        }
        if use_cache:
            self.answer_cache.set(question, {"answer": out["answer"], "sources": out["sources"]})
        yield out


_pipeline_singleton: RAGPipeline | None = None


def get_rag_pipeline() -> RAGPipeline:
    """Single shared pipeline (heavy models load once per process)."""
    global _pipeline_singleton
    if _pipeline_singleton is None:
        _pipeline_singleton = RAGPipeline()
    return _pipeline_singleton
