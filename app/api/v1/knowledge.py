"""Upload and manage knowledge-base documents."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.api.v1.auth import User, get_current_user
from app.storage.call_store import KnowledgeSource, get_db
from app.rag.knowledge import knowledge

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    file_type: str
    file_size: int
    status: str
    chunk_count: int
    error: str | None
    created_at: datetime | None
    synced_at: datetime | None


async def require_owned_source(session, source_id: str, user_id: str) -> KnowledgeSource:
    row = await session.get(KnowledgeSource, source_id)
    if row is None or row.user_id != user_id:
        raise HTTPException(status_code=404, detail="Source not found")
    return row


@router.get("/sources")
async def list_sources(user: User = Depends(get_current_user)) -> dict:
    async with get_db() as session:
        rows = (
            await session.execute(
                select(KnowledgeSource)
                .where(KnowledgeSource.user_id == user.id)
                .order_by(KnowledgeSource.created_at.desc())
            )
        ).scalars().all()
    items = [SourceOut.model_validate(row) for row in rows]
    return {"items": items, "total_bytes": sum(item.file_size for item in items)}


@router.post("/upload", response_model=SourceOut)
async def upload_source(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
) -> SourceOut:
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(content) > knowledge.MAX_BYTES:
        raise HTTPException(status_code=400, detail="File too large (max 15 MB)")

    try:
        row = await knowledge.save_upload(file.filename or "upload.txt", content, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    knowledge.queue_ingest(row.id)
    return SourceOut.model_validate(row)


@router.post("/sources/{source_id}/sync", response_model=SourceOut)
async def sync_source(source_id: str, user: User = Depends(get_current_user)) -> SourceOut:
    async with get_db() as session:
        row = await require_owned_source(session, source_id, user.id)
        if row.status != "processing":
            row.status, row.error = "processing", None
            await session.commit()
            await session.refresh(row)

    knowledge.queue_ingest(source_id)
    return SourceOut.model_validate(row)


@router.post("/sync-all")
async def sync_all(user: User = Depends(get_current_user)) -> dict:
    async with get_db() as session:
        rows = (
            await session.execute(
                select(KnowledgeSource).where(
                    KnowledgeSource.user_id == user.id,
                    KnowledgeSource.status.in_(["ready", "failed"]),
                )
            )
        ).scalars().all()
        ids = [row.id for row in rows]
        for row in rows:
            row.status, row.error = "processing", None
        await session.commit()

    for source_id in ids:
        knowledge.queue_ingest(source_id)
    return {"queued": len(ids)}


@router.delete("/sources/{source_id}")
async def delete_source(source_id: str, user: User = Depends(get_current_user)) -> dict:
    if not await knowledge.delete(source_id, user.id):
        raise HTTPException(status_code=404, detail="Source not found")
    return {"deleted": source_id}
