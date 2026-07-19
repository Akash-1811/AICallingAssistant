"""
Structured signals from a natural-language retrieval query.

Used to prevent answer-cache semantic collisions (e.g. 2BHK vs 3BHK follow-ups
that embed similarly but must not share cached answers).
"""

from __future__ import annotations

import re
from typing import FrozenSet, Optional

# Normalized "flat type" mentions (spoken + written variants).
_BHK_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\b1\s*bhk\b", "1bhk"),
    (r"\bone\s+bhk\b", "1bhk"),
    (r"\b2\s*bhk\b", "2bhk"),
    (r"\btwo\s+bhk\b", "2bhk"),
    (r"\b3\s*bhk\b", "3bhk"),
    (r"\bthree\s+bhk\b", "3bhk"),
    (r"\b4\s*bhk\b", "4bhk"),
    (r"\bfour\s+bhk\b", "4bhk"),
)


def config_slots(text: str) -> FrozenSet[str]:
    """Extract BHK configuration mentions from arbitrary query text."""
    s = text.strip().lower()
    s = re.sub(r"\s+", " ", s)
    if not s:
        return frozenset()
    found: set[str] = set()
    for pattern, tag in _BHK_PATTERNS:
        if re.search(pattern, s, re.IGNORECASE):
            found.add(tag)
    return frozenset(found)


def semantic_cache_compatible(new_norm: str, cached_norm: Optional[str]) -> bool:
    """
    Whether a semantic cache entry keyed by `cached_norm` may serve `new_norm`.

    If both queries mention specific BHK types, the sets must match exactly.
    If only one side mentions BHK, we allow match (generic ↔ specific paraphrase).

    Payloads without `query_norm` (legacy) only participate in semantic hits when the
    new query has no BHK slots—otherwise we miss and avoid 2BHK/3BHK cache bleed.
    """
    a = config_slots(new_norm)
    if not cached_norm:
        return len(a) == 0
    b = config_slots(cached_norm)
    if not a and not b:
        return True
    if not a or not b:
        return True
    return a == b
