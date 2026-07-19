"""Closing/acknowledgement turns must be skipped — a pitch after "thank you" sounds robotic."""

import pytest

from app.live.turn_gate import is_closing_pleasantry


@pytest.mark.parametrize(
    "turn",
    [
        "Oh, great to hear this.",
        "I appreciate you. Thank you.",
        "Okay great, sounds good.",
        "Perfect, thank you so much.",
        "Alright then, talk to you later.",
        "Thanks a lot, have a great day.",
    ],
)
def test_pure_pleasantries_are_closing(turn: str) -> None:
    assert is_closing_pleasantry(turn) is True


@pytest.mark.parametrize(
    "turn",
    [
        # A question after thanks is a real turn, not a closing.
        "Thanks, but what is the price of 3BHK?",
        # Question-word starters are real asks even without a question mark.
        "What about the swimming pool",
        "How do I commute over there",
        # New information / objections must reach the pipeline.
        "That sounds good but I need to think about it and compare",
        "I would like to know more about the gym.",
        "",
    ],
)
def test_real_turns_are_not_closing(turn: str) -> None:
    assert is_closing_pleasantry(turn) is False


class TestExtractIntent:
    """The LLM tags each live turn; parsing must be forgiving but never invalid."""

    def test_accepts_all_valid_tags_with_or_without_label(self) -> None:
        from app.rag.pipeline import extract_intent

        assert extract_intent(" question") == "question"
        assert extract_intent("INTENT: opener") == "opener"
        assert extract_intent("intent: OBJECTION") == "objection"
        assert extract_intent("  closing  ") == "closing"

    def test_malformed_tags_fall_back_to_question(self) -> None:
        from app.rag.pipeline import extract_intent

        assert extract_intent("") == "question"
        assert extract_intent("something odd") == "question"
        assert extract_intent("INTENT: pricing") == "question"
