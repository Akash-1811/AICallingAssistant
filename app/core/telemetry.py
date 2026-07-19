"""
Optional OpenTelemetry tracing. Enable with OTEL_ENABLED=true.

Console export by default; set OTEL_EXPORTER_OTLP_ENDPOINT for OTLP HTTP
(requires: pip install opentelemetry-exporter-otlp).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class _NoOpSpan:
    def set_attribute(self, *args: Any, **kwargs: Any) -> None:
        pass

    def record_exception(self, *args: Any, **kwargs: Any) -> None:
        pass


class _NoOpTracer:
    @contextmanager
    def start_as_current_span(self, name: str, **kwargs: Any) -> Iterator[_NoOpSpan]:
        yield _NoOpSpan()


def setup_telemetry() -> None:
    if not settings.OTEL_ENABLED:
        return
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        logger.warning(
            "OTEL_ENABLED but opentelemetry not installed; "
            "pip install opentelemetry-api opentelemetry-sdk"
        )
        return

    resource = Resource.create(
        {
            "service.name": settings.OTEL_SERVICE_NAME,
            "deployment.environment": settings.ENVIRONMENT,
        }
    )
    provider = TracerProvider(resource=resource)
    endpoint = (settings.OTEL_EXPORTER_OTLP_ENDPOINT or "").strip()

    if endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )

            exporter = OTLPSpanExporter(endpoint=endpoint)
            provider.add_span_processor(BatchSpanProcessor(exporter))
            logger.info("OTLP trace export: %s", endpoint)
        except ImportError:
            logger.warning(
                "OTEL_EXPORTER_OTLP_ENDPOINT set; install opentelemetry-exporter-otlp"
            )
            return
    else:
        from opentelemetry.sdk.trace.export import ConsoleSpanExporter

        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        logger.info("OpenTelemetry console export (set OTEL_EXPORTER_OTLP_ENDPOINT for OTLP)")

    trace.set_tracer_provider(provider)
    logger.info("OpenTelemetry ready (service=%s)", settings.OTEL_SERVICE_NAME)


def get_tracer():
    if not settings.OTEL_ENABLED:
        return _NoOpTracer()
    try:
        from opentelemetry import trace

        return trace.get_tracer(settings.OTEL_SERVICE_NAME)
    except Exception:
        return _NoOpTracer()
