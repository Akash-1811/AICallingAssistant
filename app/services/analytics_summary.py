"""Caller analytics aggregation for the dashboard summary endpoint."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

from app.call_store import Conversation, ConversationAnalysis


def range_start_time(range_key: str) -> datetime:
    now = datetime.now(timezone.utc)
    days = {"7d": 7, "30d": 30, "90d": 90}.get(range_key, 30)
    return now - timedelta(days=days)


def build_time_buckets(
    range_key: str, since: datetime
) -> list[tuple[str, datetime, datetime]]:
    now = datetime.now(timezone.utc)
    bucket_count = {"7d": 7, "30d": 6, "90d": 12}.get(range_key, 6)
    step = (now - since) / bucket_count
    buckets: list[tuple[str, datetime, datetime]] = []
    for index in range(bucket_count):
        start = since + step * index
        end = since + step * (index + 1) if index < bucket_count - 1 else now
        label = start.strftime("%a") if range_key == "7d" else f"W{index + 1}"
        buckets.append((label, start, end))
    return buckets


def is_in_time_bucket(ts: datetime | None, start: datetime, end: datetime) -> bool:
    if not ts:
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return start <= ts < end


def normalize_score_percent(value: Any) -> int | None:
    if value is None:
        return None
    try:
        score = int(float(value))
    except (TypeError, ValueError):
        return None
    if score < 0:
        return None
    if 0 < score <= 10:
        return min(100, score * 10)
    return min(100, max(0, score))


def get_client_intent(analysis: dict | None) -> dict[str, Any]:
    intent = (analysis or {}).get("client_intent") or {}
    return intent if isinstance(intent, dict) else {}


def read_interest_and_conversion(analysis: dict | None) -> tuple[int | None, int | None]:
    intent = get_client_intent(analysis)
    return (
        normalize_score_percent(intent.get("interest_score")),
        normalize_score_percent(intent.get("conversion_probability_pct")),
    )


def read_prospect_signals(analysis: dict | None) -> dict[str, int]:
    intent = get_client_intent(analysis)
    buying = intent.get("buying_signals") or []
    objections = intent.get("objections") or []
    open_questions = intent.get("open_questions_unresolved") or []
    high_objections = 0
    if isinstance(objections, list):
        high_objections = sum(
            1
            for item in objections
            if isinstance(item, dict) and item.get("severity") == "high"
        )
    return {
        "buying_signals": len(buying) if isinstance(buying, list) else 0,
        "objections": len(objections) if isinstance(objections, list) else 0,
        "open_questions": len(open_questions) if isinstance(open_questions, list) else 0,
        "high_objections": high_objections,
    }


def classify_call_outcome(
    interest: int | None,
    conversion: int | None,
    signals: dict[str, int],
) -> str:
    if (
        signals["high_objections"] > 0
        or (interest is not None and interest < 45)
        or (conversion is not None and conversion < 35)
    ):
        return "at_risk"
    if (conversion is not None and conversion >= 65) or (interest is not None and interest >= 70):
        return "qualified"
    if signals["open_questions"] > 0 or signals["objections"] > signals["buying_signals"]:
        return "follow_up"
    return "nurture"


def label_talk_balance(rep_pct: float) -> str:
    if 35 <= rep_pct <= 55:
        return "balanced"
    if rep_pct > 55:
        return "rep_heavy"
    return "prospect_heavy"


def calculate_listening_index(rep_pct: float) -> int:
    return max(0, min(100, 100 - int(abs(rep_pct - 45) * 2)))


def build_call_analytics_row(
    conv: Conversation,
    analysis_row: ConversationAnalysis | None,
) -> dict[str, Any]:
    analysis = analysis_row.analysis if analysis_row else None
    interest, conversion = read_interest_and_conversion(analysis)
    signals = read_prospect_signals(analysis)
    metrics = analysis_row.metrics if analysis_row else {}
    ratio = metrics.get("talk_listen_ratio") or {}
    rep_talk = ratio.get("rep_pct")
    rep_talk_pct = round(float(rep_talk), 1) if rep_talk is not None else None
    return {
        "id": conv.id,
        "started_at": conv.started_at.isoformat() if conv.started_at else None,
        "duration_sec": conv.duration_sec,
        "status": conv.status,
        "rep_label": conv.rep_label,
        "interest_score": interest,
        "conversion_pct": conversion,
        "buying_signals": signals["buying_signals"] if analysis_row else 0,
        "objections": signals["objections"] if analysis_row else 0,
        "outcome": classify_call_outcome(interest, conversion, signals)
        if analysis_row
        else "pending",
        "rep_talk_pct": rep_talk_pct,
        "rep_questions": int(metrics.get("rep_questions_asked") or 0),
        "rep_wpm": metrics.get("rep_wpm"),
        "listening_index": calculate_listening_index(rep_talk_pct)
        if rep_talk_pct is not None
        else None,
        "suggestion_count": int(metrics.get("suggestion_count") or 0),
        "suggestions_from_cache": int(metrics.get("suggestions_from_cache") or 0),
    }


def average(values: Sequence[float | int]) -> float:
    return sum(values) / len(values) if values else 0


def build_analytics_summary(
    range_key: str,
    conversations: Sequence[Conversation],
    latest_by_conv: dict[str, ConversationAnalysis],
) -> dict[str, Any]:
    since = range_start_time(range_key)
    buckets = build_time_buckets(range_key, since)
    total = len(conversations)
    calls = [
        build_call_analytics_row(conv, latest_by_conv.get(conv.id))
        for conv in sorted(
            [c for c in conversations if c.started_at],
            key=lambda c: c.started_at,
            reverse=True,
        )
    ]
    analyzed = [call for call in calls if call["outcome"] != "pending"]
    analyzed_count = len(analyzed)

    interest_scores = [call["interest_score"] for call in analyzed if call["interest_score"] is not None]
    conversion_scores = [
        call["conversion_pct"] for call in analyzed if call["conversion_pct"] is not None
    ]
    rep_talk_values = [call["rep_talk_pct"] for call in analyzed if call["rep_talk_pct"] is not None]
    wpm_values = [call["rep_wpm"] for call in analyzed if call["rep_wpm"]]
    question_values = [call["rep_questions"] for call in analyzed if call["rep_questions"]]
    durations = [c.duration_sec for c in conversations if c.duration_sec]

    avg_rep_talk = round(average(rep_talk_values), 1)
    suggestion_total = sum(call["suggestion_count"] for call in analyzed)
    cache_hits = sum(call["suggestions_from_cache"] for call in analyzed)

    weekly_volume = []
    for label, start, end in buckets:
        bucket_convs = [c for c in conversations if is_in_time_bucket(c.started_at, start, end)]
        weekly_volume.append(
            {"label": label, "count": len(bucket_convs), "call_ids": [c.id for c in bucket_convs]}
        )

    return {
        "range": range_key,
        "total_conversations": total,
        "analyzed_conversations": analyzed_count,
        "analysis_coverage_pct": round(100 * analyzed_count / total, 1) if total else 0,
        "avg_rep_talk_pct": avg_rep_talk,
        "avg_rep_wpm": round(average(wpm_values)) if wpm_values else 0,
        "avg_duration_sec": round(average(durations)) if durations else 0,
        "avg_interest_score": round(average(interest_scores)) if interest_scores else 0,
        "avg_conversion_pct": round(average(conversion_scores)) if conversion_scores else 0,
        "suggestion_cache_hit_pct": round(100 * cache_hits / suggestion_total, 1)
        if suggestion_total
        else 0,
        "pipeline_outlook": {
            "qualified_calls": sum(1 for call in analyzed if call["outcome"] == "qualified"),
            "follow_up_calls": sum(1 for call in analyzed if call["outcome"] == "follow_up"),
            "at_risk_calls": sum(1 for call in analyzed if call["outcome"] == "at_risk"),
        },
        "conversion_bands": {
            "likely": sum(1 for call in analyzed if (call["conversion_pct"] or 0) >= 65),
            "possible": sum(
                1 for call in analyzed if 45 <= (call["conversion_pct"] or -1) < 65
            ),
            "unlikely": sum(1 for call in analyzed if (call["conversion_pct"] or 0) < 45),
        },
        "signal_balance": {
            "buying_signals_total": sum(call["buying_signals"] for call in analyzed),
            "objections_total": sum(call["objections"] for call in analyzed),
            "avg_buying_signals_per_call": round(
                sum(call["buying_signals"] for call in analyzed) / analyzed_count, 1
            )
            if analyzed_count
            else 0,
            "avg_objections_per_call": round(
                sum(call["objections"] for call in analyzed) / analyzed_count, 1
            )
            if analyzed_count
            else 0,
            "net_signal_score": sum(call["buying_signals"] - call["objections"] for call in analyzed),
        },
        "coaching_snapshot": {
            "avg_rep_questions": round(average(question_values), 1) if question_values else 0,
            "talk_balance_label": label_talk_balance(avg_rep_talk),
            "listening_index": calculate_listening_index(avg_rep_talk),
        },
        "weekly_volume": weekly_volume,
        "calls": [
            {key: value for key, value in call.items() if key not in {"suggestion_count", "suggestions_from_cache"}}
            for call in calls
        ],
    }
