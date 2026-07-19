"""
Seed full-length demo conversations and run real post-call analysis.

Usage::

    python -m app.scripts.seed_demo_conversations
    python -m app.scripts.seed_demo_conversations --email akashyadav181198@gmail.com
    python -m app.scripts.seed_demo_conversations --reset
    python -m app.scripts.seed_demo_conversations --no-analyze
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select

from app.analysis.post_call_analysis import run_post_call_analysis
from app.analysis.speech_metrics import compute_speech_metrics
from app.api.v1.auth import User
from app.scripts.demo_analysis import build_demo_analysis
from app.scripts.demo_transcripts import SCENARIO_IDS, build_scenarios
from app.storage.call_store import (
    Conversation,
    ConversationAnalysis,
    SuggestionRow,
    TranscriptSegmentRow,
    get_db,
    init_database,
)

LEAD_SPEAKER_ID = 1
EMPTY_CONVERSATION_ID = "f0ed52fc-f3e4-4112-a6dd-8c7818cb0005"


async def resolve_rep_name(email: str | None) -> str:
    async with get_db() as session:
        query = select(User)
        if email:
            query = query.where(User.email == email)
        result = await session.execute(query.limit(1))
        user = result.scalar_one_or_none()
        if user is None:
            raise SystemExit("No user found. Sign up first or pass --email.")
        return (user.display_name or user.email.split("@")[0]).strip()


async def remove_conversation(session, conversation_id: str) -> None:
    await session.execute(
        delete(ConversationAnalysis).where(ConversationAnalysis.conversation_id == conversation_id)
    )
    await session.execute(
        delete(TranscriptSegmentRow).where(TranscriptSegmentRow.conversation_id == conversation_id)
    )
    await session.execute(delete(SuggestionRow).where(SuggestionRow.conversation_id == conversation_id))
    await session.execute(delete(Conversation).where(Conversation.id == conversation_id))


async def upsert_transcript(session, rep_name: str, scenario: dict[str, Any]) -> int:
    conversation_id = scenario["id"]
    transcript = scenario["transcript"]
    suggestions = scenario.get("suggestions") or []

    duration_sec = max(1, round((transcript[-1]["end_ms"] - transcript[0]["start_ms"]) / 1000))
    started = datetime.now(UTC) - timedelta(days=scenario["days_ago"], minutes=duration_sec // 60)
    ended = started + timedelta(seconds=duration_sec)

    conv = await session.get(Conversation, conversation_id)
    if conv is None:
        conv = Conversation(id=conversation_id)
        session.add(conv)

    conv.status = "analyzing"
    conv.lead_speaker_id = LEAD_SPEAKER_ID
    conv.audio_channels = 1
    conv.rep_label = rep_name
    conv.started_at = started
    conv.ended_at = ended
    conv.duration_sec = duration_sec
    conv.extra = {"source": "seed_demo_conversations", "label": scenario["label"]}

    await session.execute(
        delete(TranscriptSegmentRow).where(TranscriptSegmentRow.conversation_id == conversation_id)
    )
    await session.execute(delete(SuggestionRow).where(SuggestionRow.conversation_id == conversation_id))
    await session.execute(
        delete(ConversationAnalysis).where(ConversationAnalysis.conversation_id == conversation_id)
    )

    for line in transcript:
        session.add(
            TranscriptSegmentRow(
                conversation_id=conversation_id,
                speaker_id=line["speaker_id"],
                role=line["role"],
                text=line["text"],
                start_ms=line["start_ms"],
                end_ms=line["end_ms"],
                word_count=len(line["text"].split()),
            )
        )
    for sug in suggestions:
        session.add(
            SuggestionRow(
                conversation_id=conversation_id,
                generation_id=sug.get("generation_id"),
                trigger_query=sug["trigger_query"],
                suggestion_text=sug["suggestion_text"],
                from_cache=sug.get("from_cache", False),
                sources=[],
                latency_ms=sug.get("latency_ms"),
            )
        )

    return duration_sec


async def apply_demo_analysis(session, rep_name: str, scenario: dict[str, Any]) -> None:
    conversation_id = scenario["id"]
    transcript = scenario["transcript"]
    suggestions = scenario.get("suggestions") or []

    segment_dicts = [
        {
            "speaker_id": line["speaker_id"],
            "role": line["role"],
            "text": line["text"],
            "start_ms": line["start_ms"],
            "end_ms": line["end_ms"],
        }
        for line in transcript
    ]
    suggestion_dicts = [
        {
            "trigger_query": item["trigger_query"],
            "suggestion_text": item["suggestion_text"],
            "from_cache": item.get("from_cache", False),
            "latency_ms": item.get("latency_ms"),
        }
        for item in suggestions
    ]
    metrics = compute_speech_metrics(segment_dicts, suggestion_dicts, lead_speaker_id=LEAD_SPEAKER_ID)
    analysis, metrics = build_demo_analysis(conversation_id, rep_name, metrics, segment_dicts)

    await session.execute(
        delete(ConversationAnalysis).where(ConversationAnalysis.conversation_id == conversation_id)
    )
    conv = await session.get(Conversation, conversation_id)
    if conv is None:
        return

    conv.status = "ready"
    session.add(
        ConversationAnalysis(
            conversation_id=conversation_id,
            version=1,
            model="seed-demo",
            status="ready",
            metrics=metrics,
            analysis=analysis.model_dump(),
            created_at=conv.ended_at or datetime.now(UTC),
        )
    )


async def analyze_scenario(rep_name: str, scenario: dict[str, Any], *, use_llm: bool) -> str:
    conversation_id = scenario["id"]
    if use_llm:
        await run_post_call_analysis(conversation_id)
        async with get_db() as session:
            result = await session.execute(
                select(ConversationAnalysis)
                .where(ConversationAnalysis.conversation_id == conversation_id)
                .order_by(ConversationAnalysis.version.desc())
                .limit(1)
            )
            row = result.scalar_one_or_none()
            if row is not None and row.status == "ready":
                return "llm"

    async with get_db() as session:
        await apply_demo_analysis(session, rep_name, scenario)
        await session.commit()
    return "seed"


async def seed_demo_conversations(
    *,
    email: str | None,
    reset: bool,
    use_llm: bool,
) -> None:
    await init_database()
    rep_name = await resolve_rep_name(email)
    scenarios = build_scenarios(rep_name)

    async with get_db() as session:
        if reset:
            result = await session.execute(select(Conversation.id))
            for (conversation_id,) in result.all():
                if conversation_id not in SCENARIO_IDS:
                    await remove_conversation(session, conversation_id)

        empty = await session.get(Conversation, EMPTY_CONVERSATION_ID)
        if empty is not None:
            await remove_conversation(session, EMPTY_CONVERSATION_ID)

        for scenario in scenarios:
            duration_sec = await upsert_transcript(session, rep_name, scenario)
            print(
                f"Loaded {scenario['label']} · {len(scenario['transcript'])} segments · "
                f"{duration_sec // 60}m {duration_sec % 60}s"
            )

        await session.commit()

    print("\nBuilding post-call analysis for each conversation…")
    for index, scenario in enumerate(scenarios, start=1):
        mode = await analyze_scenario(rep_name, scenario, use_llm=use_llm)
        print(f"[{index}/{len(scenarios)}] {scenario['label']} · {mode}")

    print(f"\nDone. {len(scenarios)} conversations seeded for {rep_name}.")
    print("Open analytics: http://localhost:5173/analytics")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed full-length demo conversations.")
    parser.add_argument("--email", help="User email to assign as rep (defaults to first user)")
    parser.add_argument("--reset", action="store_true", help="Remove conversations outside the demo set")
    parser.add_argument(
        "--llm",
        action="store_true",
        help="Try Gemini/OpenAI analysis first; falls back to seed analysis on failure",
    )
    args = parser.parse_args()
    asyncio.run(
        seed_demo_conversations(email=args.email, reset=args.reset, use_llm=args.llm)
    )


if __name__ == "__main__":
    main()
