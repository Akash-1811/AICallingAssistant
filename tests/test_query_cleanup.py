"""Query cleanup contract tests: normalization, dedup, and BHK cache-compat slots."""

from app.core.config import settings
from app.rag.query_cleanup import (
    config_slots,
    dominant_language_hint,
    normalize_live_query,
    queries_are_near_duplicate,
    semantic_cache_compatible,
)


def test_normalize_live_query_typo_kane_to_thane():
    assert "Thane West" in normalize_live_query("project in kane west near mall")


def test_normalize_live_query_strips_trailing_politeness():
    t = normalize_live_query(
        "what is the price for 2BHK, thank you sir"
    )
    assert "thank you" not in t.lower()


def test_dominant_language_hint_english():
    assert dominant_language_hint("What is the price for 2BHK") == "en"


def test_dominant_language_hint_hindi_heavy():
    assert dominant_language_hint("मुझे बजट बताइए और लोन के बारे में") == "hi"


def test_queries_near_duplicate_true(monkeypatch):
    monkeypatch.setattr(settings, "QUERY_DEDUP_ENABLED", True)
    monkeypatch.setattr(settings, "QUERY_DEDUP_JACCARD_THRESHOLD", 0.72)
    a = "what is the starting price for two BHK apartment"
    b = "what is the starting price for two BHK apartments"
    assert queries_are_near_duplicate(a, b) is True


def test_queries_near_duplicate_false_different_bhk(monkeypatch):
    monkeypatch.setattr(settings, "QUERY_DEDUP_ENABLED", True)
    monkeypatch.setattr(settings, "QUERY_DEDUP_JACCARD_THRESHOLD", 0.72)
    a = "what is the price for 2 BHK"
    b = "what is the price for 3 BHK"
    assert queries_are_near_duplicate(a, b) is False


def test_queries_near_duplicate_disabled(monkeypatch):
    monkeypatch.setattr(settings, "QUERY_DEDUP_ENABLED", False)
    assert queries_are_near_duplicate("same words", "same words") is False


class TestConfigSlots:
    def test_two_and_three_bhk(self) -> None:
        assert config_slots("What is the price of 2 BHK and 3 BHK?") == frozenset(
            {"2bhk", "3bhk"}
        )

    def test_spoken_numbers(self) -> None:
        assert config_slots("two BHK flat") == frozenset({"2bhk"})
        assert config_slots("three bhk cost") == frozenset({"3bhk"})


class TestSemanticCacheCompatible:
    def test_same_slots(self) -> None:
        assert semantic_cache_compatible(
            "what is 2bhk price in thane",
            "price for 2 bhk raymond",
        )

    def test_different_slots_reject(self) -> None:
        assert not semantic_cache_compatible(
            "what is 3bhk price",
            "what is 2bhk price",
        )

    def test_legacy_no_cached_norm(self) -> None:
        assert semantic_cache_compatible("generic pricing question", None)
        assert not semantic_cache_compatible("what is 3bhk price", None)
