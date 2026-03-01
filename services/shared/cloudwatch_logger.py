"""Structured logging helpers for service processes.

This module keeps backward-compatible function names while routing logs to
standard output for platform-level aggregation.
"""

from __future__ import annotations

import logging
import os


def configure_cloudwatch_logging(
    service_name: str,
    log_level: str = "INFO",
    environment: str = "production",
    region: str = "us-east-1",
) -> logging.Logger:
    """Configure a structured stdout logger for a service.

    Args:
        service_name: Name of the service (for logger namespace)
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        environment: Deployment environment label
        region: Retained for backward compatibility

    Returns:
        Configured logger instance
    """
    del region

    logger = logging.getLogger(service_name)
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        '{"timestamp":"%(asctime)s","level":"%(levelname)s","service":"%(name)s","message":"%(message)s"}'
    )

    handler = logging.StreamHandler()
    handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    logger.info("structured_logging_configured environment=%s", environment)
    return logger


def get_cloudwatch_config_for_ecs(service_name: str, environment: str = "production") -> dict:
    """Return a neutral container log configuration.

    The function name is retained for compatibility with existing imports.
    """
    return {
        "logDriver": "json-file",
        "options": {
            "tag": f"{service_name}-{environment}",
            "max-size": os.getenv("LOG_MAX_SIZE", "10m"),
            "max-file": os.getenv("LOG_MAX_FILE", "3"),
        },
    }


if __name__ == "__main__":
    configured_logger = configure_cloudwatch_logging(
        service_name="example-service",
        log_level="INFO",
        environment=os.getenv("ENVIRONMENT", "development"),
    )

    configured_logger.info("logging configured successfully")
    configured_logger.warning("this is a warning message")
    configured_logger.error("this is an error message")
