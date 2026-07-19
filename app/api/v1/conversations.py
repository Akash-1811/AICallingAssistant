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
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import desc, select

from app.analysis.analytics_summary import build_analytics_summary, range_start_time
from app.analysis.post_call_analysis import refresh_call_metrics, schedule_post_call_analysis
from app.api.v1.auth import get_current_user
from app.core.config import settings
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


@router.get("/{conversation_id}/audio")
async def get_audio(conversation_id: str):
    """Download the recorded call audio as a WAV file (if available)."""
    ensure_database_enabled()
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
