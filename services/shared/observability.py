"""Shared observability module for RegEngine."""

import os
from typing import Optional

from opentelemetry import trace
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
import structlog

logger = structlog.get_logger("observability")


def setup_telemetry(service_name: str, app: Optional[Any] = None) -> None:
    """
    Setup OpenTelemetry for a microservice.
    
    Args:
        service_name: Name of the service for tracing
        app: Optional FastAPI app for auto-instrumentation
    """
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


def get_tracer(name: str):
    """Get a tracer instance for the given name."""
    return trace.get_tracer(name)
