"""
Ingest `app/data/raymond_realty.json` into Qdrant (collection from settings).

Local (Qdrant on localhost:6333):
  python -m app.scripts.ingest_data

Docker (Qdrant in compose):
  docker compose --profile ingest run --rm ingest
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from app.core.config import settings
from app.services.embedding_service import EmbeddingService

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_DEFAULT_FILE = "raymond_realty.json"
_QDRANT_READY_RETRIES = 15
_QDRANT_READY_DELAY_SEC = 1.0


def _wait_for_qdrant(client: QdrantClient) -> None:
    """Qdrant HTTP may not accept connections the instant the container is 'healthy'."""
    last: Exception | None = None
    for attempt in range(_QDRANT_READY_RETRIES):
        try:
            client.get_collections()
            return
        except Exception as e:
            last = e
            time.sleep(_QDRANT_READY_DELAY_SEC)
    raise ConnectionError(
        f"Could not reach Qdrant at {settings.QDRANT_URL!r} after "
        f"{_QDRANT_READY_RETRIES} attempts: {last}"
    ) from last


def _recreate_collection(client: QdrantClient) -> None:
    name = settings.QDRANT_COLLECTION
    cfg = VectorParams(size=384, distance=Distance.COSINE)
    try:
        existing = client.get_collections().collections
        if any(c.name == name for c in existing):
            client.delete_collection(collection_name=name)
    except Exception:
        pass
    client.create_collection(collection_name=name, vectors_config=cfg)


def ingest(data_filename: str = _DEFAULT_FILE) -> None:
    data_path = _DATA_DIR / data_filename
    if not data_path.is_file():
        raise FileNotFoundError(
            f"Data file not found: {data_path}. "
            f"Place your JSON export under app/data/."
        )

    with open(data_path, encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list) or not data:
        raise ValueError("Expected a non-empty JSON array of records.")

    # ASCII-only output: Windows consoles default to cp1252 and crash on unicode arrows.
    print(
        f"Ingesting {len(data)} points -> "
        f"Qdrant {settings.QDRANT_URL} / collection `{settings.QDRANT_COLLECTION}`"
    )

    # Connect to Qdrant before loading the embedding model (fail fast, correct URL).
    client = QdrantClient(settings.QDRANT_URL)
    _wait_for_qdrant(client)
    _recreate_collection(client)

    embedder = EmbeddingService()

    points: list[PointStruct] = []
    for item in data:
        if "text" not in item or "id" not in item:
            raise ValueError(f"Each item needs 'id' and 'text', got keys: {item.keys()}")
        vector = embedder.embed(item["text"])
        points.append(
            PointStruct(
                id=item["id"],
                vector=vector,
                payload={
                    "text": item["text"],
                    "id": item["id"],
                    "metadata": item.get("metadata") or {},
                },
            )
        )

    batch = 64
    for i in range(0, len(points), batch):
        chunk = points[i : i + batch]
        client.upsert(collection_name=settings.QDRANT_COLLECTION, points=chunk)

    print(
        f"Ingested {len(points)} vectors into `{settings.QDRANT_COLLECTION}` successfully."
    )


def main() -> None:
    filename = sys.argv[1] if len(sys.argv) > 1 else _DEFAULT_FILE
    ingest(filename)


if __name__ == "__main__":
    main()
