"""
REST API for saved conversations and analytics.

All routes require a valid JWT (``Authorization: Bearer``) or logged-in session.

Example::

    GET /api/v1/conversations?limit=10
    GET /api/v1/conversations/{id}/analysis
    GET /api/v1/analytics/summary?range=30d
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import desc, select

from app.analysis.analytics_summary import build_analytics_summary, range_start_time
from app.analysis.post_call_analysis import refresh_call_metrics, schedule_post_call_analysis
from app.analysis.speech_metrics import compute_speech_metrics
from app.api.v1.auth import (
    AUDIO_TOKEN_MINUTES,
    User,
    create_audio_token,
    decode_audio_token,
    decode_token,
    get_current_user,
)
from app.core.config import settings
from app.scripts.demo_analysis import build_demo_analysis
from app.scripts.demo_transcripts import build_scenarios
from app.storage.call_store import (
    Conversation,
    ConversationAnalysis,
    SuggestionRow,
    TranscriptSegmentRow,
    database_enabled,
    get_db,
)

router = APIRouter(
    prefix="/conversations",
    tags=["conversations"],
    dependencies=[Depends(get_current_user)],
)


def ensure_database_enabled() -> None:
    """
    Raise HTTP 503 when call persistence is turned off.

    Example::

        ensure_database_enabled()  # no-op when DATABASE_ENABLED=true
    """
    if not database_enabled():
        raise HTTPException(status_code=503, detail="Call persistence is not enabled")


def conversation_to_dict(row: Conversation) -> dict[str, Any]:
    """
    Serialize a conversation row for list/detail API responses.

    Example::

        conversation_to_dict(row)
        # -> {"id": "...", "status": "ready", "duration_sec": 582, ...}
    """
    return {
        "id": row.id,
        "status": row.status,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "ended_at": row.ended_at.isoformat() if row.ended_at else None,
        "duration_sec": row.duration_sec,
        "lead_speaker_id": row.lead_speaker_id,
        "audio_channels": row.audio_channels,
        "rep_label": row.rep_label,
        "caller_name": row.caller_name,
        "caller_phone": row.caller_phone,
        "caller_address": row.caller_address,
        "call_notes": row.call_notes,
    }


@router.get("")
async def list_conversations(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """Return recent conversations, newest first."""
    ensure_database_enabled()
    async with get_db() as session:
        result = await session.execute(
            select(Conversation)
            .order_by(desc(Conversation.started_at))
            .offset(offset)
            .limit(limit)
        )
        rows = result.scalars().all()
        return {
            "items": [conversation_to_dict(r) for r in rows],
            "limit": limit,
            "offset": offset,
        }


@router.get("/{conversation_id}")
async def get_conversation(conversation_id: str):
    """Return metadata for one conversation."""
    ensure_database_enabled()
    async with get_db() as session:
        row = await session.get(Conversation, conversation_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return conversation_to_dict(row)


@router.get("/{conversation_id}/transcript")
async def get_transcript(conversation_id: str):
    """Return transcript segments and AI suggestions for one conversation."""
    ensure_database_enabled()
    async with get_db() as session:
        conv = await session.get(Conversation, conversation_id)
        if conv is None:
            raise HTTPException(status_code=404, detail="Conversation not found")

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
            "conversation_id": conversation_id,
            "segments": [
                {
                    "speaker_id": s.speaker_id,
                    "role": s.role,
                    "text": s.text,
                    "start_ms": s.start_ms,
                    "end_ms": s.end_ms,
                    "word_count": s.word_count,
                }
                for s in seg_result.scalars().all()
            ],
            "suggestions": [
                {
                    "generation_id": s.generation_id,
                    "trigger_query": s.trigger_query,
                    "suggestion_text": s.suggestion_text,
                    "from_cache": s.from_cache,
                    "sources": s.sources,
                    "latency_ms": s.latency_ms,
                    "created_at": s.created_at.isoformat() if s.created_at else None,
                }
                for s in sug_result.scalars().all()
            ],
        }


@router.get("/{conversation_id}/analysis")
async def get_analysis(conversation_id: str):
    """Return the latest post-call metrics and structured analysis report."""
    ensure_database_enabled()
    async with get_db() as session:
        conv = await session.get(Conversation, conversation_id)
        if conv is None:
            raise HTTPException(status_code=404, detail="Conversation not found")

        ready_result = await session.execute(
            select(ConversationAnalysis)
            .where(
                ConversationAnalysis.conversation_id == conversation_id,
                ConversationAnalysis.status == "ready",
            )
            .order_by(desc(ConversationAnalysis.version))
            .limit(1)
        )
        analysis = ready_result.scalar_one_or_none()
        if analysis is None:
            fallback = await session.execute(
                select(ConversationAnalysis)
                .where(ConversationAnalysis.conversation_id == conversation_id)
                .order_by(desc(ConversationAnalysis.version))
                .limit(1)
            )
            analysis = fallback.scalar_one_or_none()
        if analysis is None:
            return {
                "conversation_id": conversation_id,
                "status": conv.status,
                "metrics": {},
                "analysis": {},
            }
        return {
            "conversation_id": conversation_id,
            "status": analysis.status,
            "version": analysis.version,
            "model": analysis.model,
            "metrics": analysis.metrics or {},
            "analysis": analysis.analysis or {},
            "error": analysis.error,
            "created_at": analysis.created_at.isoformat() if analysis.created_at else None,
        }


@router.get("/{conversation_id}/audio-token")
async def get_audio_token(conversation_id: str):
    """
    Mint a short-lived token scoped to this one call's recording — the media
    player uses it (via ?token=) instead of the real login token, since a
    plain <audio> element can't send an Authorization header.
    """
    ensure_database_enabled()
    async with get_db() as session:
        conv = await session.get(Conversation, conversation_id)
        if conv is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
    return {
        "token": create_audio_token(conversation_id),
        "expires_in": AUDIO_TOKEN_MINUTES * 60,
    }


# Outside `router`: a plain <audio src> can't send an Authorization header, so
# this one endpoint accepts either the normal header (existing callers) OR the
# short-lived ?token= from /audio-token above — never the blanket dependency.
audio_router = APIRouter(prefix="/conversations", tags=["conversations"])


@audio_router.get("/{conversation_id}/audio")
async def get_audio(
    conversation_id: str,
    token: str | None = Query(default=None),
    authorization: str | None = Header(default=None),
):
    """Stream the recorded call audio as a WAV file (if available)."""
    ensure_database_enabled()
    authorized = token is not None and decode_audio_token(token) == conversation_id
    if not authorized and authorization and authorization.lower().startswith("bearer "):
        authorized = decode_token(authorization[7:].strip()) is not None
    if not authorized:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Ensure the conversation exists so ids can't be probed.
    async with get_db() as session:
        conv = await session.get(Conversation, conversation_id)
        if conv is None:
            raise HTTPException(status_code=404, detail="Conversation not found")

    path = Path(settings.CALL_RECORDINGS_DIR) / f"{conversation_id}.wav"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Audio not available for this call yet")
    return FileResponse(
        str(path),
        media_type="audio/wav",
        filename=f"{conversation_id}.wav",
    )


class CallerDetailsBody(BaseModel):
    caller_name: str = Field(..., max_length=120)
    caller_phone: str | None = Field(default=None, max_length=30)
    caller_address: str | None = Field(default=None, max_length=500)
    call_notes: str | None = Field(default=None, max_length=4000)

    @field_validator("caller_name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("caller_name cannot be blank")
        return v

    @field_validator("caller_phone", "caller_address", "call_notes")
    @classmethod
    def blank_to_none(cls, v: str | None) -> str | None:
        v = (v or "").strip()
        return v or None


@router.patch("/{conversation_id}/caller")
async def update_caller_details(conversation_id: str, body: CallerDetailsBody):
    """Save the customer's name/phone/address/notes captured at the end of a call."""
    ensure_database_enabled()
    async with get_db() as session:
        conv = await session.get(Conversation, conversation_id)
        if conv is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        conv.caller_name = body.caller_name
        conv.caller_phone = body.caller_phone
        conv.caller_address = body.caller_address
        conv.call_notes = body.call_notes
        await session.commit()
        return {
            "conversation_id": conversation_id,
            "caller_name": conv.caller_name,
            "caller_phone": conv.caller_phone,
            "caller_address": conv.caller_address,
            "call_notes": conv.call_notes,
        }


class SeedDemoBody(BaseModel):
    count: int = Field(default=10, ge=1, le=25)
    reset: bool = False


@router.post("/seed-demo")
async def seed_demo_calls(body: SeedDemoBody, user: User = Depends(get_current_user)) -> dict:
    """
    Insert production-quality demo calls (long transcripts + ready analysis) for the current user.

    Calls are tagged in `Conversation.extra` so they can be reset per-user.
    """
    ensure_database_enabled()
    rep_name = (user.display_name or user.email.split("@")[0]).strip() if user.email else "Rep"
    templates = build_scenarios(rep_name)
    if not templates:
        raise HTTPException(status_code=500, detail="No demo scenarios available")

    # Build the requested number of scenarios with unique ids.
    scenarios = []
    for i in range(body.count):
        src = templates[i % len(templates)]
        scenario = {**src}
        scenario["id"] = str(uuid.uuid4())
        scenario["label"] = f"{src.get('label', 'Demo call')} #{i+1}"
        scenario["days_ago"] = int(src.get("days_ago") or 0) + (i // len(templates))
        scenarios.append(scenario)

    async with get_db() as session:
        if body.reset:
            result = await session.execute(select(Conversation).where(Conversation.workspace_id == user.id))
            for conv in result.scalars().all():
                extra = conv.extra or {}
                if extra.get("source") == "seed_demo_api":
                    await session.delete(conv)
            await session.commit()

        for scenario in scenarios:
            conversation_id = scenario["id"]
            transcript = scenario["transcript"]
            suggestions = scenario.get("suggestions") or []

            duration_sec = max(1, round((transcript[-1]["end_ms"] - transcript[0]["start_ms"]) / 1000))
            # Spread calls over time so charts look realistic.
            started = datetime.now(UTC) - timedelta(days=int(scenario.get("days_ago") or 0), minutes=duration_sec // 60)
            ended = started + timedelta(seconds=duration_sec)

            conv = Conversation(
                id=conversation_id,
                status="ready",
                lead_speaker_id=1,
                audio_channels=1,
                rep_label=rep_name,
                workspace_id=user.id,
                started_at=started,
                ended_at=ended,
                duration_sec=duration_sec,
                extra={
                    "source": "seed_demo_api",
                    "label": scenario.get("label"),
                    "seed_owner_user_id": user.id,
                },
            )
            session.add(conv)

            for line in transcript:
                session.add(
                    TranscriptSegmentRow(
                        conversation_id=conversation_id,
                        speaker_id=line["speaker_id"],
                        role=line["role"],
                        text=line["text"],
                        start_ms=line["start_ms"],
                        end_ms=line["end_ms"],
                        word_count=len(line["text"].split()),
                    )
                )
            for sug in suggestions:
                session.add(
                    SuggestionRow(
                        conversation_id=conversation_id,
                        generation_id=sug.get("generation_id"),
                        trigger_query=sug.get("trigger_query") or "",
                        suggestion_text=sug.get("suggestion_text") or "",
                        from_cache=bool(sug.get("from_cache", False)),
                        sources=[],
                        latency_ms=sug.get("latency_ms"),
                    )
                )

            # Compute metrics + attach deterministic demo analysis (fast, no external calls).
            segment_dicts = [
                {
                    "speaker_id": line["speaker_id"],
                    "role": line["role"],
                    "text": line["text"],
                    "start_ms": line["start_ms"],
                    "end_ms": line["end_ms"],
                }
                for line in transcript
            ]
            suggestion_dicts = [
                {
                    "trigger_query": item.get("trigger_query") or "",
                    "suggestion_text": item.get("suggestion_text") or "",
                    "from_cache": bool(item.get("from_cache", False)),
                    "latency_ms": item.get("latency_ms"),
                }
                for item in suggestions
            ]
            metrics = compute_speech_metrics(segment_dicts, suggestion_dicts, lead_speaker_id=1)
            analysis, metrics = build_demo_analysis(conversation_id, rep_name, metrics, segment_dicts)
            session.add(
                ConversationAnalysis(
                    conversation_id=conversation_id,
                    version=1,
                    model="seed-demo-api",
                    status="ready",
                    metrics=metrics,
                    analysis=analysis.model_dump(),
                    created_at=ended,
                )
            )

        await session.commit()

    return {"seeded": len(scenarios)}


@router.post("/{conversation_id}/reanalyze")
async def reanalyze(conversation_id: str):
    """Re-run post-call analysis and keep the previous report as history."""
    ensure_database_enabled()
    async with get_db() as session:
        conv = await session.get(Conversation, conversation_id)
        if conv is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        conv.status = "analyzing"
        await session.commit()

    asyncio.create_task(schedule_post_call_analysis(conversation_id))
    return {"conversation_id": conversation_id, "status": "analyzing"}


@router.post("/{conversation_id}/refresh-metrics")
async def refresh_metrics(conversation_id: str):
    """Recompute transcript timeline metrics without calling the LLM."""
    ensure_database_enabled()
    async with get_db() as session:
        conv = await session.get(Conversation, conversation_id)
        if conv is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
    updated = await refresh_call_metrics(conversation_id)
    if not updated:
        raise HTTPException(status_code=400, detail="No saved analysis to attach metrics to")
    return {"conversation_id": conversation_id, "status": "ready"}


analytics_router = APIRouter(
    prefix="/analytics",
    tags=["analytics"],
    dependencies=[Depends(get_current_user)],
)


@analytics_router.get("/summary")
async def analytics_summary(range: str = Query("30d")):
    """Aggregate caller analytics for saved conversations in the selected range."""
    ensure_database_enabled()
    async with get_db() as session:
        conv_result = await session.execute(
            select(Conversation).where(Conversation.started_at >= range_start_time(range))
        )
        conversations = conv_result.scalars().all()
        conv_ids = [c.id for c in conversations]

        latest_by_conv: dict[str, ConversationAnalysis] = {}
        if conv_ids:
            analysis_result = await session.execute(
                select(ConversationAnalysis).where(
                    ConversationAnalysis.conversation_id.in_(conv_ids),
                    ConversationAnalysis.status == "ready",
                )
            )
            for analysis_row in analysis_result.scalars().all():
                prev = latest_by_conv.get(analysis_row.conversation_id)
                if not prev or analysis_row.version > prev.version:
                    latest_by_conv[analysis_row.conversation_id] = analysis_row

        return build_analytics_summary(range, conversations, latest_by_conv)
