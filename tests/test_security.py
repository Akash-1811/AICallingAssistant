"""Security contracts: rate limiting, production config refusal, JWT round-trip."""

import pytest

from app.api.v1.auth import create_token, decode_token
from app.core import ratelimit
from app.core.config import settings, validate_production_settings
from app.core.ratelimit import SlidingWindowLimiter


class TestSlidingWindowLimiter:
    def test_allows_up_to_max_then_blocks(self) -> None:
        limiter = SlidingWindowLimiter(max_events=3, window_seconds=60)
        assert [limiter.allow("ip1") for _ in range(4)] == [True, True, True, False]

    def test_keys_are_independent(self) -> None:
        limiter = SlidingWindowLimiter(max_events=1, window_seconds=60)
        assert limiter.allow("ip1") is True
        assert limiter.allow("ip2") is True
        assert limiter.allow("ip1") is False

    def test_window_expiry_frees_the_slot(self, monkeypatch: pytest.MonkeyPatch) -> None:
        clock = {"now": 1000.0}
        monkeypatch.setattr(ratelimit.time, "monotonic", lambda: clock["now"])
        limiter = SlidingWindowLimiter(max_events=1, window_seconds=10)
        assert limiter.allow("k") is True
        assert limiter.allow("k") is False
        clock["now"] += 11
        assert limiter.allow("k") is True


class TestProductionValidation:
    """Production must refuse to boot with forgeable or unsafe auth config."""

    def _make_production_safe(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "ENVIRONMENT", "production")
        monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-key")
        monkeypatch.setattr(settings, "DEEPGRAM_API_KEY", "test-key")
        monkeypatch.setattr(settings, "JWT_SECRET", "x" * 32)
        monkeypatch.setattr(settings, "CORS_ORIGINS", "https://app.example.com")

    def test_safe_config_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._make_production_safe(monkeypatch)
        validate_production_settings()  # must not raise

    def test_default_jwt_secret_is_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._make_production_safe(monkeypatch)
        monkeypatch.setattr(settings, "JWT_SECRET", "dev-change-me-in-production")
        with pytest.raises(RuntimeError, match="JWT_SECRET"):
            validate_production_settings()

    def test_short_jwt_secret_is_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._make_production_safe(monkeypatch)
        monkeypatch.setattr(settings, "JWT_SECRET", "too-short")
        with pytest.raises(RuntimeError, match="32 bytes"):
            validate_production_settings()

    def test_wildcard_cors_is_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._make_production_safe(monkeypatch)
        monkeypatch.setattr(settings, "CORS_ORIGINS", "*")
        with pytest.raises(RuntimeError, match="CORS"):
            validate_production_settings()

    def test_dev_environment_skips_all_checks(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "ENVIRONMENT", "development")
        monkeypatch.setattr(settings, "JWT_SECRET", "dev-change-me-in-production")
        validate_production_settings()  # must not raise


class TestJwtRoundTrip:
    def test_created_token_decodes_to_same_user(self) -> None:
        assert decode_token(create_token("user-42")) == "user-42"

    def test_garbage_token_is_rejected(self) -> None:
        assert decode_token("not-a-jwt") is None
        assert decode_token("") is None
