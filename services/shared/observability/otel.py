from opentelemetry import trace, baggage, _logs as logs
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.trace import NoOpTracerProvider
from fastapi import FastAPI
import os
import structlog

logger = structlog.get_logger("observability")


def _otel_enabled() -> bool:
    """Determine whether OTEL should be active.

    OTEL is strictly opt-in: only enabled when ENABLE_OTEL is explicitly
    set to "true".  Defaults to **disabled** so local dev environments
    don't produce noisy gRPC connection errors to otel-collector.
    """
    return os.getenv("ENABLE_OTEL", "false").lower() == "true"


def get_shared_resource(service_name: str):
    """Standardized resource with K8s Downward API metadata."""
    attributes = {
        "service.name": service_name,
        "service.version": os.getenv("SERVICE_VERSION", "1.0.0"),
        "deployment.environment": os.getenv("ENV", "dev"),
        "service.instance.id": os.getenv("HOSTNAME", "unknown"),
        "k8s.pod.name": os.getenv("K8S_POD_NAME"),
        "k8s.namespace.name": os.getenv("K8S_NAMESPACE"),
        "k8s.container.name": os.getenv("K8S_CONTAINER_NAME"),
    }
    # Filter out None values to prevent OTel crashes
    valid_attributes = {k: v for k, v in attributes.items() if v is not None}
    return Resource.create(valid_attributes)

def add_observability(app: FastAPI, service_name: str):
    """Unified entry point for FastAPI OTel (Tracing + Baggage + Logs)."""
    if not _otel_enabled():
        trace.set_tracer_provider(NoOpTracerProvider())
        logger.info("otel_disabled", service=service_name)
        return

    try:
        resource = get_shared_resource(service_name)
        endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")

        # 1. Tracing
        sampling_rate = float(os.getenv("OTEL_TRACE_SAMPLING_RATE", "0.1"))
        trace_provider = TracerProvider(sampler=TraceIdRatioBased(sampling_rate), resource=resource)
        trace.set_tracer_provider(trace_provider)
        trace_exporter = OTLPSpanExporter(endpoint=endpoint)
        trace_provider.add_span_processor(BatchSpanProcessor(trace_exporter))

        # 2. Logging (OTLP)
        try:
            log_provider = LoggerProvider(resource=resource)
            logs.set_logger_provider(log_provider)
            log_exporter = OTLPLogExporter(endpoint=endpoint)
            log_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))
        except Exception as e:
            logger.warning("otel_log_setup_failed", service=service_name, error=str(e))

        FastAPIInstrumentor.instrument_app(app)
        SQLAlchemyInstrumentor().instrument()
        HTTPXClientInstrumentor().instrument()
    except Exception as e:
        logger.error("otel_setup_failed", service=service_name, error=str(e))

def setup_standalone_observability(service_name: str):
    """Setup OTel for workers and consumers (no FastAPI app)."""
    if not _otel_enabled():
        trace.set_tracer_provider(NoOpTracerProvider())
        logger.info("otel_disabled", service=service_name)
        return trace.get_tracer(service_name)

    try:
        resource = get_shared_resource(service_name)
        endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")

        # 1. Tracing
        sampling_rate = float(os.getenv("OTEL_TRACE_SAMPLING_RATE", "0.1"))
        trace_provider = TracerProvider(sampler=TraceIdRatioBased(sampling_rate), resource=resource)
        trace.set_tracer_provider(trace_provider)
        trace_exporter = OTLPSpanExporter(endpoint=endpoint)
        trace_provider.add_span_processor(BatchSpanProcessor(trace_exporter))

        # 2. Logging (OTLP)
        try:
            log_provider = LoggerProvider(resource=resource)
            logs.set_logger_provider(log_provider)
            log_exporter = OTLPLogExporter(endpoint=endpoint)
            log_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))
        except Exception as e:
            logger.warning("otel_log_setup_failed", service=service_name, error=str(e))

        SQLAlchemyInstrumentor().instrument()
        HTTPXClientInstrumentor().instrument()
    except Exception as e:
        logger.error("otel_standalone_setup_failed", service=service_name, error=str(e))

    return trace.get_tracer(service_name)
