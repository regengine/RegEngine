from opentelemetry import trace, baggage, _logs as logs
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from fastapi import FastAPI
import os

def get_shared_resource(service_name: str):
    """Standardized resource with K8s Downward API metadata."""
    return Resource.create({
        "service.name": service_name,
        "service.version": os.getenv("SERVICE_VERSION", "1.0.0"),
        "deployment.environment": os.getenv("ENV", "dev"),
        "service.instance.id": os.getenv("HOSTNAME", "unknown"),
        "k8s.pod.name": os.getenv("K8S_POD_NAME"),
        "k8s.namespace.name": os.getenv("K8S_NAMESPACE"),
        "k8s.container.name": os.getenv("K8S_CONTAINER_NAME"),
    })

def add_observability(app: FastAPI, service_name: str):
    """Unified entry point for FastAPI OTel (Tracing + Baggage + Logs)."""
    resource = get_shared_resource(service_name)
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")

    # 1. Tracing
    sampling_rate = float(os.getenv("OTEL_TRACE_SAMPLING_RATE", "0.1"))
    trace_provider = TracerProvider(sampler=TraceIdRatioBased(sampling_rate), resource=resource)
    trace.set_tracer_provider(trace_provider)
    trace_exporter = OTLPSpanExporter(endpoint=endpoint)
    trace_provider.add_span_processor(BatchSpanProcessor(trace_exporter))

    # 2. Logging (OTLP)
    log_provider = LoggerProvider(resource=resource)
    logs.set_logger_provider(log_provider)
    log_exporter = OTLPLogExporter(endpoint=endpoint)
    log_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))

    # Enable W3C Baggage propagation globally
    try:
        from opentelemetry import baggage
        baggage.set_baggage_propagator()
    except Exception:
        pass

    FastAPIInstrumentor.instrument_app(app)

def setup_standalone_observability(service_name: str):
    """Setup OTel for workers and consumers (no FastAPI app)."""
    resource = get_shared_resource(service_name)
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")

    # 1. Tracing
    sampling_rate = float(os.getenv("OTEL_TRACE_SAMPLING_RATE", "0.1"))
    trace_provider = TracerProvider(sampler=TraceIdRatioBased(sampling_rate), resource=resource)
    trace.set_tracer_provider(trace_provider)
    trace_exporter = OTLPSpanExporter(endpoint=endpoint)
    trace_provider.add_span_processor(BatchSpanProcessor(trace_exporter))

    # 2. Logging (OTLP)
    log_provider = LoggerProvider(resource=resource)
    logs.set_logger_provider(log_provider)
    log_exporter = OTLPLogExporter(endpoint=endpoint)
    log_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))
    
    return trace.get_tracer(service_name)
