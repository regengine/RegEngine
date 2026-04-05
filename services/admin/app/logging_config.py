"""Structured logging configuration for the admin service.

Thin wrapper around the shared logging config (#556). Kept for backward
compatibility so existing `from app.logging_config import configure_logging`
imports continue to work without changes.

Usage:
    from app.logging_config import configure_logging

    configure_logging(level="INFO")
"""

from shared.logging_config import configure_logging as _shared_configure_logging


def configure_logging(level: str = "INFO") -> None:
    """Configure structured JSON logging for the admin service.

    Delegates to shared.logging_config.configure_logging so all services
    emit identical JSON records (#556).

    Args:
        level: Log level string (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    """
    _shared_configure_logging(service_name="admin-service", log_level=level)
