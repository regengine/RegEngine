import structlog
import logging
import sys
import os
from opentelemetry import trace

# Configure base structlog processors
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger("regengine")

# Safely import OTel logging components
try:
    from opentelemetry.sdk._logs import LoggingHandler
    from opentelemetry import _logs as logs
    OTEL_LOGGING_AVAILABLE = True
except ImportError:
    OTEL_LOGGING_AVAILABLE = False

def setup_logging():
    """Setup basic logging configuration and return the global logger."""
    level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
    
    # 1. Stdout listener
    handlers = [logging.StreamHandler(sys.stdout)]
    
    # 2. OTel Bridge (If available)
    if OTEL_LOGGING_AVAILABLE:
        handlers.append(LoggingHandler(logger_provider=logs.get_logger_provider()))
        
    logging.basicConfig(
        format="%(message)s", 
        level=level, 
        handlers=handlers
    )
    return logger

# OTel context + sampling flag injection
def otel_context_processor(logger, method_name, event_dict):
    current_span = trace.get_current_span()
    if current_span is not None and current_span.get_span_context().is_valid:
        ctx = current_span.get_span_context()
        event_dict["trace_id"] = format(ctx.trace_id, "032x")
        event_dict["span_id"] = format(ctx.span_id, "016x")
        event_dict["trace_sampled"] = bool(ctx.trace_flags.sampled)
    else:
        event_dict["trace_sampled"] = False
    return event_dict

# Sampling-aware filter (drops INFO/DEBUG for sampled-out traces when disabled)
def sampling_aware_filter(logger, method_name, event_dict):
    if os.getenv("LOG_ALL_SAMPLED_OUT", "true").lower() == "false":
        if event_dict.get("trace_sampled") is False and method_name not in ("error", "critical", "warning"):
            raise structlog.DropEvent
    return event_dict

# Inject finalized processors into the configuration
structlog.configure(
    processors=[otel_context_processor, sampling_aware_filter] + structlog.get_config()["processors"]
)
