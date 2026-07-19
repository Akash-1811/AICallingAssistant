"""
Deterministic speech metrics from saved transcript segments.

All numeric coaching stats (talk %, WPM, fillers, etc.) are computed here in code.
The LLM post-call report must use these values — it should not invent numbers.

Example::

    metrics = compute_speech_metrics(
        segments=[
            {"role": "rep", "text": "Tell me your budget?", "start_ms": 0, "end_ms": 3000, "speaker_id": 0},
            {"role": "prospect", "text": "Around two crore.", "start_ms": 3000, "end_ms": 6000, "speaker_id": 1},
        ],
        suggestions=[],
        lead_speaker_id=1,
    )
    metrics["talk_listen_ratio"]  # -> {"rep_pct": 50, "prospect_pct": 50, ...}
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

# Deliberately narrow: "yes", "okay", "sure", "right" are real answers on a
# sales call, not fillers — counting them would inflate the coaching metric.
# "matlab/मतलब" is the Hindi/Hinglish equivalent of "I mean".
# (The broader list in conversation_manager serves a different job: cleaning
# retrieval queries, where stripping "okay yes" is correct.)
FILLER_PATTERN = re.compile(
    r"\b(um|uh|hmm|you know|i mean|basically|literally|actually|honestly|matlab|मतलब)\b",
    re.IGNORECASE,
)
# English + Hindi (Devanagari and romanized) question openers — calls are
# multilingual, so question counting must be too.
QUESTION_STARTERS = frozenset(
    {
        "what", "which", "where", "when", "why", "how", "who", "whose",
        "whom", "can", "could", "would", "should", "is", "are", "was",
        "were", "do", "does", "did", "will", "have", "has",
        "kya", "kaise", "kahan", "kab", "kyun", "kyu", "kaun",
        "kitna", "kitni", "kitne",
        "क्या", "कैसे", "कहाँ", "कहां", "कब", "क्यों", "कौन",
        "कितना", "कितनी", "कितने",
    }
)


def segment_duration_ms(segment: dict[str, Any]) -> int:
    """
    Estimate how long one transcript segment lasted in milliseconds.

    Uses Deepgram timestamps when present; otherwise approximates ~400 ms per word.

    Example::

        segment_duration_ms({"start_ms": 1000, "end_ms": 4500})  # -> 3500
        segment_duration_ms({"text": "hello there", "word_count": 2})  # -> 800
    """
    start = segment.get("start_ms")
    end = segment.get("end_ms")
    if start is not None and end is not None and end > start:
        return int(end - start)
    words = max(
        1, int(segment.get("word_count") or len((segment.get("text") or "").split()))
    )
    return words * 400


def is_question_sentence(text: str) -> bool:
    """
    Heuristic: True when the utterance looks like a question.

    Example::

        is_question_sentence("What is your budget?")  # -> True
        is_question_sentence("Thanks for calling.")     # -> False
    """
    cleaned = text.strip()
    if not cleaned:
        return False
    if cleaned.endswith("?"):
        return True
    first = cleaned.split()[0].lower()
    return first in QUESTION_STARTERS


def empty_metrics(suggestion_count: int = 0, cache_hits: int = 0) -> dict[str, Any]:
    """Return a zeroed metrics dict when there is no transcript to analyze."""
    return {
        "metrics_quality": "empty",
        "talk_listen_ratio": {"rep_pct": 0, "prospect_pct": 0},
        "rep_wpm": 0,
        "rep_filler_rate_pct": 0.0,
        "rep_questions_asked": 0,
        "prospect_questions_asked": 0,
        "total_questions_asked": 0,
        "longest_rep_monologue_sec": 0,
        "turn_count": 0,
        "suggestion_count": suggestion_count,
        "suggestions_from_cache": cache_hits,
        "call_timeline": {"bucket_count": 0, "duration_ms": 0, "buckets": [], "markers": []},
    }


def format_ms_label(ms: int) -> str:
    """Format milliseconds as MM:SS for chart axis labels."""
    sec = max(0, ms // 1000)
    return f"{sec // 60:02d}:{sec % 60:02d}"


def compute_call_timeline(
    segments: Iterable[dict[str, Any]],
    *,
    lead_speaker_id: int | None = None,
    bucket_count: int = 16,
) -> dict[str, Any]:
    """
    Build per-window talk balance and activity from timestamped transcript segments.

    Stored on ``metrics["call_timeline"]`` and enriched after LLM analysis with
    sentiment, interest, and objection markers.

    Example::

        timeline = compute_call_timeline(segments, lead_speaker_id=1)
        timeline["buckets"][0]["rep_talk_pct"]  # -> 100 when only rep spoke first
    """
    segment_list = list(segments)
    if not segment_list:
        return {"bucket_count": 0, "duration_ms": 0, "buckets": [], "markers": []}

    if lead_speaker_id is not None:
        for segment in segment_list:
            segment["role"] = (
                "prospect"
                if int(segment.get("speaker_id", 0)) == lead_speaker_id
                else "rep"
            )

    duration_ms = max(
        (s.get("end_ms") or s.get("start_ms") or 0 for s in segment_list),
        default=0,
    )
    if duration_ms <= 0:
        duration_ms = sum(segment_duration_ms(s) for s in segment_list)

    bucket_ms = max(duration_ms // bucket_count, 1)
    buckets: list[dict[str, Any]] = []
    for i in range(bucket_count):
        start_ms = i * bucket_ms
        end_ms = duration_ms if i == bucket_count - 1 else (i + 1) * bucket_ms
        buckets.append(
            {
                "index": i,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "label": format_ms_label(start_ms),
                "rep_talk_pct": 0,
                "prospect_talk_pct": 0,
                "rep_words": 0,
                "prospect_words": 0,
                "rep_questions": 0,
                "prospect_questions": 0,
                "objection_score": 0,
                "events": [],
            }
        )

    for segment in segment_list:
        role = segment.get("role") or "unknown"
        text = (segment.get("text") or "").strip()
        words = len(text.split()) if text else 0
        start = segment.get("start_ms")
        end = segment.get("end_ms")
        if start is None:
            continue
        mid = int((start + (end if end is not None else start)) / 2)
        idx = min(bucket_count - 1, int(mid / max(duration_ms, 1) * bucket_count))
        bucket = buckets[idx]
        if role == "rep":
            bucket["rep_words"] += words
            bucket["rep_talk_pct"] += segment_duration_ms(segment)
            if is_question_sentence(text):
                bucket["rep_questions"] += 1
        elif role == "prospect":
            bucket["prospect_words"] += words
            bucket["prospect_talk_pct"] += segment_duration_ms(segment)
            if is_question_sentence(text):
                bucket["prospect_questions"] += 1

    for bucket in buckets:
        rep_ms = bucket.pop("rep_talk_pct", 0)
        prospect_ms = bucket.pop("prospect_talk_pct", 0)
        total = rep_ms + prospect_ms
        if total <= 0:
            bucket["rep_talk_pct"] = 0
            bucket["prospect_talk_pct"] = 0
        else:
            bucket["rep_talk_pct"] = round(100 * rep_ms / total)
            bucket["prospect_talk_pct"] = 100 - bucket["rep_talk_pct"]

    return {
        "bucket_count": bucket_count,
        "duration_ms": duration_ms,
        "buckets": buckets,
        "markers": [],
    }


def compute_speech_metrics(
    segments: Iterable[dict[str, Any]],
    suggestions: Iterable[dict[str, Any]],
    *,
    lead_speaker_id: int | None = None,
) -> dict[str, Any]:
    """
    Compute Gong / Read AI-style coaching metrics for one saved call.

    Re-derives ``rep`` vs ``prospect`` roles from ``lead_speaker_id`` when segments
    were saved before lead calibration.

    Example::

        result = compute_speech_metrics(segments, suggestions, lead_speaker_id=1)
        result["rep_wpm"]           # words per minute for the salesperson
        result["metrics_quality"]   # "full", "degraded", or "empty"
    """
    segment_list = list(segments)
    suggestion_list = list(suggestions)
    cache_hits = sum(1 for s in suggestion_list if s.get("from_cache"))

    if not segment_list:
        return empty_metrics(len(suggestion_list), cache_hits)

    if lead_speaker_id is not None:
        for segment in segment_list:
            segment["role"] = (
                "prospect"
                if int(segment.get("speaker_id", 0)) == lead_speaker_id
                else "rep"
            )

    has_timestamps = any(
        segment.get("start_ms") is not None and segment.get("end_ms") is not None
        for segment in segment_list
    )

    rep_ms = 0
    prospect_ms = 0
    rep_words = 0
    rep_fillers = 0
    rep_questions = 0
    prospect_questions = 0
    turn_count = 0
    prev_role = None
    rep_run_ms = 0
    longest_rep_monologue_ms = 0

    for segment in segment_list:
        role = segment.get("role") or "unknown"
        text = (segment.get("text") or "").strip()
        duration = segment_duration_ms(segment)
        words = len(text.split()) if text else 0

        if role == "rep":
            rep_ms += duration
            rep_words += words
            rep_fillers += len(FILLER_PATTERN.findall(text))
            if is_question_sentence(text):
                rep_questions += 1
            rep_run_ms += duration
            longest_rep_monologue_ms = max(longest_rep_monologue_ms, rep_run_ms)
        else:
            rep_run_ms = 0
            if role == "prospect":
                prospect_ms += duration
                if is_question_sentence(text):
                    prospect_questions += 1

        if role in ("rep", "prospect") and role != prev_role:
            turn_count += 1
            prev_role = role

    total_ms = rep_ms + prospect_ms
    if total_ms <= 0:
        rep_pct, prospect_pct = 50, 50
    else:
        rep_pct = round(100 * rep_ms / total_ms)
        prospect_pct = 100 - rep_pct

    rep_minutes = max(rep_ms / 60000.0, 1 / 60.0)
    rep_wpm = round(rep_words / rep_minutes)
    filler_rate = round(100.0 * rep_fillers / max(rep_words, 1), 1)

    return {
        "metrics_quality": "full" if has_timestamps else "degraded",
        "talk_listen_ratio": {
            "rep_pct": rep_pct,
            "prospect_pct": prospect_pct,
            "benchmark_note": "Benchmark: on a good discovery call the customer does ~55-60% of the talking.",
        },
        "rep_wpm": rep_wpm,
        "rep_filler_rate_pct": filler_rate,
        "rep_questions_asked": rep_questions,
        "prospect_questions_asked": prospect_questions,
        "total_questions_asked": rep_questions + prospect_questions,
        "longest_rep_monologue_sec": round(longest_rep_monologue_ms / 1000),
        "turn_count": turn_count,
        "suggestion_count": len(suggestion_list),
        "suggestions_from_cache": cache_hits,
        "segment_count": len(segment_list),
        "call_timeline": compute_call_timeline(
            segment_list, lead_speaker_id=lead_speaker_id
        ),
    }


CURVE_LABELS = ("Start", "Early", "Middle", "Late", "End")


def downsample_bucket_series(
    buckets: list[dict[str, Any]],
    value_key: str,
    *,
    labels: tuple[str, ...] = CURVE_LABELS,
) -> list[dict[str, Any]]:
    """Map timeline buckets to five chart points for dashboard engagement curves."""
    if not buckets:
        return [{"label": label, "score": 0} for label in labels]

    scores = [int(b.get(value_key) or 0) for b in buckets]
    if len(scores) <= len(labels):
        return [
            {"label": labels[i], "score": scores[min(i, len(scores) - 1)]}
            for i in range(len(labels))
        ]

    points: list[dict[str, Any]] = []
    for i, label in enumerate(labels):
        t = i / max(len(labels) - 1, 1)
        idx = min(len(scores) - 1, round(t * (len(scores) - 1)))
        points.append({"label": label, "score": scores[idx]})
    return points


def build_call_glance(metrics: dict[str, Any]) -> dict[str, Any]:
    """Compact call stats for the Client Intent dashboard."""
    timeline = metrics.get("call_timeline") or {}
    duration_ms = int(timeline.get("duration_ms") or 0)
    ratio = metrics.get("talk_listen_ratio") or {}
    rep_pct = int(ratio.get("rep_pct") or 0)
    prospect_pct = int(ratio.get("prospect_pct") or 0)
    rep_talk_ms = round(duration_ms * rep_pct / 100) if duration_ms else 0
    prospect_talk_ms = round(duration_ms * prospect_pct / 100) if duration_ms else 0
    total_questions = int(
        metrics.get("total_questions_asked")
        or (metrics.get("rep_questions_asked", 0) + metrics.get("prospect_questions_asked", 0))
    )

    return {
        "total_duration_sec": round(duration_ms / 1000),
        "total_duration_label": format_ms_label(duration_ms) if duration_ms else "00:00",
        "rep_talk_pct": rep_pct,
        "prospect_talk_pct": prospect_pct,
        "rep_talk_sec": round(rep_talk_ms / 1000),
        "prospect_talk_sec": round(prospect_talk_ms / 1000),
        "rep_talk_label": format_ms_label(rep_talk_ms),
        "prospect_talk_label": format_ms_label(prospect_talk_ms),
        "questions_asked": total_questions,
        "rep_questions": int(metrics.get("rep_questions_asked") or 0),
        "prospect_questions": int(metrics.get("prospect_questions_asked") or 0),
    }


def build_engagement_curves(timeline: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """
    Five-point MEASURED curves for the UI — every value comes from transcript
    timestamps and word counts, never from model guesses:

    - prospect_talk: how much of each window the prospect spoke (%)
    - prospect_questions: questions the prospect asked per window
    - objections: quote-anchored objection severity per window
    """
    buckets = timeline.get("buckets") or []
    return {
        "prospect_talk": downsample_bucket_series(buckets, "prospect_talk_pct"),
        "prospect_questions": downsample_bucket_series(buckets, "prospect_questions"),
        "objections": downsample_bucket_series(buckets, "objection_score"),
    }
