"""Structured retrieval outputs for grounding, citations, and API contracts."""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class RetrievedChunk:
    """One passage from the vector store with optional business metadata."""

    text: str
    chunk_id: Optional[str] = None
    vector_score: Optional[float] = None
    rerank_score: Optional[float] = None  # cross-encoder score when reranking runs
    metadata: Dict[str, Any] = field(default_factory=dict)

    def excerpt(self, max_len: int = 200) -> str:
        t = (self.text or "").strip().replace("\n", " ")
        if len(t) <= max_len:
            return t
        return t[: max_len - 1] + "…"
