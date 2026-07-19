import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.loggin import get_logger
from app.core.security import websocket_api_key_ok
from app.api.v1.auth import websocket_jwt_ok
from app.modules.conversation_intelligence.conversation_manager import (
    conversation_manager,
)
from app.services.call_recorder import (
    RecordingQueue,
    finalize_conversation,
    start_conversation,
)
from app.services.deepgram_service import DeepgramService
from app.services.post_call_analysis import schedule_post_call_analysis
from app.services.transcript_processor import TranscriptProcessor

logger = get_logger(__name__)

router = APIRouter()

# Backpressure: drop oldest strategy would need different structure; cap prevents unbounded RAM
_AUDIO_QUEUE_MAX = 512


@router.websocket("/realtime")
async def realtime_assistant(websocket: WebSocket):
    if not websocket_jwt_ok(websocket) and not websocket_api_key_ok(websocket):
        await websocket.close(code=1008)
        return

    await websocket.accept()

    # Audio is always interleaved stereo: channel 0 = rep mic, channel 1 = tab audio.
    session_id = await conversation_manager.create_session()
    await start_conversation(session_id, audio_channels=2)
    await websocket.send_json({"type": "session_started", "session_id": session_id})
    logger.info("Realtime session started: %s", session_id)

    audio_queue: asyncio.Queue = asyncio.Queue(maxsize=_AUDIO_QUEUE_MAX)
    transcript_queue: asyncio.Queue = asyncio.Queue()
    client_queue: asyncio.Queue = asyncio.Queue()
    outbound_queue = RecordingQueue(client_queue, session_id)

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
        logger.info("Realtime session ended: %s", session_id)
