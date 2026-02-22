"""Structured logging configuration for the admin service.

Configures structlog with JSON output for production and console-friendly
output for development. This module should be imported and initialized early
in the application lifecycle.

Usage:
    from app.logging_config import configure_logging
    
    configure_logging(level="INFO")
"""

import logging
import os

import structlog


def configure_logging(level: str = "INFO") -> None:
    """Configure structlog with JSON output and appropriate log level.
    
    Args:
        level: Log level string (DEBUG, INFO, WARNING, ERROR, CRITICAL).
               Defaults to INFO.
    
    The configuration includes:
    - Context variable merging for correlation IDs
    - ISO timestamp formatting
    - Log level addition
    - JSON rendering for structured output
    - Filtering based on configured log level
    """
    # Determine if we should use console-friendly or JSON output
    # Use console for development, JSON for production
    env = os.getenv("REGENGINE_ENV", "development").lower()
    
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
    ]
    
    # Use console renderer for development, JSON for production
    if env == "development":
        processors.append(structlog.dev.ConsoleRenderer())
    else:
        processors.append(structlog.processors.JSONRenderer())
    
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        cache_logger_on_first_use=True,
    )
    
    # Configure standard library logging to match
    logging.root.setLevel(getattr(logging, level.upper(), logging.INFO))
