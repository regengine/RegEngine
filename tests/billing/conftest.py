"""Shared fixtures for billing tests."""
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_stripe():
    """Mock the stripe module."""
    with patch("services.ingestion.app.stripe_billing.stripe") as mock:
        yield mock


@pytest.fixture
def mock_settings():
    """Mock billing settings."""
    settings = MagicMock()
    settings.stripe_secret_key = "sk_test_fake"
    settings.stripe_webhook_secret = "whsec_test_fake"
    return settings
