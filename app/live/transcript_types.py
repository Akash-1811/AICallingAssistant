"""
Shared shape of one transcribed speech span (text + speaker channel + timing).
Used by every stage from Deepgram parsing to the database.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class TranscriptSegment:
    """One contiguous span of speech from a single speaker channel."""

    text: str
    speaker: int
    start_ms: int | None = None
    end_ms: int | None = None
