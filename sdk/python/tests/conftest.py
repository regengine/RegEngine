"""Test configuration and fixtures."""

import pytest


@pytest.fixture
def mock_api_key():
    """Provide a test API key."""
    return "rge_test_12345"


@pytest.fixture
def sample_asset():
    """Provide a sample asset dictionary."""
    return {
        "id": "T1",
        "type": "TRANSFORMER",
        "firmware_version": "2.4.1",
        "last_verified": "2026-01-26T15:00:00Z"
    }


@pytest.fixture
def sample_esp_config():
    """Provide a sample ESP configuration."""
    return {
        "firewall_version": "2.4.1",
        "ids_enabled": True,
        "patch_level": "current"
    }
