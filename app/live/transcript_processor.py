"""
The main live loop: one iteration per finished customer sentence. Gates out
noise ("okay", "thank you"), cancels stale suggestions when the topic moves on,
and streams each worthwhile turn through the RAG pipeline to the rep's screen.
Flow position: the bridge between transcription and answering.
"""
import asyncio
import threading
import time
from itertools import count
from typing import Any, List

from app.core.config import settings
from app.core.logging import get_logger
from app.live.conversation_manager import (
    conversation_manager,
)
from app.live.turn_gate import is_closing_pleasantry
from app.rag.pipeline import get_rag_pipeline
from app.rag.query_cleanup import (
    dominant_language_hint,
    normalize_live_query,
    queries_are_near_duplicate,
)
from app.live.call_recorder import OutboundQueue
from app.live.transcript_types import TranscriptSegment

logger = get_logger(__name__)

_DUPLICATE_NUDGE = (
    "You already covered this point — keep it brief: acknowledge briefly, then ask "
    "one specific follow-up (budget, preferred location, or timeline)."
)


def _word_count(text: str) -> int:
    return len(text.split())


class TranscriptProcessor:

    def __init__(self):
        self.pipeline = get_rag_pipeline()
        self._generation_counter = count(1)
        self._latest_generation: dict[str, int] = {}

    async def process_stream(
        self,
        session_id: str,
        transcript_queue: asyncio.Queue,
        outbound_queue: OutboundQueue,
    ):
        """
        Consume transcript segment batches and stream AI output back incrementally.
        """
        current_task: asyncio.Task | None = None
        current_generation_id: int | None = None
        current_cancel: threading.Event | None = None

        while True:
            segments: List[TranscriptSegment] = await transcript_queue.get()

            if not segments:
                continue

            (
                _raw_ctx,
                focused_query,
                speakers_seen,
                lead,
            ) = await conversation_manager.record_turn(
                session_id, segments
            )

            await outbound_queue.put(
                {
                    "type": "session_status",
                    "session_id": session_id,
                    "speakers": speakers_seen,
                    "lead_speaker_id": lead,
                }
            )

            if lead is None:
                logger.debug(
                    "session=%s no lead speaker yet (speakers=%s)",
                    session_id,
                    speakers_seen,
                )
                continue

            lead_only_batch = " ".join(
                s.text for s in segments if int(s.speaker) == lead
            ).strip()
            if _word_count(lead_only_batch) < settings.TRANSCRIPT_MIN_WORDS:
                logger.debug(
                    "session=%s skipping short lead-only turn (%d words): %r",
                    session_id,
                    _word_count(lead_only_batch),
                    lead_only_batch,
                )
                continue

            if _word_count(focused_query) < settings.TRANSCRIPT_MIN_WORDS:
                logger.debug(
                    "session=%s focused_query too short after extraction: %r",
                    session_id,
                    focused_query,
                )
                continue

            # The question put to the LLM is ONLY the newest lead speech;
            # focused_query (which may merge earlier turns) is for retrieval.
            question = normalize_live_query(lead_only_batch)

            if is_closing_pleasantry(question):
                logger.debug(
                    "session=%s skipping closing/acknowledgement turn: %r",
                    session_id,
                    question,
                )
                continue

            if current_task is not None and not current_task.done():
                if current_cancel is not None:
                    current_cancel.set()
                if current_generation_id is not None:
                    await outbound_queue.put(
                        {
                            "type": "answer_cancelled",
                            "session_id": session_id,
                            "generation_id": current_generation_id,
                        }
                    )

            generation_id = next(self._generation_counter)
            self._latest_generation[session_id] = generation_id
            cancel_event = threading.Event()
            current_generation_id = generation_id
            current_cancel = cancel_event

            current_task = asyncio.create_task(
                self._handle_turn(
                    session_id,
                    question,
                    focused_query,
                    outbound_queue,
                    generation_id=generation_id,
                    cancel_event=cancel_event,
                )
            )

    async def _handle_turn(
        self,
        session_id: str,
        question: str,
        focused_query: str,
        outbound_queue: OutboundQueue,
        *,
        generation_id: int,
        cancel_event: threading.Event,
    ):
        started_at = time.perf_counter()
        try:
            retrieval_query = normalize_live_query(focused_query) or question
            rag_ctx = await conversation_manager.get_rag_context(session_id)
            lang_hint = dominant_language_hint(question)
            conversation_context = {
                "previous_query": rag_ctx.get("last_query"),
                "previous_suggestion": rag_ctx.get("last_suggestion"),
                "recent_lead_snippet": rag_ctx.get("recent_lead_snippet"),
                "language_hint": lang_hint,
            }

            if queries_are_near_duplicate(question, rag_ctx.get("last_query")):
                logger.debug(
                    "session=%s generation=%s near-duplicate query vs last — fast path",
                    session_id,
                    generation_id,
                )
                if not self._is_generation_active(session_id, generation_id, cancel_event):
                    return
                answer = _DUPLICATE_NUDGE
                await outbound_queue.put(
                    {
                        "type": "answer_started",
                        "session_id": session_id,
                        "generation_id": generation_id,
                        "query": question,
                    }
                )
                await conversation_manager.set_last_turn(
                    session_id, question, answer
                )
                await outbound_queue.put(
                    {
                        "type": "answer_done",
                        "text": answer,
                        "session_id": session_id,
                        "generation_id": generation_id,
                        "query": question,
                        "from_cache": False,
                        "duplicate_skip": True,
                        "latency_ms": int((time.perf_counter() - started_at) * 1000),
                    }
                )
                logger.info(
                    "session=%s generation=%s duplicate fast-path completed in %.0fms",
                    session_id,
                    generation_id,
                    (time.perf_counter() - started_at) * 1000.0,
                )
                return

            logger.debug(
                "session=%s generation=%s running RAG | query=%r",
                session_id,
                generation_id,
                question,
            )

            if not self._is_generation_active(session_id, generation_id, cancel_event):
                return

            await outbound_queue.put(
                {
                    "type": "answer_started",
                    "session_id": session_id,
                    "generation_id": generation_id,
                    "query": question,
                }
            )

            event_queue: asyncio.Queue[Any] = asyncio.Queue()
            loop = asyncio.get_running_loop()
            sentinel = object()

            def publish_from_thread(item: Any) -> None:
                if cancel_event.is_set():
                    return
                loop.call_soon_threadsafe(event_queue.put_nowait, item)

            def worker() -> None:
                try:
                    events = self.pipeline.stream_live(
                        question,
                        retrieval_query=retrieval_query,
                        conversation_context=conversation_context,
                        is_cancelled=cancel_event.is_set,
                    )
                    for item in events:
                        if cancel_event.is_set():
                            break
                        publish_from_thread(item)
                except Exception as e:
                    logger.exception(
                        "session=%s generation=%s worker stream failed: %s",
                        session_id,
                        generation_id,
                        e,
                    )
                    publish_from_thread(
                        {
                            "type": "answer_done",
                            "answer": "Assistant hit an error processing this turn.",
                            "sources": [],
                            "error": "llm_failed",
                            "from_cache": False,
                        }
                    )
                finally:
                    loop.call_soon_threadsafe(event_queue.put_nowait, sentinel)

            threading.Thread(
                target=worker,
                name=f"rag-stream-{session_id[:8]}-{generation_id}",
                daemon=True,
            ).start()

            first_delta_at: float | None = None
            while True:
                try:
                    item = await asyncio.wait_for(
                        event_queue.get(),
                        timeout=settings.RAG_TIMEOUT_SECONDS,
                    )
                except asyncio.TimeoutError:
                    cancel_event.set()
                    if self._is_generation_current(session_id, generation_id):
                        await outbound_queue.put(
                            {
                                "type": "error",
                                "message": "Response took too long — listening for next question.",
                                "session_id": session_id,
                            }
                        )
                    logger.warning(
                        "session=%s generation=%s timed out after %.1fs",
                        session_id,
                        generation_id,
                        settings.RAG_TIMEOUT_SECONDS,
                    )
                    return

                if item is sentinel:
                    return
                if not self._is_generation_active(session_id, generation_id, cancel_event):
                    continue

                item_type = item.get("type")
                if item_type == "answer_delta":
                    if first_delta_at is None:
                        first_delta_at = time.perf_counter()
                        logger.info(
                            "session=%s generation=%s first_answer_chunk_ms=%.0f",
                            session_id,
                            generation_id,
                            (first_delta_at - started_at) * 1000.0,
                        )
                    await outbound_queue.put(
                        {
                            "type": "answer_delta",
                            "delta": item.get("delta", ""),
                            "text": item.get("text", ""),
                            "session_id": session_id,
                            "generation_id": generation_id,
                            "query": question,
                            "from_cache": item.get("from_cache", False),
                            "cache_hit": item.get("cache_hit"),
                        }
                    )
                    continue

                if item_type == "answer_done":
                    answer = (item.get("answer") or "").strip()
                    if answer:
                        await conversation_manager.set_last_turn(
                            session_id, question, answer
                        )
                    payload = {
                        "type": "answer_done",
                        "text": answer,
                        "session_id": session_id,
                        "generation_id": generation_id,
                        "query": question,
                        "intent": item.get("intent"),
                        "error": item.get("error"),
                        "from_cache": item.get("from_cache", False),
                        "cache_hit": item.get("cache_hit"),
                        "duplicate_skip": item.get("duplicate_skip", False),
                        "latency_ms": int((time.perf_counter() - started_at) * 1000),
                    }
                    if settings.INCLUDE_SOURCES_IN_WS and item.get("sources"):
                        payload["sources"] = item.get("sources") or []
                    await outbound_queue.put(payload)
                    logger.info(
                        "session=%s generation=%s completed in %.0fms (first_chunk_ms=%s)",
                        session_id,
                        generation_id,
                        (time.perf_counter() - started_at) * 1000.0,
                        (
                            f"{(first_delta_at - started_at) * 1000.0:.0f}"
                            if first_delta_at is not None
                            else "n/a"
                        ),
                    )
                    return

        except Exception as e:
            logger.exception(
                "Transcript processing failed session=%s generation=%s: %s",
                session_id,
                generation_id,
                e,
            )
            await outbound_queue.put(
                {
                    "type": "error",
                    "message": "Assistant hit an error processing this turn.",
                    "session_id": session_id,
                }
            )

    def _is_generation_current(self, session_id: str, generation_id: int) -> bool:
        return self._latest_generation.get(session_id) == generation_id

    def _is_generation_active(
        self,
        session_id: str,
        generation_id: int,
        cancel_event: threading.Event,
    ) -> bool:
        return self._is_generation_current(session_id, generation_id) and not cancel_event.is_set()
