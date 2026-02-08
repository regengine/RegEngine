"""Shared observability module for RegEngine.

Provides conditional OpenTelemetry initialization. If the OTel SDK is not
installed, all functions degrade to no-ops so services can boot without
the tracing dependency.
"""

import os
from typing import Any, Optional

import structlog

logger = structlog.get_logger("observability")

# Conditional OTel import — services work fine without it
_OTEL_AVAILABLE = False
try:
    from opentelemetry import trace
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    _OTEL_AVAILABLE = True
except ImportError:
    trace = None  # type: ignore[assignment]
    logger.info("opentelemetry_not_installed", hint="pip install opentelemetry-sdk to enable tracing")


def setup_telemetry(service_name: str, app: Optional[Any] = None) -> None:
    """
    Setup OpenTelemetry for a microservice.

    If the OTel SDK is not installed, this function logs a warning and returns
    immediately. Services continue to operate without tracing.

    Args:
        service_name: Name of the service for tracing
        app: Optional FastAPI app for auto-instrumentation
    """
    if not _OTEL_AVAILABLE:
        logger.warning(
            "telemetry_skipped",
            service_name=service_name,
            reason="opentelemetry not installed",
        )
        return

    # Check if telemetry is explicitly disabled
    if os.getenv("OTEL_ENABLED", "true").lower() in ("false", "0", "no"):
        logger.info("telemetry_disabled_by_env", service_name=service_name)
        return

    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")

    # Configure resource
    resource = Resource(attributes={
        SERVICE_NAME: service_name
    })

    # Set up tracer provider
    provider = TracerProvider(resource=resource)

    # Configure OTLP exporter
    try:
        exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
        processor = BatchSpanProcessor(exporter)
        provider.add_span_processor(processor)

        # Set global tracer provider
        trace.set_tracer_provider(provider)

        logger.info("telemetry_initialized", service_name=service_name, endpoint=otlp_endpoint)

        # Instrument FastAPI if provided
        if app:
            FastAPIInstrumentor.instrument_app(app)
            logger.info("fastapi_instrumented", service_name=service_name)

    except Exception as e:
        logger.warning("telemetry_initialization_failed", error=str(e))


def get_tracer(name: str) -> Any:
    """Get a tracer instance for the given name.

    Returns a no-op tracer if OpenTelemetry is not available.
    """
    if not _OTEL_AVAILABLE or trace is None:
        # Return a minimal no-op object
        class _NoOpTracer:
            def start_span(self, *args: Any, **kwargs: Any) -> "_NoOpSpan":
                return _NoOpSpan()

        class _NoOpSpan:
            def __enter__(self) -> "_NoOpSpan":
                return self

            def __exit__(self, *args: Any) -> None:
                pass

            def set_attribute(self, *args: Any) -> None:
                pass

        return _NoOpTracer()

    return trace.get_tracer(name)
