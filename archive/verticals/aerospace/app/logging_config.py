"""
Structured logging configuration for Aerospace service.

Configures structlog with:
- JSON output for production (machine-readable)
- Console-friendly output for development
- ISO timestamp format
- Log level filtering
- Context variable merging for request tracking
"""

import logging
import os
import structlog


def configure_logging(log_level: str = "INFO") -> None:
    """
    Configure structlog for the aerospace service.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    # Determine environment
    environment = os.getenv("REGENGINE_ENV", "development")
    
    # Configure processors based on environment
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
    ]
    
    # Use JSON renderer for production, console renderer for development
    if environment == "production":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())
    
    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper(), logging.INFO)
        ),
        cache_logger_on_first_use=True,
        logger_factory=structlog.stdlib.LoggerFactory(),
    )
    
    # Also configure standard logging
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(message)s",
    )
