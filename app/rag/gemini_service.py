"""
Gemini LLM service on the ``google-genai`` SDK.

Two jobs:
- ``stream_live``  — realtime path: one intent-tagged stream per customer turn
  (the pipeline strips the INTENT line before it reaches the rep).
- ``generate_answer`` — REST /ask path: plain grounded Q&A, non-streamed.
"""

import concurrent.futures
from collections.abc import Iterator
from functools import lru_cache
from typing import Any

from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from app.core.config import settings
from app.core.logging import get_logger
from app.core.telemetry import get_tracer
from app.rag.models import RetrievedChunk
from app.rag.prompts import (
    build_grounded_answer_prompt,
    build_live_suggestion_prompt,
    build_no_context_prompt,
    empty_retrieval_message,
)

logger = get_logger(__name__)

_GENERIC_FAILURE = "I could not generate an answer right now. Please try again in a moment."


@lru_cache(maxsize=1)
def get_gemini_client() -> genai.Client | None:
    """One SDK client per process (also used by post-call analysis)."""
    if not settings.GEMINI_API_KEY:
        return None
    return genai.Client(api_key=settings.GEMINI_API_KEY)


def format_numbered_context(chunks: list[RetrievedChunk]) -> str:
    """Number KB passages so prompts can anchor on specific ones."""
    lines = []
    for i, c in enumerate(chunks, start=1):
        label = f"[{i}]"
        if c.chunk_id is not None:
            label += f" (id={c.chunk_id})"
        lines.append(f"{label} {c.text.strip()}")
    return "\n".join(lines)


class GeminiService:

    def __init__(self, *, model_name: str | None = None):
        self._model_name = model_name or settings.GEMINI_MODEL
        self._config = genai_types.GenerateContentConfig(
            temperature=settings.GEMINI_TEMPERATURE,
            max_output_tokens=settings.GEMINI_MAX_OUTPUT_TOKENS,
        )
        # One pool per service — bounds concurrent Gemini calls and lets the
        # non-streamed REST path enforce a timeout.
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=2,
            thread_name_prefix="gemini",
        )

    # ── Realtime path ────────────────────────────────────────────────────────

    def stream_live(
        self,
        question: str,
        chunks: list[RetrievedChunk],
        *,
        conversation_context: dict[str, Any] | None = None,
    ) -> Iterator[str]:
        """
        Stream the raw intent-tagged response for one live turn. The first line
        is ``INTENT: <tag>``; everything after is the rep's spoken lines.
        """
        client = get_gemini_client()
        if client is None:
            yield "INTENT: question\nConfiguration error: GEMINI_API_KEY is not set."
            return

        prompt = build_live_suggestion_prompt(
            question,
            format_numbered_context(chunks),
            conversation_context=conversation_context,
        )
        tracer = get_tracer()
        with tracer.start_as_current_span("llm.gemini.stream_live") as span:
            span.set_attribute("model", self._model_name)
            span.set_attribute("context.chunks", len(chunks))
            try:
                stream = client.models.generate_content_stream(
                    model=self._model_name,
                    contents=prompt,
                    config=self._config,
                )
                for chunk in stream:
                    if chunk.text:
                        yield chunk.text
            except genai_errors.APIError as e:
                span.record_exception(e)
                logger.error(
                    "Gemini stream failed (HTTP %s, model=%r): %s",
                    e.code,
                    self._model_name,
                    e.message,
                )
                yield f"\n{_GENERIC_FAILURE}"
            except Exception as e:
                span.record_exception(e)
                logger.exception("Gemini stream failed: %s", e)
                yield f"\n{_GENERIC_FAILURE}"

    # ── REST path ────────────────────────────────────────────────────────────

    def generate_answer(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        *,
        conversation_context: dict[str, Any] | None = None,
    ) -> str:
        if get_gemini_client() is None:
            return "Configuration error: GEMINI_API_KEY is not set."

        if chunks:
            prompt = build_grounded_answer_prompt(
                query,
                format_numbered_context(chunks),
                conversation_context=conversation_context,
            )
            config = self._config
        else:
            prompt = build_no_context_prompt(query, conversation_context=conversation_context)
            config = genai_types.GenerateContentConfig(
                temperature=settings.GEMINI_TEMPERATURE,
                max_output_tokens=min(384, settings.GEMINI_MAX_OUTPUT_TOKENS),
            )

        tracer = get_tracer()
        with tracer.start_as_current_span("llm.gemini.generate") as span:
            span.set_attribute("model", self._model_name)
            span.set_attribute("context.chunks", len(chunks))
            try:
                future = self._executor.submit(self._generate_sync, prompt, config)
                text = future.result(timeout=settings.LLM_REQUEST_TIMEOUT_SECONDS)
            except concurrent.futures.TimeoutError:
                logger.warning(
                    "Gemini generate timed out after %.1fs",
                    settings.LLM_REQUEST_TIMEOUT_SECONDS,
                )
                return "Response generation timed out. Please try again in a moment."
            except genai_errors.APIError as e:
                span.record_exception(e)
                logger.error(
                    "Gemini generate failed (HTTP %s, model=%r): %s",
                    e.code,
                    self._model_name,
                    e.message,
                )
                return _GENERIC_FAILURE
            except Exception as e:
                span.record_exception(e)
                logger.exception("Gemini generate failed: %s", e)
                return _GENERIC_FAILURE

            out = (text or "").strip()
            if out:
                return out
            return empty_retrieval_message() if not chunks else _GENERIC_FAILURE

    def _generate_sync(self, prompt: str, config: genai_types.GenerateContentConfig) -> str:
        client = get_gemini_client()
        assert client is not None
        response = client.models.generate_content(
            model=self._model_name,
            contents=prompt,
            config=config,
        )
        return response.text or ""
