"""
Live-call query cleanup and cheap similarity for duplicate-turn detection.
No extra LLM calls — keeps latency low.
"""

from __future__ import annotations

import re
from typing import FrozenSet, Optional

from app.core.config import settings

# ASR / dictation fixes before retrieval (add more as needed).
_TYPO_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bkane\s+west\b", re.IGNORECASE), "Thane West"),
    (re.compile(r"\bfat\b", re.IGNORECASE), "flat"),
)

_VAGUE_REFERENCE = re.compile(
    r"\b(it|there|this|that|the project|the site|same place|that area)\b",
    re.IGNORECASE,
)
_LOCATION_HINT = re.compile(
    r"\b(where|located|location|address|area|near|connectivity|landmark|"
    r"kahan|कहाँ|कहां|लोकेशन|पता)\b",
    re.IGNORECASE,
)

# Strip trailing spoken noise (conservative — only at end of string).
_TRAILING_POLITENESS = re.compile(
    r"(?i)[\s,]+(thank you|thanks|sir|madam|okay|ok|then|k\.)\s*\.?\s*$"
)


def normalize_live_query(text: str) -> str:
    """Lightweight cleanup before embed / Qdrant / cache."""
    t = (text or "").strip()
    if not t:
        return t
    for pat, repl in _TYPO_REPLACEMENTS:
        t = pat.sub(repl, t)
    prev = None
    while prev != t:
        prev = t
        t = _TRAILING_POLITENESS.sub("", t).strip()
    t = re.sub(r"\s{2,}", " ", t).strip()
    return t


def build_retrieval_query(
    query: str,
    *,
    previous_query: Optional[str] = None,
) -> str:
    """Enrich vague follow-ups so embeddings match the right KB passages."""
    q = normalize_live_query(query)
    if not q:
        return q

    if _VAGUE_REFERENCE.search(q) and _LOCATION_HINT.search(q):
        cleaned = re.sub(r"^(and|also)\s+", "", q, flags=re.IGNORECASE).strip()
        cleaned = _VAGUE_REFERENCE.sub("the project", cleaned)
        return f"Where is the Raymond Realty project located {cleaned}"

    if previous_query and _VAGUE_REFERENCE.search(q):
        prev = normalize_live_query(previous_query)
        if prev and not _LOCATION_HINT.search(q):
            return f"{prev} {q}"
    return q


def dominant_language_hint(text: str) -> str:
    """
    Cheap language hint for prompts — avoids an extra LLM call.
    Returns: en | hi | mixed
    """
    if not (text or "").strip():
        return "en"
    devanagari = sum(1 for c in text if "\u0900" <= c <= "\u097f")
    n = max(len(text), 1)
    ratio = devanagari / n
    if ratio > 0.12:
        return "hi"
    if devanagari > 0:
        return "mixed"
    return "en"


def _token_jaccard(a_norm: str, b_norm: str) -> float:
    ta = set(a_norm.split())
    tb = set(b_norm.split())
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union else 0.0


def queries_are_near_duplicate(new_query: str, previous_query: Optional[str]) -> bool:
    """
    True when the new turn is essentially the same question as the last one
    (fast path: skip retrieval + LLM).
    """
    if not settings.QUERY_DEDUP_ENABLED:
        return False
    if not previous_query or not new_query:
        return False
    na = normalize_query(normalize_live_query(new_query))
    nb = normalize_query(normalize_live_query(previous_query))
    if len(na.split()) < 4 or len(nb.split()) < 4:
        return False

    sa, sb = config_slots(na), config_slots(nb)
    if sa and sb and sa != sb:
        return False

    j = _token_jaccard(na, nb)
    return j >= settings.QUERY_DEDUP_JACCARD_THRESHOLD

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

_MAX_QUERY_LEN = 4000


def normalize_query(q: str) -> str:
    """Lowercase + collapse whitespace — the canonical cache/dedup key form."""
    s = q.strip().lower()
    s = re.sub(r"\s+", " ", s)
    if len(s) > _MAX_QUERY_LEN:
        s = s[:_MAX_QUERY_LEN]
    return s
