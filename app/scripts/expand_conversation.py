"""
Expand an existing saved conversation with a longer transcript and re-run analysis.

Usage::

    python -m app.scripts.expand_conversation
    python -m app.scripts.expand_conversation --id <conversation-uuid>
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from app.call_store import (
    Conversation,
    SuggestionRow,
    TranscriptSegmentRow,
    get_db,
    init_database,
)
from app.services.post_call_analysis import run_post_call_analysis

DEFAULT_CONVERSATION_ID = "7d593e0a-aa11-4151-b42f-4258468098c3"
LEAD_SPEAKER_ID = 1

# ~18 minute discovery call — Goregaon 3BHK (Raymond Realty context)
TRANSCRIPT = [
    {"speaker_id": 0, "role": "rep", "text": "Good afternoon, thank you for calling Raymond Realty. My name is Priya. How can I help you today?", "start_ms": 0, "end_ms": 6500},
    {"speaker_id": 1, "role": "prospect", "text": "Hi Priya, I saw your ad for the Goregaon project. We are looking for a three BHK with a sea view if possible.", "start_ms": 7000, "end_ms": 14500},
    {"speaker_id": 0, "role": "rep", "text": "Great choice. May I ask what budget range you are comfortable with, and when are you planning to move in?", "start_ms": 15000, "end_ms": 21000},
    {"speaker_id": 1, "role": "prospect", "text": "We are thinking around two crore, maybe stretch to two point two. Move-in would be within six months.", "start_ms": 21500, "end_ms": 28000},
    {"speaker_id": 0, "role": "rep", "text": "Perfect. We have a three BHK in Tower B facing the western skyline starting at about one point nine five crore. Is Goregaon West your preferred micro-market?", "start_ms": 28500, "end_ms": 37000},
    {"speaker_id": 1, "role": "prospect", "text": "Yes, near the station would be ideal. My office is in Andheri East so commute matters.", "start_ms": 37500, "end_ms": 43000},
    {"speaker_id": 0, "role": "rep", "text": "Understood. The site is roughly twelve minutes from Goregaon station off the main road. Do you need two parking slots?", "start_ms": 43500, "end_ms": 50000},
    {"speaker_id": 1, "role": "prospect", "text": "Yes, two covered parking spaces. We also want a higher floor — at least fifteenth plus for the view.", "start_ms": 50500, "end_ms": 57000},
    {"speaker_id": 0, "role": "rep", "text": "We still have inventory on floors fifteen through twenty-two in that tower. The premium for a sea-facing unit is roughly eight to twelve lakhs depending on floor.", "start_ms": 57500, "end_ms": 66000},
    {"speaker_id": 1, "role": "prospect", "text": "That is within range. What is the carpet area for the three BHK configuration?", "start_ms": 66500, "end_ms": 71000},
    {"speaker_id": 0, "role": "rep", "text": "The carpet is approximately nine hundred eighty square feet with an attached deck on the living room.", "start_ms": 71500, "end_ms": 77000},
    {"speaker_id": 1, "role": "prospect", "text": "Hmm, one point nine five sounds good but I am worried about the maintenance charges. Last project we saw had very high society fees.", "start_ms": 77500, "end_ms": 85000},
    {"speaker_id": 0, "role": "rep", "text": "Fair concern. Maintenance here is roughly twelve rupees per square foot, and we can share the full breakup on email. It is competitive for a branded developer in this micro-market.", "start_ms": 85500, "end_ms": 94000},
    {"speaker_id": 1, "role": "prospect", "text": "Okay. What about the payment plan? We can put down thirty percent but need flexibility on the next two tranches.", "start_ms": 94500, "end_ms": 101000},
    {"speaker_id": 0, "role": "rep", "text": "We offer a construction-linked plan: ten percent on booking, twenty on agreement, and the balance tied to milestones. I can send a customized schedule.", "start_ms": 101500, "end_ms": 109000},
    {"speaker_id": 1, "role": "prospect", "text": "We are also comparing Lodha's project in the same belt. How would you differentiate?", "start_ms": 109500, "end_ms": 115000},
    {"speaker_id": 0, "role": "rep", "text": "Raymond offers lower density — four apartments per floor, dedicated club house, and possession track record in this corridor. Happy to share a side-by-side comparison sheet.", "start_ms": 115500, "end_ms": 124000},
    {"speaker_id": 1, "role": "prospect", "text": "That would help. My wife cares a lot about kids' amenities — is there a pool and indoor play area?", "start_ms": 124500, "end_ms": 130000},
    {"speaker_id": 0, "role": "rep", "text": "Yes, rooftop pool, indoor games room, and a co-working lounge. The sample flat is ready on site.", "start_ms": 130500, "end_ms": 136500},
    {"speaker_id": 1, "role": "prospect", "text": "Good. Any bank tie-ups for home loans? We are pre-approved with HDFC but open to others if the rate is better.", "start_ms": 137000, "end_ms": 143500},
    {"speaker_id": 0, "role": "rep", "text": "We have tie-ups with HDFC, ICICI, and SBI. Subvention schemes may be available depending on the tower — I will confirm with finance.", "start_ms": 144000, "end_ms": 151000},
    {"speaker_id": 1, "role": "prospect", "text": "One more thing — is the western view actually sea view or just city skyline? That is important for us.", "start_ms": 151500, "end_ms": 157500},
    {"speaker_id": 0, "role": "rep", "text": "Floors eighteen and above get a clear sea glimpse on the west; lower floors are predominantly skyline. I can mark the best stacks on the floor plan.", "start_ms": 158000, "end_ms": 166000},
    {"speaker_id": 1, "role": "prospect", "text": "That clarifies it. Yes please, send the brochure, payment plan, and maintenance sheet to rajesh dot mehta at gmail.", "start_ms": 166500, "end_ms": 173000},
    {"speaker_id": 0, "role": "rep", "text": "Will do today. If the numbers look right, would Saturday morning work for a site visit with your wife?", "start_ms": 173500, "end_ms": 179000},
    {"speaker_id": 1, "role": "prospect", "text": "Saturday around ten works. If the sample flat matches what we discussed, we can discuss token amount on the spot.", "start_ms": 179500, "end_ms": 185500},
    {"speaker_id": 0, "role": "rep", "text": "Excellent. I will block ten A M and share the site map and visitor pass. Thank you for your time, Rajesh — speak soon.", "start_ms": 186000, "end_ms": 192000},
]

SUGGESTIONS = [
    {"generation_id": 1, "trigger_query": "three bhk goregaon sea view", "suggestion_text": "Confirm tower name and floor band for sea glimpse. Ask if Andheri commute is non-negotiable.", "from_cache": False, "latency_ms": 840},
    {"generation_id": 2, "trigger_query": "budget two crore move in six months", "suggestion_text": "Anchor on 1.95 Cr starting price and 6-month possession. Offer 3BHK stack comparison within 2.2 Cr cap.", "from_cache": False, "latency_ms": 920},
    {"generation_id": 3, "trigger_query": "maintenance charges society fees", "suggestion_text": "Share ₹12/sq ft maintenance with one-page society cost breakdown vs last project they saw.", "from_cache": True, "latency_ms": 120},
    {"generation_id": 4, "trigger_query": "comparing lodha same belt", "suggestion_text": "Lead with density (4 units/floor), club amenities, and possession track record — offer comparison PDF.", "from_cache": False, "latency_ms": 1100},
    {"generation_id": 5, "trigger_query": "western view sea view or skyline", "suggestion_text": "Be precise: sea glimpse from floor 18+. Propose marking best stacks on floor plan before visit.", "from_cache": False, "latency_ms": 780},
]


async def expand_and_analyze(conversation_id: str, *, run_analysis: bool = True) -> None:
    await init_database()
    started = datetime.now(timezone.utc) - timedelta(minutes=19)
    ended = started + timedelta(minutes=18, seconds=12)

    async with get_db() as session:
        conv = await session.get(Conversation, conversation_id)
        if conv is None:
            conv = Conversation(
                id=conversation_id,
                status="analyzing",
                lead_speaker_id=LEAD_SPEAKER_ID,
                audio_channels=1,
                rep_label="Priya",
                extra={"source": "expand_conversation_script"},
            )
            session.add(conv)
            print(f"Created conversation {conversation_id}")

        await session.execute(
            delete(TranscriptSegmentRow).where(
                TranscriptSegmentRow.conversation_id == conversation_id
            )
        )
        await session.execute(
            delete(SuggestionRow).where(SuggestionRow.conversation_id == conversation_id)
        )

        conv.status = "analyzing"
        conv.lead_speaker_id = LEAD_SPEAKER_ID
        conv.started_at = started
        conv.ended_at = ended
        conv.duration_sec = 1092

        for line in TRANSCRIPT:
            session.add(
                TranscriptSegmentRow(
                    conversation_id=conversation_id,
                    speaker_id=line["speaker_id"],
                    role=line["role"],
                    text=line["text"],
                    start_ms=line["start_ms"],
                    end_ms=line["end_ms"],
                    word_count=len(str(line["text"]).split()),
                )
            )
        for sug in SUGGESTIONS:
            session.add(
                SuggestionRow(
                    conversation_id=conversation_id,
                    generation_id=sug["generation_id"],
                    trigger_query=sug["trigger_query"],
                    suggestion_text=sug["suggestion_text"],
                    from_cache=sug["from_cache"],
                    sources=[],
                    latency_ms=sug["latency_ms"],
                )
            )
        await session.commit()

    print(f"Expanded conversation {conversation_id} — {len(TRANSCRIPT)} segments")
    if run_analysis:
        await run_post_call_analysis(conversation_id)
    else:
        async with get_db() as session:
            conv = await session.get(Conversation, conversation_id)
            if conv is not None:
                conv.status = "ready"
                await session.commit()
    print(f"Done. Open: http://localhost:5173/conversations/{conversation_id}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", default=DEFAULT_CONVERSATION_ID)
    parser.add_argument("--no-analyze", action="store_true", help="Only update transcript, skip LLM")
    args = parser.parse_args()
    asyncio.run(expand_and_analyze(args.id, run_analysis=not args.no_analyze))


if __name__ == "__main__":
    main()
