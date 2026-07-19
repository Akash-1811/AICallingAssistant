"""Structured retrieval outputs for grounding, citations, and API contracts."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RetrievedChunk:
    """One passage from the vector store with optional business metadata."""

    text: str
    chunk_id: str | None = None
    vector_score: float | None = None
    rerank_score: float | None = None  # cross-encoder score when reranking runs
    metadata: dict[str, Any] = field(default_factory=dict)

    def excerpt(self, max_len: int = 200) -> str:
        t = (self.text or "").strip().replace("\n", " ")
        if len(t) <= max_len:
            return t
        return t[: max_len - 1] + "…"
