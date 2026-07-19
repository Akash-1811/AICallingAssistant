"""
WebSocket entry point for a live call: authenticates via the first message,
then runs four concurrent tasks per session — receive audio, transcribe
(Deepgram), turn transcripts into suggestions, and send events back.
"""
import asyncio
import json
from collections import defaultdict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.analysis.post_call_analysis import schedule_post_call_analysis
from app.api.v1.auth import decode_token
from app.core.config import settings
from app.core.logging import get_logger
from app.live.call_recorder import (
    RecordingQueue,
    finalize_conversation,
    start_conversation,
)
from app.live.conversation_manager import conversation_manager
from app.live.deepgram_service import DeepgramService
from app.live.transcript_processor import TranscriptProcessor

logger = get_logger(__name__)

router = APIRouter()

# Backpressure: drop oldest strategy would need different structure; cap prevents unbounded RAM
_AUDIO_QUEUE_MAX = 512
_POLICY_VIOLATION = 1008

# Live session count per owner (user id or "api-key") — caps runaway tabs.
_active_sessions: dict[str, int] = defaultdict(int)


async def _authenticate(websocket: WebSocket) -> str | None:
    """
    Return the session owner (a user id, or "api-key") or None to refuse.

    Auth arrives in the FIRST WebSocket message — {"type": "auth", "token": …}
    or {"type": "auth", "api_key": …} — never in the URL, so credentials never
    reach access logs. Non-browser clients may instead send the X-API-Key header.
    """
    internal_key = settings.INTERNAL_API_KEY
    if internal_key and websocket.headers.get("x-api-key") == internal_key:
        return "api-key"
    try:
        raw = await asyncio.wait_for(
            websocket.receive_text(), timeout=settings.WS_AUTH_TIMEOUT_SECONDS
        )
        body = json.loads(raw)
    except (TimeoutError, KeyError, json.JSONDecodeError, WebSocketDisconnect):
        return None
    if body.get("type") != "auth":
        return None
    user_id = decode_token(body.get("token") or "")
    if user_id:
        return user_id
    if internal_key and body.get("api_key") == internal_key:
        return "api-key"
    return None


@router.websocket("/realtime")
async def realtime_assistant(websocket: WebSocket):
    await websocket.accept()

    owner = await _authenticate(websocket)
    if owner is None:
        await websocket.close(code=_POLICY_VIOLATION)
        return

    try:
        deepgram = DeepgramService()
    except ValueError as e:
        logger.error("Deepgram not configured: %s", e)
        await websocket.send_json(
            {
                "type": "error",
                "message": "Server misconfiguration: speech service unavailable.",
            }
        )
        await websocket.close(code=1011)
        return

    if _active_sessions[owner] >= settings.MAX_CONCURRENT_SESSIONS_PER_USER:
        logger.warning("Session cap reached for owner=%s", owner)
        await websocket.send_json(
            {"type": "error", "message": "Too many live sessions — close another tab first."}
        )
        await websocket.close(code=_POLICY_VIOLATION)
        return
    _active_sessions[owner] += 1

    # Audio is always interleaved stereo: channel 0 = rep mic, channel 1 = tab audio.
    session_id = await conversation_manager.create_session()
    await start_conversation(session_id, audio_channels=2)
    await websocket.send_json({"type": "session_started", "session_id": session_id})
    logger.info("Realtime session started: %s", session_id)

    audio_queue: asyncio.Queue = asyncio.Queue(maxsize=_AUDIO_QUEUE_MAX)
    transcript_queue: asyncio.Queue = asyncio.Queue()
    client_queue: asyncio.Queue = asyncio.Queue()
    outbound_queue = RecordingQueue(client_queue, session_id)

    processor = TranscriptProcessor()

    async def receive_audio():
        """Binary frames: interleaved stereo PCM chunks. Text frames are ignored."""
        try:
            while True:
                message = await websocket.receive()
                if message.get("type") == "websocket.disconnect":
                    break
                data = message.get("bytes")
                if data is None:
                    continue
                try:
                    audio_queue.put_nowait(data)
                except asyncio.QueueFull:
                    logger.warning(
                        "Audio queue full (session=%s), dropping chunk",
                        session_id,
                    )
        except WebSocketDisconnect:
            logger.info("WebSocket disconnected (receive): session=%s", session_id)
        except Exception as e:
            logger.exception("receive_audio error session=%s: %s", session_id, e)

    async def send_events():
        try:
            while True:
                item = await client_queue.get()
                await websocket.send_json(item)
        except WebSocketDisconnect:
            logger.info("WebSocket disconnected (send): session=%s", session_id)
        except Exception as e:
            logger.exception("send_events error session=%s: %s", session_id, e)

    t_deepgram = asyncio.create_task(
        deepgram.stream_transcription(
            audio_queue,
            transcript_queue,
            outbound_queue,
            session_id,
        ),
        name=f"deepgram-{session_id}",
    )
    t_proc = asyncio.create_task(
        processor.process_stream(session_id, transcript_queue, outbound_queue),
        name=f"processor-{session_id}",
    )
    t_send = asyncio.create_task(send_events(), name=f"send-{session_id}")
    t_recv = asyncio.create_task(receive_audio(), name=f"recv-{session_id}")

    # Drive session lifetime from the browser WebSocket receive loop only.
    # If Deepgram or the processor errors, those tasks reconnect or block — they must
    # NOT cancel receive_audio, or the client keeps sending PCM that nothing reads.
    tasks = [t_deepgram, t_proc, t_send, t_recv]
    try:
        await t_recv
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.exception("receive_audio failed session=%s: %s", session_id, e)
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        # Persist any events still queued before analysis reads the conversation.
        await outbound_queue.flush_and_close()
        should_analyze = await finalize_conversation(session_id)
        if should_analyze:
            asyncio.create_task(schedule_post_call_analysis(session_id))
        _active_sessions[owner] -= 1
        if _active_sessions[owner] <= 0:
            del _active_sessions[owner]
        logger.info("Realtime session ended: %s", session_id)
