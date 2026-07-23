"""
Per-call memory. Stores what has been said so far (Redis or in-memory), decides
which audio channel is the customer, and turns the customer's latest words into
a clean question for retrieval. Flow position: after speech-to-text, before RAG.
"""
import json
import re
import uuid
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.live.transcript_types import TranscriptSegment

logger = get_logger(__name__)

try:
    import redis.asyncio as aioredis
except ImportError:
    aioredis = None

# Words that indicate a question is being asked (heuristic for query extraction)
_QUESTION_WORDS = frozenset(
    {
        "what", "which", "where", "when", "why", "how", "who", "whose",
        "whom", "can", "could", "would", "should", "is", "are", "was",
        "were", "do", "does", "did", "will", "have", "has",
    }
)

# Filler words that add noise to a retrieval query without changing semantics
_FILLER_RE = re.compile(
    r"\b(um|uh|hmm|like|you know|so|right|okay|ok|yeah|yep|yes|no|sure|"
    r"actually|basically|literally|honestly|i mean|well)\b",
    re.IGNORECASE,
)

# Short follow-ups that need prior turn context (same topic, new configuration).
_FOLLOW_UP_PREFIXES = (
    "and ",
    "also ",
    "what about ",
    "how about ",
    "same for ",
    "and for ",
)

_VAGUE_REFERENCE = re.compile(
    r"\b(it|there|this|that|the project|the site|same place|that area)\b",
    re.IGNORECASE,
)


def _count_words(text: str) -> int:
    return len(text.split())


def _strip_fillers(text: str) -> str:
    """Remove spoken filler words that pollute an embedding query."""
    cleaned = _FILLER_RE.sub(" ", text)
    return re.sub(r"\s{2,}", " ", cleaned).strip()


def _is_question_sentence(sentence: str) -> bool:
    """Heuristic: sentence ends in '?' or starts with a question word."""
    s = sentence.strip()
    if s.endswith("?"):
        return True
    first = s.split()[0].lower() if s else ""
    return first in _QUESTION_WORDS


def _needs_prior_context(text: str) -> bool:
    """Pronoun-style follow-ups like 'where is it located' need the prior turn."""
    t = _strip_fillers(text)
    if not t:
        return False
    low = t.lower()
    if any(low.startswith(p) for p in _FOLLOW_UP_PREFIXES):
        return True
    return bool(_VAGUE_REFERENCE.search(t))


def _looks_like_short_follow_up(text: str) -> bool:
    """
    Spoken continuations like 'and 3BHK' or 'what about three BHK' — too short to
    retrieve alone; merge with earlier lead turns.
    """
    t = _strip_fillers(text)
    if not t:
        return False
    low = t.lower()
    if any(low.startswith(p) for p in _FOLLOW_UP_PREFIXES):
        return True
    if len(t.split()) <= 6 and re.search(
        r"\b([1234]|one|two|three|four)\s*bhk\b", low, re.IGNORECASE
    ):
        return True
    return False


def _extract_best_query(turns: list[str]) -> str:
    """
    Given the most recent N transcript turns, produce the sharpest
    retrieval query possible:

    1. If the last turn is a question (ends with '?' or starts with a
       question word) and has ≥ 4 words, use it alone — the model needs
       to answer *this* specific question.
    2. Otherwise build a joined context from the last 2 turns (question
       context + previous utterance), capped to avoid noise.
    3. If the last turn is a short follow-up ('and 3BHK'), merge last 3
       lead turns so retrieval + cache see both configurations.
    4. Strip filler words before returning.
    """
    if not turns:
        return ""

    latest = turns[-1].strip()
    latest_clean = _strip_fillers(latest)

    if _count_words(latest_clean) >= 4 and _is_question_sentence(latest_clean):
        if len(turns) >= 2 and _needs_prior_context(latest_clean):
            combined = f"{turns[-2].strip()} {latest_clean}".strip()
            return _strip_fillers(combined)
        return latest_clean

    # Fall back: join prior turns so follow-ups like 'and 3BHK' keep full context.
    if len(turns) >= 2:
        if len(turns) >= 3 and _looks_like_short_follow_up(latest_clean):
            combined = " ".join(
                x.strip() for x in (turns[-3], turns[-2], turns[-1]) if x.strip()
            )
        else:
            combined = f"{turns[-2].strip()} {latest}".strip()
        return _strip_fillers(combined)

    return latest_clean


def _session_key(session_id: str) -> str:
    return f"aicall:session:{session_id}"


def _normalize_history_item(item: Any) -> dict[str, Any]:
    if isinstance(item, str):
        return {"text": item, "speaker": 0}
    if isinstance(item, dict) and "text" in item:
        sp = item.get("speaker", 0)
        try:
            sp = int(sp)
        except (TypeError, ValueError):
            sp = 0
        return {"text": str(item["text"]), "speaker": sp}
    return {"text": "", "speaker": 0}


def _migrate_session_state(state: dict[str, Any]) -> dict[str, Any]:
    raw_hist = state.get("history") or []
    state["history"] = [_normalize_history_item(x) for x in raw_hist]
    if "last_query" not in state:
        state["last_query"] = None
    if "call_language" not in state:
        state["call_language"] = "multi"
    return state


def _speakers_in_history(history: list[dict[str, Any]]) -> list[int]:
    seen = {int(h["speaker"]) for h in history if h.get("text")}
    return sorted(seen)


def _lead_turn_strings(
    history: list[dict[str, Any]], lead_id: int | None
) -> list[str]:
    if lead_id is None:
        return []
    return [
        str(h["text"]).strip()
        for h in history
        if int(h["speaker"]) == lead_id and str(h.get("text", "")).strip()
    ]


def _lead_speaker_id(speakers_seen: list[int]) -> int | None:
    """
    Speaker ids are physical audio channels: 0 = the rep's mic, 1 = the shared
    meeting-tab audio (the customer). Once the tab has spoken, channel 1 is the
    lead. Mic-only sessions (demos, phone on speaker) have a single channel —
    treat it as the lead so the assistant still responds.
    """
    if 1 in speakers_seen:
        return 1
    if len(speakers_seen) == 1:
        return speakers_seen[0]
    return None


class ConversationManager:

    def __init__(self):
        self._memory: dict[str, dict[str, Any]] = {}
        self._redis: Any | None = None
        self._redis_failed = False

    async def _get_redis(self):
        if not settings.REDIS_URL or aioredis is None:
            return None
        if self._redis_failed:
            return None
        if self._redis is None:
            try:
                self._redis = aioredis.from_url(
                    settings.REDIS_URL,
                    encoding="utf-8",
                    decode_responses=True,
                )
                await self._redis.ping()
                logger.info("Redis session backend connected")
            except Exception as e:
                logger.warning(
                    "Redis unavailable (%s); using in-memory sessions", e
                )
                self._redis_failed = True
                self._redis = None
                return None
        return self._redis

    async def create_session(self, call_language: str = "multi") -> str:
        session_id = str(uuid.uuid4())
        r = await self._get_redis()
        empty = {
            "history": [],
            "last_query": None,
            "last_suggestion": None,
            "call_language": call_language,
        }
        if r:
            await r.setex(
                _session_key(session_id),
                settings.SESSION_TTL_SECONDS,
                json.dumps(empty),
            )
        else:
            self._memory[session_id] = dict(empty)
        return session_id

    async def _load(self, session_id: str) -> dict[str, Any]:
        empty = {"history": [], "last_query": None, "last_suggestion": None}
        r = await self._get_redis()
        if r:
            raw = await r.get(_session_key(session_id))
            return _migrate_session_state(json.loads(raw) if raw else empty)
        return _migrate_session_state(self._memory.get(session_id, empty))

    async def _save(self, session_id: str, state: dict[str, Any]) -> None:
        r = await self._get_redis()
        if r:
            await r.setex(
                _session_key(session_id),
                settings.SESSION_TTL_SECONDS,
                json.dumps(state),
            )
        else:
            self._memory[session_id] = state

    async def add_transcript(self, session_id: str, text: str) -> None:
        state = await self._load(session_id)
        history: list[dict[str, Any]] = state.setdefault("history", [])
        history.append({"text": text, "speaker": 0})
        if len(history) > settings.MAX_HISTORY_PER_SESSION:
            state["history"] = history[-settings.MAX_HISTORY_PER_SESSION :]
        await self._save(session_id, state)

    async def get_context(self, session_id: str, window: int = 5) -> str:
        state = await self._load(session_id)
        history: list[dict[str, Any]] = state.get("history", [])
        texts = [str(h.get("text", "")) for h in history[-window:]]
        return " ".join(texts)

    async def record_turn(
        self, session_id: str, segments: list[TranscriptSegment]
    ) -> tuple[str, str, list[int], int | None]:
        """
        Append channel-tagged segments, return:
        (raw_lead_context, focused_query, speakers_seen, lead_speaker_id).

        focused_query uses only the lead's (customer's) turns.
        """
        state = await self._load(session_id)
        history: list[dict[str, Any]] = state.setdefault("history", [])
        for seg in segments:
            history.append({"text": seg.text, "speaker": int(seg.speaker)})

        if len(history) > settings.MAX_HISTORY_PER_SESSION:
            state["history"] = history[-settings.MAX_HISTORY_PER_SESSION :]
            history = state["history"]

        speakers_seen = _speakers_in_history(history)
        lead = _lead_speaker_id(speakers_seen)

        window = settings.CONTEXT_QUERY_WINDOW
        lead_turns = _lead_turn_strings(history, lead)
        recent_lead = lead_turns[-window:] if lead_turns else []
        focused_query = _extract_best_query(recent_lead) if lead is not None else ""
        raw_context = " ".join(recent_lead)

        await self._save(session_id, state)
        return raw_context, focused_query, speakers_seen, lead

    async def set_last_suggestion(self, session_id: str, text: str) -> None:
        state = await self._load(session_id)
        state["last_suggestion"] = text
        await self._save(session_id, state)

    async def get_rag_context(self, session_id: str) -> dict[str, Any]:
        """Prior turn + recent lead speech for session-aware prompts."""
        state = await self._load(session_id)
        history: list[dict[str, Any]] = state.get("history") or []
        lead = _lead_speaker_id(_speakers_in_history(history))
        lead_turns = _lead_turn_strings(history, lead)
        recent = " ".join(lead_turns[-2:]) if lead_turns else ""
        return {
            "last_query": state.get("last_query"),
            "last_suggestion": state.get("last_suggestion"),
            "recent_lead_snippet": recent[:2000],
            "call_language": state.get("call_language", "multi"),
        }

    async def set_last_turn(self, session_id: str, query: str, suggestion: str) -> None:
        state = await self._load(session_id)
        state["last_query"] = query
        state["last_suggestion"] = suggestion
        await self._save(session_id, state)

    async def close(self) -> None:
        if self._redis is None:
            return
        try:
            close_fn = getattr(self._redis, "aclose", None)
            if close_fn is not None:
                await close_fn()
            else:
                maybe = self._redis.close()
                if hasattr(maybe, "__await__"):
                    await maybe
        except Exception as e:
            logger.warning("Error closing Redis: %s", e)
        finally:
            self._redis = None


conversation_manager = ConversationManager()
