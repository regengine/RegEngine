"""Fail-closed webhook outbox requirement (audit medium finding).

Failed recall webhook deliveries with no outbox file are acknowledged and
lost on restart: the dead letter lives only in process memory. The notifier
must therefore refuse to start with webhooks-but-no-outbox in production,
while dev and test keep the legacy in-memory behavior.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("LOG_LEVEL", "WARNING")

_SERVICES_DIR = Path(__file__).resolve().parent.parent.parent
if str(_SERVICES_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICES_DIR))

from shared.paths import ensure_shared_importable  # noqa: E402

ensure_shared_importable()

import app.notifications as notifications_mod  # noqa: E402
import pytest  # noqa: E402
from app.config import get_settings  # noqa: E402

WebhookNotifier = notifications_mod.WebhookNotifier

_TEST_DB_URL = "postgresql://test:test@localhost:5432/test"
_TEST_API_KEY = "test-scheduler-key"


@pytest.fixture
def _prod_env(monkeypatch):
    """Point settings at production with valid secrets, restoring after."""
    monkeypatch.setenv("REGENGINE_ENV", "production")
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.setenv("DATABASE_URL", _TEST_DB_URL)
    monkeypatch.setenv("SCHEDULER_API_KEY", _TEST_API_KEY)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def _dev_env(monkeypatch):
    monkeypatch.setenv("REGENGINE_ENV", "development")
    monkeypatch.delenv("ENV", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class TestDurableOutboxRequired:
    def test_raises_in_production_without_outbox(self, _prod_env):
        with pytest.raises(ValueError, match="outbox"):
            WebhookNotifier(urls=["https://hook.example.com/alerts"])

    def test_no_raise_in_production_with_outbox(self, _prod_env, tmp_path):
        notifier = WebhookNotifier(
            urls=["https://hook.example.com/alerts"],
            outbox_path=str(tmp_path / "outbox.jsonl"),
        )
        try:
            assert notifier.outbox_durable is True
        finally:
            notifier.close()

    def test_no_raise_in_production_without_urls(self, _prod_env):
        notifier = WebhookNotifier(urls=[])
        try:
            assert notifier.outbox_durable is False
        finally:
            notifier.close()

    def test_no_raise_outside_production_without_outbox(self, _dev_env):
        notifier = WebhookNotifier(urls=["https://hook.example.com/alerts"])
        try:
            assert notifier.outbox_durable is False
            assert notifier.unpersisted_dead_letter_count() == 0
        finally:
            notifier.close()
