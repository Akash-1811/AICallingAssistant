"""Unit tests for BHK intent extraction and semantic cache compatibility."""

from app.modules.rag.query_intent import config_slots, semantic_cache_compatible


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
