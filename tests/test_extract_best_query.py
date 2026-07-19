"""
Scenario tests for _extract_best_query.

These mirror how the assistant is used after diarization + lead filtering: the
model receives *only the lead's* recent utterances as `turns`. Each scenario is
a slice of a plausible sales / discovery call.
"""

from app.modules.conversation_intelligence.conversation_manager import (
    _extract_best_query,
)


class TestRealEstateDiscoveryCall:
    """Lead is the buyer; turns are already lead-only (rep talk stripped upstream)."""

    def test_buyer_asks_pointed_question_after_context_turn(self) -> None:
        """
        Buyer first states interest, then asks a specific question — the last
        turn is a clear question with enough words, so retrieval should target
        that question alone.
        """
        turns = [
            "We drove by the Maple Street listing last weekend.",
            "What are the annual property taxes and are they escrowed?",
        ]
        q = _extract_best_query(turns)
        assert "tax" in q.lower() or "taxes" in q.lower()
        assert "escrow" in q.lower()

    def test_buyer_asks_follow_up_about_financing(self) -> None:
        turns = [
            "The asking price is in our range.",
            "How does the rate lock work if we are not closing for sixty days?",
        ]
        q = _extract_best_query(turns)
        assert "rate" in q.lower() or "lock" in q.lower()
        assert "sixty" in q.lower() or "closing" in q.lower()

    def test_buyer_uses_fillers_but_question_stays_intelligible(self) -> None:
        """
        Spoken disfluencies should not remove the semantic core of the question.
        """
        turns = [
            "Um, so, like, what is the MLS number for the Oak Lane property?",
        ]
        q = _extract_best_query(turns)
        assert "mls" in q.lower()
        assert "oak" in q.lower() or "property" in q.lower()


class TestWhenLastTurnIsNotAQuestion:
    """Heuristic joins the previous turn for retrieval context."""

    def test_buyer_requests_more_detail_without_question_mark(self) -> None:
        turns = [
            "The roof was replaced in twenty twenty one according to the disclosure.",
            "Tell me more about that work and who did the inspection.",
        ]
        q = _extract_best_query(turns)
        assert "roof" in q.lower() or "twenty" in q.lower()
        assert "inspection" in q.lower() or "more" in q.lower()


class TestShortFollowUpMergesThreeTurns:
    """Spoken 'and 3BHK' after a price question must keep both configurations in the query."""

    def test_and_three_bhk_after_okay(self) -> None:
        turns = [
            "What is the price of 2BHK in Raymond Realty?",
            "Okay.",
            "And three BHK.",
        ]
        q = _extract_best_query(turns)
        low = q.lower()
        assert ("2" in low or "two" in low) and ("3" in low or "three" in low)


class TestShortOrThinTurns:
    def test_empty_means_no_retrieval_signal(self) -> None:
        assert _extract_best_query([]) == ""

    def test_single_acknowledgment_is_all_we_have(self) -> None:
        """Single short non-question turn — still returned as the only signal."""
        q = _extract_best_query(["Sounds good."])
        assert q  # stripped but non-empty


class TestConversationManagerLeadOnlyScenarios:
    """
    End-to-end behavior: channel-tagged segments → history → lead-only window →
    _extract_best_query. Speaker ids are audio channels: 0 = rep mic, 1 = tab
    audio (the customer). Uses an isolated ConversationManager (not the app
    singleton).
    """

    def test_tab_channel_is_lead_and_drives_focused_query(self) -> None:
        """Once channel 1 (customer) speaks, only its lines inform retrieval."""
        import asyncio

        from app.modules.conversation_intelligence.conversation_manager import (
            ConversationManager,
        )
        from app.services.transcript_types import TranscriptSegment

        async def scenario():
            cm = ConversationManager()
            sid = await cm.create_session()
            _, fq, speakers, lead = await cm.add_segments_and_get_focused_query(
                sid,
                [
                    TranscriptSegment(text="Thanks for hopping on today.", speaker=0),
                    TranscriptSegment(
                        text="What are the monthly HOA dues?", speaker=1
                    ),
                ],
            )
            assert sorted(speakers) == [0, 1]
            assert lead == 1
            assert "hoa" in fq.lower() or "dues" in fq.lower()
            await cm.close()

        asyncio.run(scenario())

    def test_rep_talk_between_customer_turns_does_not_pollute_query(self) -> None:
        """Rep (channel 0) filler between customer questions must not appear
        in the retrieval query."""
        import asyncio

        from app.modules.conversation_intelligence.conversation_manager import (
            ConversationManager,
        )
        from app.services.transcript_types import TranscriptSegment

        async def scenario():
            cm = ConversationManager()
            sid = await cm.create_session()
            _, fq, _, lead = await cm.add_segments_and_get_focused_query(
                sid,
                [
                    TranscriptSegment(
                        text="Let me pull the listing photos on my second screen.",
                        speaker=0,
                    ),
                    TranscriptSegment(
                        text="What time is the open house this Saturday?",
                        speaker=1,
                    ),
                ],
            )
            assert lead == 1
            low = fq.lower()
            assert "open house" in low or "saturday" in low
            assert "second screen" not in low and "pull" not in low
            await cm.close()

        asyncio.run(scenario())

    def test_mic_only_session_treats_single_channel_as_lead(self) -> None:
        """No tab share (demo / phone on speaker) → the lone mic channel is the lead."""
        import asyncio

        from app.modules.conversation_intelligence.conversation_manager import (
            ConversationManager,
        )
        from app.services.transcript_types import TranscriptSegment

        async def scenario():
            cm = ConversationManager()
            sid = await cm.create_session()
            _, fq, speakers, lead = await cm.add_segments_and_get_focused_query(
                sid,
                [
                    TranscriptSegment(
                        text="Could you email me the seller disclosure packet?",
                        speaker=0,
                    ),
                ],
            )
            assert speakers == [0]
            assert lead == 0
            assert "disclosure" in fq.lower() or "email" in fq.lower()
            await cm.close()

        asyncio.run(scenario())
