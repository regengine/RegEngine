"""Tests for the webhook outbox drainer secret lookup.

The lookup backs ``drain_webhook_outbox.main`` and must not open one
database session per row. Results are cached per tenant for the life
of one lookup (one drain batch).
"""

from __future__ import annotations

from app.metrics import (
    _TENANT_SETTINGS_WEBHOOK_SECRET_KEY,
    _TENANT_SETTINGS_WEBHOOK_URL_KEY,
)

from services.admin.scripts.drain_webhook_outbox import _build_secret_lookup


class _FakeTenant:
    def __init__(self, settings):
        self.settings = settings


class _FakeSession:
    def __init__(self, tenants):
        self._tenants = tenants

    def get(self, model, tenant_id):
        settings = self._tenants.get(tenant_id)
        if settings is None:
            return None
        return _FakeTenant(settings)

    def close(self):
        pass


def test_secret_lookup_opens_one_session_per_tenant(monkeypatch):
    tenants = {
        "tenant-a": {
            _TENANT_SETTINGS_WEBHOOK_URL_KEY: "https://a.example.test/hook",
            _TENANT_SETTINGS_WEBHOOK_SECRET_KEY: "secret_a",
        },
        "tenant-b": {
            _TENANT_SETTINGS_WEBHOOK_URL_KEY: "https://b.example.test/hook",
            _TENANT_SETTINGS_WEBHOOK_SECRET_KEY: "secret_b",
        },
    }
    opens = []

    def fake_session_factory():
        opens.append(1)
        return _FakeSession(tenants)

    import app.database

    monkeypatch.setattr(app.database, "SessionLocal", fake_session_factory)

    lookup = _build_secret_lookup()
    assert lookup("tenant-a") == ("https://a.example.test/hook", "secret_a")
    # Same tenant again must come from the cache, not a new session.
    assert lookup("tenant-a") == ("https://a.example.test/hook", "secret_a")
    assert lookup("tenant-a") == ("https://a.example.test/hook", "secret_a")
    assert lookup("tenant-b") == ("https://b.example.test/hook", "secret_b")

    # Four lookups across two tenants open two sessions. A lookup that
    # opens a session per call would open four.
    assert len(opens) == 2


def test_secret_lookup_returns_none_for_unknown_tenant(monkeypatch):
    opens = []

    def fake_session_factory():
        opens.append(1)
        return _FakeSession({})

    import app.database

    monkeypatch.setattr(app.database, "SessionLocal", fake_session_factory)

    lookup = _build_secret_lookup()
    assert lookup("missing-tenant") == (None, None)
    assert lookup("missing-tenant") == (None, None)
    assert len(opens) == 1
