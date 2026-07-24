"""
Records live WebSocket events into the database and finalizes calls on disconnect.

The realtime handler wraps the outbound queue with ``RecordingQueue``. Events are
forwarded to the browser immediately; persistence happens on a background writer
task so database latency never delays what the rep sees.

Example::

    outbound = RecordingQueue(client_queue, session_id)
    await start_conversation(session_id, audio_channels=2)
    # … call runs …
    await outbound.flush_and_close()
    if await finalize_conversation(session_id):
        asyncio.create_task(schedule_post_call_analysis(session_id))
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import select

from app.core.logging import get_logger
from app.storage.call_store import (
    Conversation,
    SuggestionRow,
    TranscriptSegmentRow,
    database_enabled,
    get_db,
)

logger = get_logger(__name__)


def speaker_role(speaker_id: int, lead_speaker_id: int | None) -> str:
    """
    Map a speaker channel to ``rep``, ``prospect``, or ``unknown``.

    The lead channel is the prospect/client; every other channel is the
    salesperson.

    Example::

        speaker_role(speaker_id=1, lead_speaker_id=1)  # -> "prospect"
        speaker_role(speaker_id=0, lead_speaker_id=1)  # -> "rep"
    """
    if lead_speaker_id is None:
        return "unknown"
    return "prospect" if speaker_id == lead_speaker_id else "rep"


def resolve_lead_speaker_id(row: Conversation) -> int | None:
    """
    The conversation row's `lead_speaker_id` is set from a `session_status`
    event processed on a separate queue from `transcript_final` — so for the
    very first segment of every call, it can still be unset even though we
    already know the answer: channel 1 is the customer on any real two-channel
    call, no need to wait on anything. Only fall back to "not yet known" for a
    genuinely single-channel call, where there truly is nothing to resolve
    until we've heard the one channel that exists.
    """
    if row.lead_speaker_id is not None:
        return row.lead_speaker_id
    return 1 if row.audio_channels >= 2 else None


class OutboundQueue(Protocol):
    """Anything that can receive WebSocket payloads (client queue or recording wrapper)."""

    async def put(self, item: Any) -> None: ...


class RecordingQueue:
    """
    Forwards WebSocket payloads to the client immediately and persists them from a
    background writer task. The writer processes events in order, so transcript and
    suggestion rows keep their insertion order.

    Call ``flush_and_close()`` when the session ends so every event is persisted
    before post-call analysis reads the conversation.

    Example::

        client_queue: asyncio.Queue = asyncio.Queue()
        outbound = RecordingQueue(client_queue, conversation_id)
        await outbound.put({"type": "transcript_final", "text": "Hello", "speaker": 0})
        await outbound.flush_and_close()
    """

    _CLOSE = object()

    def __init__(self, client_queue: asyncio.Queue, conversation_id: str):
        self.client_queue = client_queue
        self.conversation_id = conversation_id
        self._pending: asyncio.Queue = asyncio.Queue()
        self._writer: asyncio.Task | None = None
        if database_enabled():
            self._writer = asyncio.create_task(
                self._drain(), name=f"recorder-{conversation_id[:8]}"
            )

    async def put(self, item: dict[str, Any]) -> None:
        await self.client_queue.put(item)
        if self._writer is not None:
            self._pending.put_nowait(item)

    async def flush_and_close(self) -> None:
        """Persist everything still queued, then stop the writer."""
        if self._writer is None:
            return
        self._pending.put_nowait(self._CLOSE)
        await self._writer
        self._writer = None

    async def _drain(self) -> None:
        while True:
            item = await self._pending.get()
            if item is self._CLOSE:
                return
            try:
                await handle_ws_event(self.conversation_id, item)
            except Exception as e:
                logger.warning(
                    "call_recorder failed conversation=%s type=%s: %s",
                    self.conversation_id,
                    item.get("type"),
                    e,
                )


async def start_conversation(
    conversation_id: str,
    *,
    audio_channels: int = 1,
    call_language: str = "multi",
    rep_label: str | None = None,
) -> None:
    """
    Insert a new ``live`` conversation row when a WebSocket session opens.

    Idempotent: does nothing if the row already exists.

    Example::

        await start_conversation("f47ac10b-58cc-4372-a567-0e02b2c3d479", audio_channels=1)
    """
    if not database_enabled():
        return
    async with get_db() as session:
        existing = await session.get(Conversation, conversation_id)
        if existing is not None:
            return
        session.add(
            Conversation(
                id=conversation_id,
                status="live",
                audio_channels=audio_channels,
                started_at=datetime.now(UTC),
                rep_label=rep_label,
                extra={"call_language": call_language},
            )
        )
        await session.commit()


async def attach_audio_recording(
    conversation_id: str,
    *,
    wav_path: str,
    bytes_written: int,
) -> None:
    """Persist audio recording metadata on the conversation row."""
    if not database_enabled():
        return
    async with get_db() as session:
        row = await session.get(Conversation, conversation_id)
        if row is None:
            return
        row.extra = {
            **(row.extra or {}),
            "audio_wav_path": wav_path,
            "audio_bytes": int(bytes_written),
            "audio_mime": "audio/wav",
        }
        await session.commit()


async def handle_ws_event(conversation_id: str, event: dict[str, Any]) -> None:
    """
    Route one outbound WebSocket event to the appropriate persistence handler.

    Supported types: ``transcript_final``, ``session_status``, ``answer_done``.
    Other types are ignored.

    Example::

        await handle_ws_event(cid, {
            "type": "transcript_final",
            "text": "What is the price for 3BHK?",
            "speaker": 1,
            "start_ms": 12000,
            "end_ms": 15500,
        })
    """
    event_type = event.get("type")
    if event_type == "transcript_final":
        await save_transcript_segment(conversation_id, event)
    elif event_type == "session_status":
        await update_lead_speaker(conversation_id, event.get("lead_speaker_id"))
    elif event_type == "answer_done":
        await save_suggestion(conversation_id, event)


async def update_lead_speaker(conversation_id: str, lead: Any) -> None:
    """
    Store which speaker channel is the prospect (lead).

    Example::

        await update_lead_speaker(cid, lead=1)
    """
    lead_id = parse_optional_int(lead)
    if lead_id is None:
        return
    async with get_db() as session:
        row = await session.get(Conversation, conversation_id)
        if row is None:
            return
        row.lead_speaker_id = lead_id
        await session.commit()


def parse_optional_int(value: Any) -> int | None:
    """
    Parse an optional integer from a WebSocket payload field.

    Example::

        parse_optional_int("15500")  # -> 15500
        parse_optional_int("bad")    # -> None
    """
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


async def save_transcript_segment(conversation_id: str, event: dict[str, Any]) -> None:
    """
    Append one finalized transcript line to the conversation.

    Example::

        await save_transcript_segment(cid, {
            "type": "transcript_final",
            "text": "We are looking at Goregaon.",
            "speaker": 1,
            "start_ms": 5000,
            "end_ms": 7200,
        })
    """
    text = (event.get("text") or "").strip()
    if not text:
        return
    try:
        speaker_id = int(event.get("speaker", 0))
    except (TypeError, ValueError):
        speaker_id = 0

    async with get_db() as session:
        row = await session.get(Conversation, conversation_id)
        if row is None:
            return
        session.add(
            TranscriptSegmentRow(
                conversation_id=conversation_id,
                speaker_id=speaker_id,
                role=speaker_role(speaker_id, resolve_lead_speaker_id(row)),
                start_ms=parse_optional_int(event.get("start_ms")),
                end_ms=parse_optional_int(event.get("end_ms")),
                text=text,
                word_count=len(text.split()),
            )
        )
        await session.commit()


async def save_suggestion(conversation_id: str, event: dict[str, Any]) -> None:
    """
    Store one completed AI suggestion and its trigger query.

    ``latency_ms`` is measured by the transcript processor and carried on the event.

    Example::

        await save_suggestion(cid, {
            "type": "answer_done",
            "text": "Mention the 3BHK starting at 1.2 Cr…",
            "query": "price for 3bhk",
            "generation_id": 3,
            "latency_ms": 1180,
            "from_cache": False,
        })
    """
    answer = (event.get("text") or "").strip()
    if not answer:
        return

    generation_id = event.get("generation_id")
    latency_ms = parse_optional_int(event.get("latency_ms"))

    async with get_db() as session:
        row = await session.get(Conversation, conversation_id)
        if row is None:
            return
        session.add(
            SuggestionRow(
                conversation_id=conversation_id,
                generation_id=generation_id if isinstance(generation_id, int) else None,
                trigger_query=(event.get("query") or "").strip(),
                suggestion_text=answer,
                from_cache=bool(event.get("from_cache")),
                sources=event.get("sources") or [],
                latency_ms=latency_ms,
            )
        )
        await session.commit()


async def finalize_conversation(conversation_id: str) -> bool:
    """
    Mark a live call as ended and ready for post-call analysis.

    Returns ``True`` only once per call (when transitioning from ``live`` to
    ``analyzing``). Returns ``False`` if the row is missing or already finalized.

    Example::

        should_run_analysis = await finalize_conversation(session_id)
        if should_run_analysis:
            asyncio.create_task(schedule_post_call_analysis(session_id))
    """
    if not database_enabled():
        return False
    async with get_db() as session:
        row = await session.get(Conversation, conversation_id)
        if row is None:
            return False
        if row.status not in ("live", "failed"):
            return False
        ended = datetime.now(UTC)
        row.ended_at = ended
        if row.started_at:
            row.duration_sec = max(0, int((ended - row.started_at).total_seconds()))
        row.status = "analyzing"
        await session.commit()
        return True


async def set_conversation_status(
    conversation_id: str, status: str, error: str | None = None
) -> None:
    """
    Update the top-level conversation status (e.g. ``ready`` or ``failed``).

    Example::

        await set_conversation_status(cid, "failed", error="No transcript segments")
    """
    if not database_enabled():
        return
    async with get_db() as session:
        row = await session.get(Conversation, conversation_id)
        if row is None:
            return
        row.status = status
        if error:
            row.extra = {**(row.extra or {}), "last_error": error}
        await session.commit()


async def load_conversation_bundle(conversation_id: str) -> dict[str, Any] | None:
    """
    Load a conversation with all transcript segments and suggestions ordered by id.

    Used by the post-call analysis job.

    Example::

        bundle = await load_conversation_bundle("abc-123")
        if bundle:
            segments = bundle["segments"]
            suggestions = bundle["suggestions"]
    """
    if not database_enabled():
        return None
    async with get_db() as session:
        row = await session.get(Conversation, conversation_id)
        if row is None:
            return None
        seg_result = await session.execute(
            select(TranscriptSegmentRow)
            .where(TranscriptSegmentRow.conversation_id == conversation_id)
            .order_by(TranscriptSegmentRow.id)
        )
        sug_result = await session.execute(
            select(SuggestionRow)
            .where(SuggestionRow.conversation_id == conversation_id)
            .order_by(SuggestionRow.id)
        )
        return {
            "conversation": row,
            "segments": seg_result.scalars().all(),
            "suggestions": sug_result.scalars().all(),
        }
