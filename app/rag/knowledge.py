"""Upload, parse, chunk, and index knowledge files into Qdrant."""

from __future__ import annotations

import asyncio
import csv
import hashlib
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from pypdf import PdfReader
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PointStruct,
    VectorParams,
)
from sqlalchemy import delete

from app.core.config import settings
from app.core.logging import get_logger
from app.rag.embedding_service import EmbeddingService
from app.storage.call_store import KnowledgeSource, get_db

logger = get_logger(__name__)


class KnowledgeService:
    UPLOAD_DIR = Path("data/uploads")
    CHUNK_SIZE = 700
    ALLOWED = frozenset({".txt", ".csv", ".pdf", ".json"})
    MAX_BYTES = 15 * 1024 * 1024

    def parse_json_records(self, path: Path) -> list[dict] | None:
        """Structured FAQ JSON: one Qdrant point per record with metadata.

        Returns None when the file is not a JSON array of objects with ``text``,
        so callers can fall back to plain-text chunking without dropping content.
        """
        if path.suffix.lower() != ".json":
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
        except json.JSONDecodeError:
            return None
        if not isinstance(data, list) or not data:
            return None

        records: list[dict] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if not isinstance(text, str) or not text.strip():
                continue
            records.append(item)

        # Mixed/non-FAQ JSON (e.g. nested config) — fall back to blob chunking.
        if not records:
            return None
        return records

    def read(self, path: Path) -> str:
        suffix = path.suffix.lower()
        if suffix == ".txt":
            return path.read_text(encoding="utf-8", errors="ignore")
        if suffix == ".csv":
            lines: list[str] = []
            with path.open(newline="", encoding="utf-8", errors="ignore") as handle:
                for row in csv.reader(handle):
                    cells = [cell.strip() for cell in row if cell and cell.strip()]
                    if cells:
                        lines.append(" | ".join(cells))
            return "\n".join(lines)
        if suffix == ".pdf":
            return "\n".join(
                (page.extract_text() or "")
                for page in PdfReader(str(path)).pages
            )
        if suffix == ".json":
            data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
            if isinstance(data, list):
                parts: list[str] = []
                for item in data:
                    if isinstance(item, dict) and isinstance(item.get("text"), str):
                        text = item["text"].strip()
                        if text:
                            parts.append(text)
                    elif isinstance(item, str) and item.strip():
                        parts.append(item.strip())
                    elif item is not None:
                        parts.append(json.dumps(item, ensure_ascii=False))
                return "\n".join(parts)
            if isinstance(data, dict) and isinstance(data.get("text"), str):
                return data["text"]
            return json.dumps(data, ensure_ascii=False, indent=2)
        raise ValueError(f"Unsupported file type: {suffix}")

    def chunk(self, text: str) -> list[str]:
        text = " ".join(text.split())
        if not text:
            return []
        chunks: list[str] = []
        start = 0
        while start < len(text):
            end = min(len(text), start + self.CHUNK_SIZE)
            if end < len(text):
                space = text.rfind(" ", start, end)
                if space > start + 120:
                    end = space
            piece = text[start:end].strip()
            if piece:
                chunks.append(piece)
            start = max(end, start + 1)
        return chunks

    def connect_to_qdrant(self) -> QdrantClient:
        return QdrantClient(settings.QDRANT_URL)

    def ensure_vector_collection(self, client: QdrantClient) -> None:
        name = settings.QDRANT_COLLECTION
        if name in {c.name for c in client.get_collections().collections}:
            return
        client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=384, distance=Distance.COSINE),
        )

    def remove_source_vectors(self, client: QdrantClient, source_id: str) -> None:
        client.delete(
            collection_name=settings.QDRANT_COLLECTION,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[FieldCondition(key="source_id", match=MatchValue(value=source_id))]
                )
            ),
        )

    @staticmethod
    def stable_chunk_point_id(source_id: str, index: int) -> int:
        digest = hashlib.sha256(f"{source_id}:{index}".encode()).hexdigest()
        return int(digest[:15], 16)

    async def update_source_record(self, source_id: str, **fields) -> None:
        async with get_db() as session:
            row = await session.get(KnowledgeSource, source_id)
            if row is None:
                return
            for key, value in fields.items():
                setattr(row, key, value)
            await session.commit()

    async def ingest(self, source_id: str) -> None:
        async with get_db() as session:
            row = await session.get(KnowledgeSource, source_id)
            if row is None:
                return
            path, filename = Path(row.file_path), row.filename

        await self.update_source_record(source_id, status="processing", error=None)
        try:
            if not path.is_file():
                raise FileNotFoundError("Uploaded file is missing on disk")

            client = self.connect_to_qdrant()
            self.ensure_vector_collection(client)
            self.remove_source_vectors(client, source_id)

            embedder = EmbeddingService()
            json_records = self.parse_json_records(path)
            if json_records:
                points = [
                    PointStruct(
                        id=self.stable_chunk_point_id(source_id, index),
                        vector=embedder.embed(str(item["text"]).strip()),
                        payload={
                            "text": str(item["text"]).strip(),
                            "source_id": source_id,
                            "filename": filename,
                            "record_index": index,
                            "metadata": item.get("metadata") or {},
                        },
                    )
                    for index, item in enumerate(json_records)
                ]
                chunk_count = len(points)
            else:
                chunks = self.chunk(self.read(path))
                if not chunks:
                    raise ValueError("No readable text found in file")
                points = [
                    PointStruct(
                        id=self.stable_chunk_point_id(source_id, index),
                        vector=embedder.embed(text),
                        payload={
                            "text": text,
                            "source_id": source_id,
                            "filename": filename,
                            "chunk_index": index,
                        },
                    )
                    for index, text in enumerate(chunks)
                ]
                chunk_count = len(chunks)

            for offset in range(0, len(points), 64):
                client.upsert(
                    collection_name=settings.QDRANT_COLLECTION,
                    points=points[offset : offset + 64],
                )

            await self.update_source_record(
                source_id,
                status="ready",
                chunk_count=chunk_count,
                synced_at=datetime.now(UTC),
                error=None,
            )
            logger.info("Knowledge ready id=%s chunks=%d", source_id, chunk_count)
        except Exception as exc:
            logger.exception("Knowledge ingest failed id=%s", source_id)
            await self.update_source_record(source_id, status="failed", error=str(exc)[:500])

    async def save_upload(self, filename: str, content: bytes, user_id: str) -> KnowledgeSource:
        suffix = Path(filename).suffix.lower()
        if suffix not in self.ALLOWED:
            raise ValueError("Only PDF, TXT, CSV, and JSON files are supported")

        self.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        source_id = str(uuid.uuid4())
        safe_name = Path(filename).name.replace("..", "").strip() or f"upload{suffix}"
        path = self.UPLOAD_DIR / f"{source_id}_{safe_name}"
        path.write_bytes(content)

        row = KnowledgeSource(
            id=source_id,
            user_id=user_id,
            filename=safe_name,
            file_type=suffix.lstrip("."),
            file_path=str(path),
            file_size=len(content),
            status="processing",
        )
        async with get_db() as session:
            session.add(row)
            await session.commit()
            await session.refresh(row)
        return row

    async def delete(self, source_id: str, user_id: str) -> bool:
        async with get_db() as session:
            row = await session.get(KnowledgeSource, source_id)
            if row is None or row.user_id != user_id:
                return False
            file_path = row.file_path
            await session.execute(delete(KnowledgeSource).where(KnowledgeSource.id == source_id))
            await session.commit()

        try:
            self.remove_source_vectors(self.connect_to_qdrant(), source_id)
        except Exception:
            pass
        Path(file_path).unlink(missing_ok=True)
        return True

    def queue_ingest(self, source_id: str) -> None:
        asyncio.create_task(self.ingest(source_id))


knowledge = KnowledgeService()
