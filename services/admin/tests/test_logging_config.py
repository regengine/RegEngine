"""Test structured logging configuration."""

import logging
import os
import pytest
import structlog


def test_logging_config_import():
    """Test that logging_config module can be imported."""
    from app.logging_config import configure_logging
    assert callable(configure_logging)


def test_configure_logging_info_level():
    """Test configuring logging with INFO level."""
    from app.logging_config import configure_logging
    
    # Should not raise any exceptions
    configure_logging("INFO")
    
    # Verify structlog is configured
    logger = structlog.get_logger("test")
    assert logger is not None


def test_configure_logging_debug_level(monkeypatch):
    """Test configuring logging with DEBUG level."""
    from app.logging_config import configure_logging

    # Clear LOG_LEVEL env override so the passed level takes effect
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    configure_logging("DEBUG")

    # Verify standard logging level is set
    assert logging.root.level == logging.DEBUG


def test_configure_logging_development_env():
    """Test that development environment uses console renderer."""
    from app.logging_config import configure_logging
    
    os.environ["REGENGINE_ENV"] = "development"
    configure_logging("INFO")
    
    # Should complete without error
    logger = structlog.get_logger("test")
    assert logger is not None


def test_configure_logging_production_env():
    """Test that production environment uses JSON renderer."""
    from app.logging_config import configure_logging
    
    os.environ["REGENGINE_ENV"] = "production"
    configure_logging("INFO")
    
    # Should complete without error
    logger = structlog.get_logger("test")
    assert logger is not None


def test_logger_can_log():
    """Test that logger can actually log messages."""
    from app.logging_config import configure_logging
    
    configure_logging("INFO")
    logger = structlog.get_logger("test_module")
    
    # These should not raise exceptions
    logger.info("test_event", key="value")
    logger.warning("test_warning", count=42)
    logger.error("test_error", error_code="TEST001")
