"""
Every tunable setting in one place, loaded from .env. If you are tempted to
hardcode a number anywhere else, it probably belongs here with a comment.
"""

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "AI Sales Assistant"
    # development | staging | production — in production, missing API keys fail startup
    ENVIRONMENT: str = Field(default="development")

    GEMINI_API_KEY: str | None = None
    # Stable model id for the google-genai SDK. Google deprecates older IDs regularly;
    # use a current name from https://ai.google.dev/gemini-api/docs/models/gemini
    # (e.g. gemini-3.5-flash). Older models (gemini-2.5-flash, gemini-2.0-flash) 404 for new API keys.
    GEMINI_MODEL: str = "gemini-3.5-flash"
    REALTIME_GEMINI_MODEL: str | None = None
    GEMINI_TEMPERATURE: float = 0.25
    # Lower = faster generation; 512 is enough for 3–5 short sentences in grounded mode.
    GEMINI_MAX_OUTPUT_TOKENS: int = 512

    # RAG answer LLM: gemini (default) or openai
    LLM_PROVIDER: str = "gemini"
    # Optional live-call override. Empty/None falls back to LLM_PROVIDER.
    REALTIME_LLM_PROVIDER: str | None = None
    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL: str = "gpt-4o-mini"
    REALTIME_OPENAI_MODEL: str | None = None
    OPENAI_TEMPERATURE: float = 0.25
    OPENAI_MAX_OUTPUT_TOKENS: int = 512

    DEEPGRAM_API_KEY: str | None = None
    # Speech-to-text: use nova-3 + language=multi for multilingual (code-switching). Override to nova-2 + en for English-only.
    DEEPGRAM_MODEL: str = "nova-3"
    DEEPGRAM_LANGUAGE: str = "multi"
    # Lower endpointing reduces end-of-turn latency, but values that are too low can split a thought mid-sentence.
    REALTIME_DEEPGRAM_ENDPOINTING_MS: int = 200

    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_COLLECTION: str = "real_estate"

    REDIS_URL: str | None = None
    SESSION_TTL_SECONDS: int = 86400

    # Durable call archive + post-call analysis (PostgreSQL or SQLite)
    DATABASE_ENABLED: bool = True
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/calls.db"
    # Live-call audio recording (WAV, stereo int16 @ 16k).
    # Stored on disk (persistent Docker volume) and referenced from the DB.
    CALL_RECORDINGS_DIR: str = "data/uploads/recordings"
    ANALYSIS_LLM_PROVIDER: str | None = None
    ANALYSIS_GEMINI_MODEL: str = "gemini-3.5-flash"
    ANALYSIS_OPENAI_MODEL: str = "gpt-4o-mini"
    ANALYSIS_MAX_OUTPUT_TOKENS: int = 8192
    # Safety ceiling only — ~50k tokens, far above any real call. Full transcripts
    # go to the analysis LLM; a warning is logged if this is ever hit.
    ANALYSIS_TRANSCRIPT_MAX_CHARS: int = 200_000
    # Language of the post-call report's free text: "en" (default, for dashboards
    # and managers) or "auto" (match the call — Hinglish for mixed Hindi calls).
    # Evidence quotes are always verbatim from the transcript, never translated.
    ANALYSIS_REPORT_LANGUAGE: str = "en"

    # RAG answer cache (Redis when REDIS_URL is set; else in-process LRU with TTL)
    ANSWER_CACHE_ENABLED: bool = True
    # Bump when the KB is reindexed OR answer prompts change shape, so stale entries are ignored
    ANSWER_CACHE_VERSION: str = "14"
    # Short TTL keeps answers fresh when KB changes; tune per domain (FAQ: 600–3600)
    ANSWER_CACHE_TTL_SECONDS: int = 300
    # Paraphrase hits: same-process embedding ring compared to recent cached queries
    ANSWER_CACHE_SEMANTIC_ENABLED: bool = True
    # BHK-scope guard in answer_cache allows 0.88 without 2↔3 bleed; more hits = lower latency.
    ANSWER_CACHE_SEMANTIC_THRESHOLD: float = 0.88
    ANSWER_CACHE_SEMANTIC_MAX_ENTRIES: int = 256
    # Do not cache ungrounded answers (empty retrieval) — avoids stale “no info” after KB updates
    ANSWER_CACHE_SKIP_EMPTY_SOURCES: bool = True
    ANSWER_CACHE_REDIS_PREFIX: str = "aicall:ragcache"
    # In-memory fallback cap when Redis is unavailable
    ANSWER_CACHE_MAX_MEMORY_ENTRIES: int = 512

    # Multilingual model: Hindi/Marathi/code-switched queries embed directly against
    # the English KB (shared vector space) — no translation call in the hot path.
    # Changing this model requires reindexing Qdrant (python -m app.scripts.seed_demo_data).
    EMBEDDING_MODEL: str = "paraphrase-multilingual-MiniLM-L12-v2"
    # Vector width of EMBEDDING_MODEL — must change together with it (and reindex).
    EMBEDDING_DIM: int = 384
    # LRU cache for embedding vectors — saves 20–80 ms per repeated phrase in a session
    EMBEDDING_CACHE_SIZE: int = 512

    # Smaller recall = faster Qdrant + rerank; tune up if you see missed hits.
    RECALL_K: int = 16
    TOP_K: int = 5
    # Realtime path can use a slightly smaller search budget for better time-to-first-answer.
    REALTIME_RECALL_K: int = 12
    REALTIME_TOP_K: int = 4

    # Multilingual cross-encoder — scores Hindi/Marathi queries against English passages.
    RERANKER_MODEL: str = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
    USE_RERANKER: bool = True
    HYBRID_KEYWORD_WEIGHT: float = 0.15
    # Skip expensive reranking when the query is very short (likely filler / acknowledgement)
    RERANKER_MIN_WORDS: int = 4
    # Realtime turns are often short; use a slightly higher threshold so low-signal turns skip reranking more often.
    REALTIME_RERANKER_MIN_WORDS: int = 6

    # Load embedding + reranker at startup so the first call is not slow.
    RAG_WARMUP_ON_STARTUP: bool = True
    # One lightweight LLM call at boot so the first user-facing answer skips cold HTTP/model latency.
    RAG_WARMUP_LLM: bool = True

    # Comma-separated origins; empty = CORS disabled (same-origin only)
    CORS_ORIGINS: str = ""

    # If set, require this value in X-API-Key (REST) or x-api-key / ?api_key= (WebSocket)
    INTERNAL_API_KEY: str | None = None

    JWT_SECRET: str = "dev-change-me-in-production"
    JWT_EXPIRE_MINUTES: int = 60 * 24 * 7

    # Abuse protection (in-process sliding windows; per-IP for auth, per-user for /ask)
    RATE_LIMIT_AUTH_PER_MINUTE: int = 10
    RATE_LIMIT_ASK_PER_MINUTE: int = 30
    # A rep needs 1 live session; 2 allows a stuck tab + a fresh one.
    MAX_CONCURRENT_SESSIONS_PER_USER: int = 2
    # How long the WebSocket waits for the client's auth message before closing.
    WS_AUTH_TIMEOUT_SECONDS: float = 5.0

    # LLM / external call safety
    LLM_REQUEST_TIMEOUT_SECONDS: float = 60.0
    # Max wait between streamed events on a live turn; exceeded = skip (not error) so the
    # rep is never staring at a stalled generation while the call moves on.
    RAG_TIMEOUT_SECONDS: float = 10.0

    # Realtime transcript filtering
    # Discard final segments shorter than this — filler words, acknowledgements, pauses
    TRANSCRIPT_MIN_WORDS: int = 3
    # Max history items stored per session (prevents unbounded Redis payloads)
    MAX_HISTORY_PER_SESSION: int = 100
    # How many recent turns to fold into the retrieval query
    CONTEXT_QUERY_WINDOW: int = 3

    # Skip full RAG+LLM when the new question is almost the same as the last (fast path)
    QUERY_DEDUP_ENABLED: bool = True
    QUERY_DEDUP_JACCARD_THRESHOLD: float = 0.72

    # Citations returned to clients (REST + WebSocket when enabled)
    SOURCE_EXCERPT_MAX_CHARS: int = 160
    EXPOSE_SOURCE_METADATA_TO_CLIENT: bool = True
    INCLUDE_SOURCES_IN_WS: bool = True

    # OpenTelemetry (optional): pip install opentelemetry-api opentelemetry-sdk
    OTEL_ENABLED: bool = False
    OTEL_SERVICE_NAME: str = "ai-calling-assistant"
    OTEL_EXPORTER_OTLP_ENDPOINT: str | None = None

    @field_validator("GEMINI_TEMPERATURE", "OPENAI_TEMPERATURE")
    @classmethod
    def temperature_in_range(cls, v: float) -> float:
        if not 0.0 <= v <= 2.0:
            raise ValueError("LLM temperature must be between 0 and 2")
        return v

    @field_validator("HYBRID_KEYWORD_WEIGHT")
    @classmethod
    def hybrid_in_range(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("HYBRID_KEYWORD_WEIGHT must be between 0 and 1")
        return v

    @field_validator("ANSWER_CACHE_SEMANTIC_THRESHOLD")
    @classmethod
    def semantic_threshold_in_range(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("ANSWER_CACHE_SEMANTIC_THRESHOLD must be between 0 and 1")
        return v

    @field_validator("QUERY_DEDUP_JACCARD_THRESHOLD")
    @classmethod
    def dedup_jaccard_in_range(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("QUERY_DEDUP_JACCARD_THRESHOLD must be between 0 and 1")
        return v

    @field_validator(
        "USE_RERANKER",
        "OTEL_ENABLED",
        "QUERY_DEDUP_ENABLED",
        "ANSWER_CACHE_ENABLED",
        "ANSWER_CACHE_SEMANTIC_ENABLED",
        "ANSWER_CACHE_SKIP_EMPTY_SOURCES",
        "RAG_WARMUP_ON_STARTUP",
        "RAG_WARMUP_LLM",
        "DATABASE_ENABLED",
        mode="before",
    )
    @classmethod
    def parse_bool_flags(cls, v):
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.lower() in ("1", "true", "yes", "on")
        return bool(v)


settings = Settings()


def validate_production_settings() -> None:
    """Refuse to start production with missing secrets or unsafe auth config."""
    if settings.ENVIRONMENT != "production":
        return
    problems = []
    if settings.LLM_PROVIDER.lower().strip() == "openai":
        if not settings.OPENAI_API_KEY:
            problems.append("OPENAI_API_KEY is missing")
    else:
        if not settings.GEMINI_API_KEY:
            problems.append("GEMINI_API_KEY is missing")
    if not settings.DEEPGRAM_API_KEY:
        problems.append("DEEPGRAM_API_KEY is missing")
    # A guessable or short JWT secret makes every session token forgeable.
    if settings.JWT_SECRET == "dev-change-me-in-production":
        problems.append("JWT_SECRET is still the dev default")
    elif len(settings.JWT_SECRET.encode()) < 32:
        problems.append("JWT_SECRET must be at least 32 bytes for HS256")
    # Empty CORS_ORIGINS = same-origin only (safe); a wildcard is never safe with credentials.
    if "*" in settings.CORS_ORIGINS:
        problems.append("CORS_ORIGINS must list explicit origins, not '*'")
    if problems:
        raise RuntimeError("Unsafe production configuration: " + "; ".join(problems))
