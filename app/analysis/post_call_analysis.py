"""
Post-call LLM analysis: client intent and rep communication coaching.

Runs automatically when a live call ends. Flow:

1. Load saved transcript + suggestions from the database.
2. Compute deterministic metrics (``speech_metrics``).
3. Ask Gemini or OpenAI for structured JSON.
4. Overwrite numeric fields with computed metrics so the report stays honest.

Example::

    await run_post_call_analysis("f47ac10b-58cc-4372-a567-0e02b2c3d479")
    # Conversation status becomes "ready"; report is in conversation_analyses.
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import UTC, datetime
from typing import Any

from google.genai import types as genai_types
from openai import OpenAI
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import desc, select

from app.analysis.speech_metrics import (
    build_call_glance,
    build_engagement_curves,
    compute_speech_metrics,
)
from app.core.config import settings
from app.core.logging import get_logger
from app.live.call_recorder import load_conversation_bundle, set_conversation_status
from app.rag.gemini_service import get_gemini_client
from app.storage.call_store import (
    Conversation,
    ConversationAnalysis,
    database_enabled,
    get_db,
    next_analysis_version,
)

logger = get_logger(__name__)


def _percent_to_fraction(v: Any) -> Any:
    """LLMs sometimes return percent-style numbers (85) for 0–1 fields; rescale
    instead of failing the whole analysis over a formatting slip."""
    if isinstance(v, (int, float)) and 1 < v <= 100:
        return v / 100
    return v


class BuyingSignal(BaseModel):
    signal: str
    evidence_quote: str
    confidence: float = Field(ge=0, le=1)

    @field_validator("confidence", mode="before")
    @classmethod
    def _scale_confidence(cls, v: Any) -> Any:
        return _percent_to_fraction(v)


class ObjectionItem(BaseModel):
    objection: str
    evidence_quote: str
    severity: str = "medium"


class CoachingTip(BaseModel):
    area: str
    recommendation: str
    example_moment_ms: int | None = None


class TalkListenRatio(BaseModel):
    rep_pct: int
    prospect_pct: int
    benchmark_note: str = ""


class ClientIntentBlock(BaseModel):
    primary_intent: str
    summary: str
    interest_score: int = Field(default=50, ge=0, le=100)
    engagement_level: str = Field(default="medium")
    conversion_likelihood: str = Field(default="medium")
    conversion_probability_pct: int = Field(default=50, ge=0, le=100)
    conversion_rationale: str = ""
    buying_signals: list[BuyingSignal] = Field(default_factory=list)
    objections: list[ObjectionItem] = Field(default_factory=list)
    open_questions_unresolved: list[str] = Field(default_factory=list)


class RepCommunicationBlock(BaseModel):
    overall_assessment: str
    talk_listen_ratio: TalkListenRatio
    pace_wpm: int
    filler_rate_pct: float
    questions_asked: int
    longest_monologue_sec: int
    strengths: list[str] = Field(default_factory=list)
    coaching_recommendations: list[CoachingTip] = Field(default_factory=list)


class TopicItem(BaseModel):
    name: str
    weight: float = Field(ge=0, le=1)

    @field_validator("weight", mode="before")
    @classmethod
    def _scale_weight(cls, v: Any) -> Any:
        return _percent_to_fraction(v)


class PivotalMoment(BaseModel):
    start_ms: int = 0
    label: str
    quote: str
    why_it_matters: str


class NextStep(BaseModel):
    owner: str
    action: str
    due_hint: str = ""


class SentimentTrajectory(BaseModel):
    opening: str
    middle: str
    closing: str
    opening_quote: str = ""
    middle_quote: str = ""
    closing_quote: str = ""
    opening_score: int = Field(default=50, ge=0, le=100)
    middle_score: int = Field(default=50, ge=0, le=100)
    closing_score: int = Field(default=50, ge=0, le=100)


class PostCallAnalysisResult(BaseModel):
    executive_summary: str
    client_intent: ClientIntentBlock
    rep_communication: RepCommunicationBlock
    topics: list[TopicItem] = Field(default_factory=list)
    pivotal_moments: list[PivotalMoment] = Field(default_factory=list)
    next_steps: list[NextStep] = Field(default_factory=list)
    sentiment_trajectory: SentimentTrajectory


ANALYSIS_PROMPT = """You are a senior sales call analyst (Read AI / Gong style).

Analyze the sales call transcript below. Focus on:
1) CLIENT INTENT — why the prospect called, buying signals, objections, interest level, conversion likelihood.
2) REP COMMUNICATION — how the salesperson spoke (pace, listening balance, questions, monologues).

RULES:
- {language_rule}
- All evidence_quote and *_quote fields must be VERBATIM from the transcript — never translate or paraphrase quotes, whatever language they are in.
- Use ONLY quotes that appear in the transcript for evidence_quote fields.
- Use the provided METRICS for rep_communication numeric fields (do not invent numbers).
- interest_score and conversion_probability_pct must reflect evidence from the call (not generic).
- Limit pivotal_moments to at most 5 items; keep quotes short.
- Be specific to this call, not generic sales advice.
- Return valid JSON matching this schema exactly:
{{
  "executive_summary": "string (2-3 sentences max)",
  "client_intent": {{
    "primary_intent": "short_snake_case_label",
    "summary": "string",
    "interest_score": 0,
    "engagement_level": "low|medium|high|very_high",
    "conversion_likelihood": "low|medium|high",
    "conversion_probability_pct": 0,
    "conversion_rationale": "why this probability, cite behavior not hope",
    "buying_signals": [{{"signal": "", "evidence_quote": "", "confidence": 0.0}}],
    "objections": [{{"objection": "", "evidence_quote": "", "severity": "low|medium|high"}}],
    "open_questions_unresolved": ["string"]
  }},
  "rep_communication": {{
    "overall_assessment": "string",
    "talk_listen_ratio": {{"rep_pct": 0, "prospect_pct": 0, "benchmark_note": ""}},
    "pace_wpm": 0,
    "filler_rate_pct": 0.0,
    "questions_asked": 0,
    "longest_monologue_sec": 0,
    "strengths": ["string"],
    "coaching_recommendations": [{{"area": "", "recommendation": "", "example_moment_ms": 0}}]
  }},
  "topics": [{{"name": "", "weight": 0.0}}],
  "pivotal_moments": [{{"start_ms": 0, "label": "", "quote": "", "why_it_matters": ""}}],
  "next_steps": [{{"owner": "rep|prospect", "action": "", "due_hint": ""}}],
  "sentiment_trajectory": {{"opening": "", "middle": "", "closing": "", "opening_quote": "", "middle_quote": "", "closing_quote": "", "opening_score": 0, "middle_score": 0, "closing_score": 0}}
}}

All *_score and *_pct fields must be integers from 0 to 100 (not 0–10).
Every sentiment phase score MUST be justified by its *_quote — a short verbatim
quote from that phase of the transcript. No quote, no confident score: use 50.

METRICS (computed, use these numbers in rep_communication):
{metrics_json}

TRANSCRIPT (speaker labels: rep = salesperson, prospect = client/lead):
{transcript}
"""


def format_transcript_for_prompt(segments: list[dict[str, Any]]) -> str:
    """
    Build a readable transcript block for the LLM prompt. The full call is sent;
    ANALYSIS_TRANSCRIPT_MAX_CHARS is a safety ceiling no real call should hit.

    Example::

        text = format_transcript_for_prompt([
            {"role": "prospect", "text": "What is the 3BHK price?", "start_ms": 12000},
        ])
        # -> "[00:12] prospect: What is the 3BHK price?"
    """
    lines = []
    for segment in segments:
        role = segment.get("role", "unknown")
        line_text = (segment.get("text") or "").strip()
        if not line_text:
            continue
        start_ms = segment.get("start_ms")
        prefix = ""
        if start_ms is not None:
            sec = int(start_ms) // 1000
            prefix = f"[{sec // 60:02d}:{sec % 60:02d}] "
        lines.append(f"{prefix}{role}: {line_text}")
    body = "\n".join(lines)
    max_chars = settings.ANALYSIS_TRANSCRIPT_MAX_CHARS
    if len(body) <= max_chars:
        return body
    logger.warning(
        "Transcript exceeds ANALYSIS_TRANSCRIPT_MAX_CHARS (%d > %d) — trimming tail",
        len(body),
        max_chars,
    )
    return body[: max_chars - 80] + "\n...(transcript trimmed for analysis)..."


def normalize_analysis_scores(analysis: PostCallAnalysisResult) -> PostCallAnalysisResult:
    """
    Rescale LLM outputs that used a 0–10 scale instead of 0–100.
    Values are only rescaled, never invented.

    Example::

        report = normalize_analysis_scores(PostCallAnalysisResult.model_validate(data))
    """
    ci = analysis.client_intent
    if ci.interest_score <= 10 and (
        ci.conversion_probability_pct > 40 or ci.engagement_level in ("high", "very_high")
    ):
        ci.interest_score = min(100, ci.interest_score * 10)
        analysis.client_intent = ci

    traj = analysis.sentiment_trajectory
    peak = max(traj.opening_score, traj.middle_score, traj.closing_score)
    if 0 < peak <= 10:
        traj.opening_score = min(100, traj.opening_score * 10)
        traj.middle_score = min(100, traj.middle_score * 10)
        traj.closing_score = min(100, traj.closing_score * 10)
        analysis.sentiment_trajectory = traj

    return analysis


def apply_computed_metrics(
    analysis: PostCallAnalysisResult, metrics: dict[str, Any]
) -> PostCallAnalysisResult:
    """
    Replace LLM-guessed numbers with values from ``compute_speech_metrics``.

    Example::

        report = apply_computed_metrics(validated, {"rep_wpm": 142, "talk_listen_ratio": {...}})
    """
    ratio = metrics.get("talk_listen_ratio") or {}
    rep = analysis.rep_communication
    rep.talk_listen_ratio = TalkListenRatio(
        rep_pct=int(ratio.get("rep_pct", rep.talk_listen_ratio.rep_pct)),
        prospect_pct=int(ratio.get("prospect_pct", rep.talk_listen_ratio.prospect_pct)),
        benchmark_note=str(ratio.get("benchmark_note", rep.talk_listen_ratio.benchmark_note)),
    )
    rep.pace_wpm = int(metrics.get("rep_wpm", rep.pace_wpm))
    rep.filler_rate_pct = float(metrics.get("rep_filler_rate_pct", rep.filler_rate_pct))
    rep.questions_asked = int(metrics.get("rep_questions_asked", rep.questions_asked))
    rep.longest_monologue_sec = int(
        metrics.get("longest_rep_monologue_sec", rep.longest_monologue_sec)
    )
    analysis.rep_communication = rep
    return analysis


def build_coaching_insight(
    topics: list[TopicItem],
    glance: dict[str, Any],
) -> str:
    """Deterministic coaching tip for the Client Intent dashboard."""
    if not topics:
        rep_pct = int(glance.get("rep_talk_pct") or 0)
        if rep_pct > 65:
            return (
                "Pro tip: You did most of the talking. Pause more often and ask "
                "open-ended questions so the prospect can share priorities."
            )
        return (
            "Pro tip: Review the transcript for unanswered prospect questions — "
            "closing those gaps often improves conversion."
        )

    ranked = sorted(topics, key=lambda t: t.weight, reverse=True)
    top = ranked[0].name
    pricing_keywords = ("pricing", "payment", "budget", "cost", "finance")
    undercovered = [
        t
        for t in topics
        if any(k in t.name.lower() for k in pricing_keywords) and t.weight < 0.18
    ]
    if undercovered and ranked[0].weight >= 0.25:
        return (
            f"Pro tip: Great job covering key topics. You spent the most time on "
            f"{top}—consider more time on {undercovered[0].name}."
        )

    if len(ranked) >= 2 and ranked[0].weight - ranked[1].weight < 0.08:
        return (
            f"Pro tip: Discussion was balanced across {ranked[0].name} and "
            f"{ranked[1].name}. Confirm which topic drives the prospect's decision."
        )

    return (
        f"Pro tip: Great job covering key topics. You spent the most time on "
        f"{top}—keep tying benefits back to the prospect's stated priorities."
    )


def finalize_dashboard_metrics(
    metrics: dict[str, Any],
    analysis: PostCallAnalysisResult | None = None,
) -> dict[str, Any]:
    """Attach dashboard-friendly glance stats, measured curves, and coaching insight."""
    metrics["call_glance"] = build_call_glance(metrics)
    timeline = metrics.get("call_timeline") or {}
    if timeline.get("buckets"):
        metrics["engagement_curves"] = build_engagement_curves(timeline)
    if analysis is not None:
        traj = analysis.sentiment_trajectory
        # AI-assessed (quote-backed) phase scores — the UI labels them as such.
        metrics["phase_scores"] = {
            "opening": traj.opening_score,
            "middle": traj.middle_score,
            "closing": traj.closing_score,
        }
    topics = analysis.topics if analysis else []
    metrics["coaching_insight"] = build_coaching_insight(topics, metrics["call_glance"])
    return metrics


def segment_start_for_quote(segments: list[dict[str, Any]], quote: str) -> int | None:
    """Find segment start_ms whose text best matches an evidence quote."""
    needle = (quote or "").strip().lower()
    if len(needle) < 12:
        return None
    snippet = needle[:48]
    for segment in segments:
        hay = (segment.get("text") or "").lower()
        if snippet in hay or needle in hay:
            start = segment.get("start_ms")
            return int(start) if start is not None else None
    return None


def enrich_call_timeline(
    timeline: dict[str, Any],
    analysis: PostCallAnalysisResult,
    segments: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Anchor objection and pivotal-moment markers onto the measured timeline.

    Buckets keep only measured values (talk share, words, questions). Markers
    are placed by locating each evidence quote in the actual transcript — no
    synthetic sentiment/interest series are generated.

    Example::

        metrics["call_timeline"] = enrich_call_timeline(
            metrics["call_timeline"], validated, segment_dicts
        )
    """
    buckets = timeline.get("buckets") or []
    if not buckets:
        return timeline

    count = len(buckets)
    duration_ms = max(int(timeline.get("duration_ms") or 1), 1)
    markers: list[dict[str, Any]] = list(timeline.get("markers") or [])

    for objection in analysis.client_intent.objections:
        start_ms = segment_start_for_quote(segments, objection.evidence_quote)
        if start_ms is None:
            continue
        idx = min(count - 1, int(start_ms / duration_ms * count))
        severity = {"high": 90, "medium": 70}.get(objection.severity, 50)
        buckets[idx]["objection_score"] = max(buckets[idx].get("objection_score", 0), severity)
        buckets[idx].setdefault("events", []).append(f"objection: {objection.objection}")
        markers.append(
            {"start_ms": start_ms, "type": "objection", "label": objection.objection}
        )

    for moment in analysis.pivotal_moments:
        # Prefer the quote's real position over the LLM's start_ms guess.
        start_ms = segment_start_for_quote(segments, moment.quote)
        markers.append(
            {
                "start_ms": int(moment.start_ms) if start_ms is None else start_ms,
                "type": "pivotal",
                "label": moment.label,
            }
        )

    timeline["markers"] = markers
    timeline["buckets"] = buckets
    return timeline


def parse_llm_json(text: str) -> dict[str, Any]:
    """
    Parse JSON from an LLM response, stripping optional markdown fences.

    Example::

        parse_llm_json('{"executive_summary": "Short call about pricing."}')
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)


def generate_gemini_analysis(prompt: str, model_name: str) -> str:
    """
    Call Gemini with JSON response mode for post-call analysis.

    Example::

        raw = generate_gemini_analysis(prompt, settings.ANALYSIS_GEMINI_MODEL)
    """
    client = get_gemini_client()
    if client is None:
        raise RuntimeError("GEMINI_API_KEY is not set for post-call analysis")
    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            temperature=0.2,
            max_output_tokens=settings.ANALYSIS_MAX_OUTPUT_TOKENS,
            response_mime_type="application/json",
        ),
    )
    return (response.text or "").strip()


def generate_openai_analysis(prompt: str, model_name: str) -> str:
    """
    Call OpenAI with JSON response mode for post-call analysis.

    Example::

        raw = generate_openai_analysis(prompt, "gpt-4o-mini")
    """
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {
                "role": "system",
                "content": "Return only valid JSON for the requested call analysis schema.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        max_tokens=settings.ANALYSIS_MAX_OUTPUT_TOKENS,
        response_format={"type": "json_object"},
    )
    return (response.choices[0].message.content or "").strip()


def generate_analysis_text(prompt: str) -> tuple[str, str]:
    """
    Run the configured analysis LLM and return ``(raw_json_text, model_name)``.

    Uses ``ANALYSIS_LLM_PROVIDER`` when set, otherwise ``LLM_PROVIDER``.

    Example::

        raw_json, model = generate_analysis_text(prompt)
    """
    provider = (settings.ANALYSIS_LLM_PROVIDER or settings.LLM_PROVIDER).lower().strip()
    if provider == "openai":
        if not settings.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not set for post-call analysis")
        model = settings.ANALYSIS_OPENAI_MODEL
        return generate_openai_analysis(prompt, model), model
    if not settings.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set for post-call analysis")
    model = settings.ANALYSIS_GEMINI_MODEL
    return generate_gemini_analysis(prompt, model), model


# Post-call analysis runs in the background — nobody is staring at a spinner —
# so a few seconds of retry is free insurance against the LLM provider's own
# transient overload (e.g. Gemini's "503 UNAVAILABLE — high demand" error),
# which is by far the most common reason a call lands on "failed" for no
# fault of the call itself.
_TRANSIENT_ANALYSIS_RETRIES = 2
_TRANSIENT_ANALYSIS_BACKOFF_SECONDS = 4.0


async def generate_analysis_with_retries(
    prompt: str, conversation_id: str
) -> tuple[str, str]:
    last_error: Exception = RuntimeError("no attempt made")
    for attempt in range(_TRANSIENT_ANALYSIS_RETRIES + 1):
        try:
            return await asyncio.to_thread(generate_analysis_text, prompt)
        except Exception as e:
            last_error = e
            if attempt == _TRANSIENT_ANALYSIS_RETRIES:
                break
            wait = _TRANSIENT_ANALYSIS_BACKOFF_SECONDS * (attempt + 1)
            logger.warning(
                "Post-call analysis LLM call failed (attempt %d/%d), retrying in %.0fs "
                "conversation=%s: %s",
                attempt + 1,
                _TRANSIENT_ANALYSIS_RETRIES + 1,
                wait,
                conversation_id,
                e,
            )
            await asyncio.sleep(wait)
    raise last_error


async def run_post_call_analysis(conversation_id: str) -> None:
    """
    Load a saved call, compute metrics, run the LLM, and persist the report.

    On success the conversation status becomes ``ready``. On failure both the
    conversation and analysis row are marked ``failed``.

    Example::

        await run_post_call_analysis("abc-123")
    """
    if not database_enabled():
        return

    bundle = await load_conversation_bundle(conversation_id)
    if bundle is None:
        return

    conversation = bundle["conversation"]
    segments = bundle["segments"]
    suggestions = bundle["suggestions"]
    metrics: dict[str, Any] = {}
    analysis_row_id: int | None = None
    model_name = ""

    if not segments:
        await set_conversation_status(
            conversation_id, "ready", error="No transcript segments to analyze"
        )
        return

    segment_dicts = [
        {
            "speaker_id": s.speaker_id,
            "role": s.role,
            "text": s.text,
            "word_count": s.word_count,
            "start_ms": s.start_ms,
            "end_ms": s.end_ms,
        }
        for s in segments
    ]
    suggestion_dicts = [
        {
            "trigger_query": s.trigger_query,
            "suggestion_text": s.suggestion_text,
            "from_cache": s.from_cache,
            "latency_ms": s.latency_ms,
        }
        for s in suggestions
    ]
    metrics = compute_speech_metrics(
        segment_dicts, suggestion_dicts, lead_speaker_id=conversation.lead_speaker_id
    )

    if settings.ANALYSIS_REPORT_LANGUAGE == "auto":
        language_rule = (
            "Write all free-text fields (summaries, assessments, recommendations) in the "
            "same language as the call; if the call mixes Hindi and English, use simple "
            "Hinglish in Roman script."
        )
    else:
        language_rule = (
            "Write all free-text fields (summaries, assessments, recommendations) in "
            "clear, simple English — even when the call is in another language."
        )

    prompt = ANALYSIS_PROMPT.format(
        language_rule=language_rule,
        metrics_json=json.dumps(metrics, indent=2),
        transcript=format_transcript_for_prompt(segment_dicts),
    )

    try:
        async with get_db() as session:
            version = await next_analysis_version(session, conversation_id)
            row = ConversationAnalysis(
                conversation_id=conversation_id,
                version=version,
                status="running",
                metrics=metrics,
                created_at=datetime.now(UTC),
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            analysis_row_id = row.id

        raw, model_name = await generate_analysis_with_retries(prompt, conversation_id)
        parsed: dict[str, Any] | None = None
        for attempt in range(2):
            try:
                parsed = parse_llm_json(raw)
                break
            except json.JSONDecodeError:
                if attempt == 0:
                    logger.warning(
                        "Post-call JSON parse failed; retrying once conversation=%s",
                        conversation_id,
                    )
                    raw, model_name = await generate_analysis_with_retries(
                        prompt, conversation_id
                    )
                    continue
                raise
        validated = PostCallAnalysisResult.model_validate(parsed)
        validated = normalize_analysis_scores(validated)
        validated = apply_computed_metrics(validated, metrics)
        metrics["call_timeline"] = enrich_call_timeline(
            metrics.get("call_timeline") or {},
            validated,
            segment_dicts,
        )
        finalize_dashboard_metrics(metrics, validated)

        async with get_db() as session:
            row = await session.get(ConversationAnalysis, analysis_row_id)
            if row is not None:
                row.status = "ready"
                row.model = model_name
                row.analysis = validated.model_dump()
                row.metrics = metrics
            conv = await session.get(Conversation, conversation_id)
            if conv is not None:
                conv.status = "ready"
            await session.commit()

        logger.info(
            "Post-call analysis ready conversation=%s model=%s", conversation_id, model_name
        )

    except Exception as e:
        logger.exception("Post-call analysis failed conversation=%s: %s", conversation_id, e)
        async with get_db() as session:
            if analysis_row_id is not None:
                row = await session.get(ConversationAnalysis, analysis_row_id)
                if row is not None:
                    row.status = "failed"
                    row.error = str(e)
                    if metrics:
                        row.metrics = metrics
            conv = await session.get(Conversation, conversation_id)
            if conv is not None:
                conv.status = "failed"
                conv.extra = {**(conv.extra or {}), "analysis_error": str(e)}
            await session.commit()


async def refresh_call_metrics(conversation_id: str) -> bool:
    """
    Recompute transcript metrics and timeline without calling the LLM.

  Uses the latest saved analysis to enrich ``call_timeline``. Safe when Gemini
  quota is exhausted.

    Example::

        updated = await refresh_call_metrics("abc-123")
    """
    bundle = await load_conversation_bundle(conversation_id)
    if bundle is None or not bundle["segments"]:
        return False

    conversation = bundle["conversation"]
    segment_dicts = [
        {
            "speaker_id": s.speaker_id,
            "role": s.role,
            "text": s.text,
            "word_count": s.word_count,
            "start_ms": s.start_ms,
            "end_ms": s.end_ms,
        }
        for s in bundle["segments"]
    ]
    suggestion_dicts = [
        {
            "trigger_query": s.trigger_query,
            "suggestion_text": s.suggestion_text,
            "from_cache": s.from_cache,
            "latency_ms": s.latency_ms,
        }
        for s in bundle["suggestions"]
    ]
    metrics = compute_speech_metrics(
        segment_dicts, suggestion_dicts, lead_speaker_id=conversation.lead_speaker_id
    )

    async with get_db() as session:
        result = await session.execute(
            select(ConversationAnalysis)
            .where(
                ConversationAnalysis.conversation_id == conversation_id,
                ConversationAnalysis.status == "ready",
            )
            .order_by(desc(ConversationAnalysis.version))
            .limit(1)
        )
        row = result.scalar_one_or_none()
        if row is not None and row.analysis:
            try:
                validated = PostCallAnalysisResult.model_validate(row.analysis)
                metrics["call_timeline"] = enrich_call_timeline(
                    metrics.get("call_timeline") or {},
                    validated,
                    segment_dicts,
                )
                finalize_dashboard_metrics(metrics, validated)
            except Exception:
                finalize_dashboard_metrics(metrics)
            row.metrics = metrics
            await session.commit()
            return True
    return False


async def schedule_post_call_analysis(conversation_id: str) -> None:
    """
    Fire-and-forget entry point used from the WebSocket ``finally`` block.

    Catches any uncaught error and marks the conversation failed.

    Example::

        asyncio.create_task(schedule_post_call_analysis(session_id))
    """
    try:
        await run_post_call_analysis(conversation_id)
    except Exception as e:
        logger.exception(
            "schedule_post_call_analysis failed conversation=%s: %s",
            conversation_id,
            e,
        )
        await set_conversation_status(conversation_id, "failed", error=str(e))
