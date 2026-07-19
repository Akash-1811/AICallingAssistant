"""Tests for dashboard coaching insight generation."""

from app.analysis.post_call_analysis import TopicItem, build_coaching_insight


def test_coaching_insight_suggests_pricing_when_undercovered():
    topics = [
        TopicItem(name="Property Features & Requirements", weight=0.35),
        TopicItem(name="Pricing & Payment", weight=0.1),
        TopicItem(name="Location & Commute", weight=0.15),
    ]
    tip = build_coaching_insight(topics, {"rep_talk_pct": 55})
    assert "Pricing & Payment" in tip
    assert "Pro tip:" in tip


def test_coaching_insight_when_no_topics_high_rep_talk():
    tip = build_coaching_insight([], {"rep_talk_pct": 72})
    assert "talking" in tip.lower()
