"""
OpenAI LLM service — mirrors ``GeminiService``:

- ``stream_live``  — realtime path: one intent-tagged stream per customer turn.
- ``generate_answer`` — REST /ask path: plain grounded Q&A, non-streamed.
"""

import concurrent.futures
from collections.abc import Iterator
from typing import Any

from openai import OpenAI

from app.core.config import settings
from app.core.logging import get_logger
from app.core.telemetry import get_tracer
from app.rag.gemini_service import format_numbered_context
from app.rag.models import RetrievedChunk
from app.rag.prompts import (
    build_grounded_answer_prompt,
    build_live_suggestion_prompt,
    build_no_context_prompt,
    empty_retrieval_message,
)

logger = get_logger(__name__)

_GENERIC_FAILURE = "I could not generate an answer right now. Please try again in a moment."


class OpenAIService:

    def __init__(self, *, model_name: str | None = None):
        self._model_name = model_name or settings.OPENAI_MODEL
        self._client: OpenAI | None = None
        if settings.OPENAI_API_KEY:
            self._client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=2,
            thread_name_prefix="openai",
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
        if self._client is None:
            yield "INTENT: question\nConfiguration error: OPENAI_API_KEY is not set."
            return

        prompt = build_live_suggestion_prompt(
            question,
            format_numbered_context(chunks),
            conversation_context=conversation_context,
        )
        tracer = get_tracer()
        with tracer.start_as_current_span("llm.openai.stream_live") as span:
            span.set_attribute("model", self._model_name)
            span.set_attribute("context.chunks", len(chunks))
            stream = None
            try:
                stream = self._client.chat.completions.create(
                    model=self._model_name,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=settings.OPENAI_TEMPERATURE,
                    max_tokens=settings.OPENAI_MAX_OUTPUT_TOKENS,
                    stream=True,
                    timeout=settings.LLM_REQUEST_TIMEOUT_SECONDS,
                )
                for chunk in stream:
                    choice = chunk.choices[0] if chunk.choices else None
                    delta = getattr(choice, "delta", None) if choice else None
                    text = getattr(delta, "content", None) if delta else None
                    if text:
                        yield text
            except Exception as e:
                span.record_exception(e)
                logger.exception("OpenAI stream failed: %s", e)
                yield f"\n{_GENERIC_FAILURE}"
            finally:
                close_fn = getattr(stream, "close", None)
                if close_fn is not None:
                    try:
                        close_fn()
                    except Exception:
                        pass

    # ── REST path ────────────────────────────────────────────────────────────

    def generate_answer(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        *,
        conversation_context: dict[str, Any] | None = None,
    ) -> str:
        if self._client is None:
            return "Configuration error: OPENAI_API_KEY is not set."

        if chunks:
            prompt = build_grounded_answer_prompt(
                query,
                format_numbered_context(chunks),
                conversation_context=conversation_context,
            )
            max_tokens = settings.OPENAI_MAX_OUTPUT_TOKENS
        else:
            prompt = build_no_context_prompt(query, conversation_context=conversation_context)
            max_tokens = min(384, settings.OPENAI_MAX_OUTPUT_TOKENS)

        tracer = get_tracer()
        with tracer.start_as_current_span("llm.openai.generate") as span:
            span.set_attribute("model", self._model_name)
            span.set_attribute("context.chunks", len(chunks))
            try:
                future = self._executor.submit(self._generate_sync, prompt, max_tokens)
                text = future.result(timeout=settings.LLM_REQUEST_TIMEOUT_SECONDS)
            except concurrent.futures.TimeoutError:
                logger.warning(
                    "OpenAI generate timed out after %.1fs",
                    settings.LLM_REQUEST_TIMEOUT_SECONDS,
                )
                return "Response generation timed out. Please try again in a moment."
            except Exception as e:
                span.record_exception(e)
                logger.exception("OpenAI generate failed: %s", e)
                return _GENERIC_FAILURE

            out = (text or "").strip()
            if out:
                return out
            return empty_retrieval_message() if not chunks else _GENERIC_FAILURE

    def _generate_sync(self, prompt: str, max_tokens: int) -> str:
        assert self._client is not None
        response = self._client.chat.completions.create(
            model=self._model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=settings.OPENAI_TEMPERATURE,
            max_tokens=max_tokens,
        )
        choice = response.choices[0] if response.choices else None
        if not choice or not choice.message:
            return ""
        if getattr(choice, "finish_reason", None) == "length":
            logger.warning(
                "OpenAI hit max_tokens — answer may be truncated; "
                "consider raising OPENAI_MAX_OUTPUT_TOKENS"
            )
        return choice.message.content or ""
