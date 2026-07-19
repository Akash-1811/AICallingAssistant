"""
Streams stereo PCM to Deepgram and turns results into speaker-tagged segments.

The browser always sends interleaved stereo linear16 @ 16 kHz:
channel 0 = the rep's microphone, channel 1 = shared meeting-tab audio (the
customer). Deepgram transcribes each channel separately (``multichannel=true``),
so speaker identity comes from physical channels — deterministic, no voice
diarization guesswork and no manual calibration.
"""

import asyncio
from typing import Any, List

from deepgram import AsyncDeepgramClient

from app.core.config import settings
from app.core.logging import get_logger
from app.live.call_recorder import OutboundQueue
from app.live.transcript_types import TranscriptSegment

logger = get_logger(__name__)


def _message_to_dict(message: Any) -> dict:
    if isinstance(message, dict):
        return message
    if hasattr(message, "model_dump"):
        return message.model_dump()
    if hasattr(message, "dict"):
        return message.dict()
    return dict(message)


def _speaker_channel(data: dict) -> int:
    """Streaming Results carry ``channel_index: [channel, total_channels]``.
    Channel 0 = mic (rep), channel 1 = tab audio (customer)."""
    idx = data.get("channel_index")
    if isinstance(idx, list) and idx:
        idx = idx[0]
    try:
        return int(idx)
    except (TypeError, ValueError):
        return 0


def _first_alternative(data: dict) -> dict:
    ch = data.get("channel")
    if not isinstance(ch, dict):
        return {}
    alts = ch.get("alternatives") or []
    return alts[0] if alts and isinstance(alts[0], dict) else {}


def _segment_from_results(data: dict) -> TranscriptSegment | None:
    """One final Results message = one speaker segment (per-channel transcript)."""
    alt = _first_alternative(data)
    text = (alt.get("transcript") or "").strip()
    if not text:
        return None

    start_ms = end_ms = None
    words = [w for w in (alt.get("words") or []) if isinstance(w, dict)]
    if words:
        try:
            start_ms = int(float(words[0].get("start")) * 1000)
            end_ms = int(float(words[-1].get("end")) * 1000)
        except (TypeError, ValueError):
            start_ms = end_ms = None

    return TranscriptSegment(
        text=text,
        speaker=_speaker_channel(data),
        start_ms=start_ms,
        end_ms=end_ms,
    )


class DeepgramService:

    def __init__(self):
        if not settings.DEEPGRAM_API_KEY:
            raise ValueError("DEEPGRAM_API_KEY is not set")
        self.client = AsyncDeepgramClient(api_key=settings.DEEPGRAM_API_KEY)

    async def _one_connection(
        self,
        audio_queue: asyncio.Queue,
        transcript_queue: asyncio.Queue,
        outbound_queue: OutboundQueue,
        session_id: str,
    ) -> None:
        """
        One Deepgram WebSocket lifecycle. If the remote closes or an error occurs,
        this returns or raises so the outer loop can reconnect — without killing
        the browser's audio receive task.
        """
        results_seen = 0
        finals_seen = 0

        async with self.client.listen.v1.connect(
            model=settings.DEEPGRAM_MODEL,
            language=settings.DEEPGRAM_LANGUAGE,
            smart_format="true",
            interim_results="true",
            endpointing=str(settings.REALTIME_DEEPGRAM_ENDPOINTING_MS),
            encoding="linear16",
            sample_rate="16000",
            channels="2",
            multichannel="true",
        ) as connection:
            logger.info(
                "Deepgram connected session=%s (model=%s, stereo 2ch)",
                session_id,
                settings.DEEPGRAM_MODEL,
            )

            async def sender() -> None:
                while True:
                    chunk = await audio_queue.get()
                    await connection.send_media(chunk)

            async def receiver() -> None:
                nonlocal results_seen, finals_seen
                async for message in connection:
                    if isinstance(message, (bytes, bytearray)):
                        continue
                    data = _message_to_dict(message)
                    if data.get("type") != "Results":
                        continue
                    results_seen += 1

                    if not data.get("is_final"):
                        text = (_first_alternative(data).get("transcript") or "").strip()
                        if text:
                            await outbound_queue.put(
                                {
                                    "type": "transcript_partial",
                                    "text": text,
                                    "session_id": session_id,
                                    "speaker": _speaker_channel(data),
                                }
                            )
                        continue

                    segment = _segment_from_results(data)
                    if segment is None:
                        continue
                    finals_seen += 1
                    await outbound_queue.put(
                        {
                            "type": "transcript_final",
                            "text": segment.text,
                            "speaker": int(segment.speaker),
                            "session_id": session_id,
                            "start_ms": segment.start_ms,
                            "end_ms": segment.end_ms,
                        }
                    )
                    await transcript_queue.put([segment])

            send_task = asyncio.create_task(sender())
            recv_task = asyncio.create_task(receiver())
            try:
                done, pending = await asyncio.wait(
                    {send_task, recv_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )
            except asyncio.CancelledError:
                # If the session task is cancelled while in wait(), child tasks are
                # not cancelled automatically — cancel explicitly to avoid
                # "Task was destroyed but it is pending" on interpreter teardown.
                for t in (send_task, recv_task):
                    if not t.done():
                        t.cancel()
                await asyncio.gather(send_task, recv_task, return_exceptions=True)
                raise
            for t in pending:
                t.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            for t in done:
                exc = t.exception()
                if exc is not None and not isinstance(exc, asyncio.CancelledError):
                    raise exc

            try:
                await connection.send_close_stream()
            except Exception as e:
                logger.debug("Deepgram send_close_stream: %s", e)

        # A connection that lived without ever producing results means Deepgram
        # heard unusable audio (silent mic, stale client sending mono) — surface it.
        log = logger.warning if results_seen == 0 else logger.info
        log(
            "Deepgram connection ended session=%s results=%d final_segments=%d",
            session_id,
            results_seen,
            finals_seen,
        )

    async def stream_transcription(
        self,
        audio_queue: asyncio.Queue,
        transcript_queue: asyncio.Queue,
        outbound_queue: OutboundQueue,
        session_id: str,
    ) -> None:
        """
        Runs until cancelled. Reconnects on transient Deepgram failures so the
        client WebSocket can keep sending PCM without the whole session dying.
        """
        backoff = 0.5
        max_backoff = 8.0
        while True:
            try:
                await self._one_connection(
                    audio_queue,
                    transcript_queue,
                    outbound_queue,
                    session_id,
                )
                logger.debug("Deepgram connection cycle ended; reconnecting")
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(
                    "Deepgram connection lost (%s); reconnecting in %.1fs",
                    e,
                    backoff,
                )
                try:
                    await asyncio.sleep(backoff)
                except asyncio.CancelledError:
                    raise
                backoff = min(backoff * 1.5, max_backoff)
                continue
            backoff = 0.5
