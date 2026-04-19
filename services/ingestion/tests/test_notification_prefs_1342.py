"""Coverage for app/notification_prefs.py — per-tenant alert preferences router.

Exercises the Pydantic models, default factory, DB helpers, and endpoint
paths (DB hit / DB miss / DB write failure fallback) via FastAPI TestClient
with dependency overrides for auth.

Issue: #1342
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import notification_prefs as np_mod
from app.notification_prefs import (
    AlertPreference,
    EscalationRule,
    NotificationChannel,
    NotificationPreferences,
    QuietHours,
    _db_get_preferences,
    _db_save_preferences,
    _default_preferences,
    _prefs_store,
    router,
)
from app.webhook_compat import _verify_api_key


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_store():
    _prefs_store.clear()
    yield
    _prefs_store.clear()


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[_verify_api_key] = lambda: None
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


class _FakeJsonbStore:
    """In-process stand-in for shared.tenant_settings JSONB helpers."""

    def __init__(self):
        self.data: dict[tuple[str, str, str], dict] = {}
        self.write_fail_for: set[str] = set()
        self.get_calls: list[tuple] = []
        self.set_calls: list[tuple] = []

    def get(self, tenant_id: str, table: str, column: str):
        self.get_calls.append((tenant_id, table, column))
        return self.data.get((tenant_id, table, column))

    def set(self, tenant_id: str, table: str, column: str, value: dict) -> bool:
        self.set_calls.append((tenant_id, table, column, value))
        if tenant_id in self.write_fail_for:
            return False
        self.data[(tenant_id, table, column)] = value
        return True


@pytest.fixture
def fake_jsonb(monkeypatch):
    store = _FakeJsonbStore()
    monkeypatch.setattr(np_mod, "get_jsonb", store.get)
    monkeypatch.setattr(np_mod, "set_jsonb", store.set)
    return store


# ---------------------------------------------------------------------------
# Pydantic model surface
# ---------------------------------------------------------------------------


class TestPydanticModels:
    def test_notification_channel_defaults(self):
        ch = NotificationChannel(channel="email")
        assert ch.channel == "email"
        assert ch.enabled is True
        assert ch.target == ""

    def test_alert_preference_defaults(self):
        ap = AlertPreference(rule_id="r1", rule_name="Rule One")
        assert ap.enabled is True
        assert ap.channels == ["email"]
        assert ap.min_severity == "warning"

    def test_alert_preference_channels_default_factory(self):
        # Default factory: two independent instances must not share the same list
        a = AlertPreference(rule_id="r1", rule_name="R1")
        b = AlertPreference(rule_id="r2", rule_name="R2")
        a.channels.append("slack")
        assert "slack" not in b.channels

    def test_quiet_hours_defaults(self):
        q = QuietHours()
        assert q.enabled is False
        assert q.start_hour == 22
        assert q.end_hour == 7
        assert q.timezone == "America/Los_Angeles"
        assert q.override_critical is True

    def test_escalation_rule_defaults(self):
        e = EscalationRule()
        assert e.enabled is True
        assert e.escalate_after_minutes == 60
        assert e.escalate_to == ""

    def test_notification_preferences_schema(self):
        prefs = _default_preferences("tenant-x")
        assert prefs.tenant_id == "tenant-x"
        assert prefs.digest_enabled is True
        assert prefs.digest_frequency == "daily"
        assert prefs.digest_time == "08:00"


class TestDefaultPreferences:
    def test_default_has_four_channels(self):
        prefs = _default_preferences("t")
        channels = [c.channel for c in prefs.channels]
        assert channels == ["email", "slack", "webhook", "sms"]

    def test_default_email_enabled_others_disabled(self):
        prefs = _default_preferences("t")
        assert prefs.channels[0].enabled is True  # email
        assert prefs.channels[1].enabled is False  # slack
        assert prefs.channels[2].enabled is False  # webhook
        assert prefs.channels[3].enabled is False  # sms

    def test_default_has_eight_alert_rules(self):
        prefs = _default_preferences("t")
        assert len(prefs.alert_preferences) == 8

    def test_default_event_volume_spike_disabled(self):
        prefs = _default_preferences("t")
        rules = {ap.rule_id: ap for ap in prefs.alert_preferences}
        assert rules["event-volume-spike"].enabled is False
        # Everything else starts enabled
        for rid, ap in rules.items():
            if rid != "event-volume-spike":
                assert ap.enabled is True

    def test_default_fda_deadline_has_sms(self):
        prefs = _default_preferences("t")
        fda = next(ap for ap in prefs.alert_preferences if ap.rule_id == "fda-deadline")
        assert "sms" in fda.channels

    def test_default_quiet_hours_off(self):
        prefs = _default_preferences("t")
        assert prefs.quiet_hours.enabled is False

    def test_default_escalation_60min(self):
        prefs = _default_preferences("t")
        assert prefs.escalation.escalate_after_minutes == 60
        assert prefs.escalation.escalate_to == "manager@example.com"

    def test_default_tenant_id_passthrough(self):
        prefs = _default_preferences("tenant-xyz")
        assert prefs.tenant_id == "tenant-xyz"


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


class TestDbGetPreferences:
    def test_db_hit_returns_prefs_with_injected_tenant_id(self, fake_jsonb):
        payload = _default_preferences("will-be-overwritten").model_dump(exclude={"tenant_id"})
        fake_jsonb.data[("t1", "tenant_notification_prefs", "prefs")] = payload
        prefs = _db_get_preferences("t1")
        assert prefs is not None
        assert prefs.tenant_id == "t1"

    def test_db_miss_returns_none(self, fake_jsonb):
        assert _db_get_preferences("missing") is None

    def test_db_empty_dict_treated_as_miss(self, fake_jsonb):
        # Empty-dict JSONB is falsy, so _db_get_preferences returns None
        fake_jsonb.data[("t2", "tenant_notification_prefs", "prefs")] = {}
        assert _db_get_preferences("t2") is None

    def test_db_get_calls_shared_helper(self, fake_jsonb):
        _db_get_preferences("t3")
        assert fake_jsonb.get_calls == [("t3", "tenant_notification_prefs", "prefs")]


class TestDbSavePreferences:
    def test_save_returns_true_on_success(self, fake_jsonb):
        prefs = _default_preferences("t1")
        assert _db_save_preferences("t1", prefs) is True

    def test_save_returns_false_on_failure(self, fake_jsonb):
        fake_jsonb.write_fail_for.add("t1")
        prefs = _default_preferences("t1")
        assert _db_save_preferences("t1", prefs) is False

    def test_save_excludes_tenant_id_from_stored_value(self, fake_jsonb):
        prefs = _default_preferences("t1")
        _db_save_preferences("t1", prefs)
        stored = fake_jsonb.data[("t1", "tenant_notification_prefs", "prefs")]
        assert "tenant_id" not in stored

    def test_save_calls_shared_helper(self, fake_jsonb):
        prefs = _default_preferences("t3")
        _db_save_preferences("t3", prefs)
        assert len(fake_jsonb.set_calls) == 1
        tid, table, col, _val = fake_jsonb.set_calls[0]
        assert (tid, table, col) == ("t3", "tenant_notification_prefs", "prefs")


# ---------------------------------------------------------------------------
# GET /{tenant_id}/preferences
# ---------------------------------------------------------------------------


class TestGetPreferencesEndpoint:
    def test_db_hit_returns_stored_prefs(self, client, fake_jsonb):
        payload = _default_preferences("x").model_dump(exclude={"tenant_id"})
        payload["digest_time"] = "09:30"
        fake_jsonb.data[("t1", "tenant_notification_prefs", "prefs")] = payload
        resp = client.get("/api/v1/notifications/t1/preferences")
        assert resp.status_code == 200
        body = resp.json()
        assert body["tenant_id"] == "t1"
        assert body["digest_time"] == "09:30"

    def test_db_hit_also_caches_in_memory(self, client, fake_jsonb):
        payload = _default_preferences("x").model_dump(exclude={"tenant_id"})
        fake_jsonb.data[("t1", "tenant_notification_prefs", "prefs")] = payload
        client.get("/api/v1/notifications/t1/preferences")
        assert "t1" in _prefs_store

    def test_db_miss_new_tenant_returns_defaults_and_caches(self, client, fake_jsonb):
        resp = client.get("/api/v1/notifications/brand-new/preferences")
        assert resp.status_code == 200
        body = resp.json()
        assert body["tenant_id"] == "brand-new"
        assert len(body["channels"]) == 4
        assert len(body["alert_preferences"]) == 8
        assert "brand-new" in _prefs_store

    def test_db_miss_existing_cache_returns_cache(self, client, fake_jsonb):
        cached = _default_preferences("t1")
        cached.digest_time = "11:11"
        _prefs_store["t1"] = cached
        resp = client.get("/api/v1/notifications/t1/preferences")
        assert resp.status_code == 200
        assert resp.json()["digest_time"] == "11:11"


# ---------------------------------------------------------------------------
# PUT /{tenant_id}/preferences
# ---------------------------------------------------------------------------


class TestUpdatePreferencesEndpoint:
    def _payload(self, tenant_id="whatever"):
        return _default_preferences(tenant_id).model_dump()

    def test_update_overrides_tenant_id_from_path(self, client, fake_jsonb):
        body = self._payload("in-body-should-be-overwritten")
        resp = client.put("/api/v1/notifications/t1/preferences", json=body)
        assert resp.status_code == 200
        assert resp.json()["tenant_id"] == "t1"

    def test_update_persists_to_db(self, client, fake_jsonb):
        body = self._payload("t1")
        body["digest_time"] = "15:00"
        client.put("/api/v1/notifications/t1/preferences", json=body)
        stored = fake_jsonb.data[("t1", "tenant_notification_prefs", "prefs")]
        assert stored["digest_time"] == "15:00"

    def test_update_caches_on_db_success(self, client, fake_jsonb):
        body = self._payload("t1")
        body["digest_time"] = "16:00"
        client.put("/api/v1/notifications/t1/preferences", json=body)
        assert _prefs_store["t1"].digest_time == "16:00"

    def test_update_falls_back_to_memory_on_db_failure(self, client, fake_jsonb):
        fake_jsonb.write_fail_for.add("t1")
        body = self._payload("t1")
        body["digest_time"] = "17:00"
        resp = client.put("/api/v1/notifications/t1/preferences", json=body)
        assert resp.status_code == 200
        assert _prefs_store["t1"].digest_time == "17:00"


# ---------------------------------------------------------------------------
# PUT /{tenant_id}/preferences/channel/{channel}
# ---------------------------------------------------------------------------


class TestToggleChannelEndpoint:
    def test_toggle_known_channel_off(self, client, fake_jsonb):
        _prefs_store["t1"] = _default_preferences("t1")
        resp = client.put(
            "/api/v1/notifications/t1/preferences/channel/email",
            params={"enabled": False},
        )
        assert resp.status_code == 200
        assert resp.json() == {"channel": "email", "enabled": False}
        assert _prefs_store["t1"].channels[0].enabled is False

    def test_toggle_unknown_channel_returns_error(self, client, fake_jsonb):
        _prefs_store["t1"] = _default_preferences("t1")
        resp = client.put(
            "/api/v1/notifications/t1/preferences/channel/carrier-pigeon",
            params={"enabled": True},
        )
        assert resp.status_code == 200
        assert "error" in resp.json()
        assert "carrier-pigeon" in resp.json()["error"]

    def test_toggle_initializes_defaults_when_tenant_unseen(self, client, fake_jsonb):
        resp = client.put(
            "/api/v1/notifications/brand-new/preferences/channel/slack",
            params={"enabled": True},
        )
        assert resp.status_code == 200
        assert resp.json() == {"channel": "slack", "enabled": True}
        assert "brand-new" in _prefs_store

    def test_toggle_uses_db_prefs_when_available(self, client, fake_jsonb):
        payload = _default_preferences("t1").model_dump(exclude={"tenant_id"})
        fake_jsonb.data[("t1", "tenant_notification_prefs", "prefs")] = payload
        resp = client.put(
            "/api/v1/notifications/t1/preferences/channel/slack",
            params={"enabled": True},
        )
        assert resp.status_code == 200
        assert resp.json() == {"channel": "slack", "enabled": True}

    def test_toggle_falls_back_to_memory_on_db_write_failure(self, client, fake_jsonb):
        _prefs_store["t1"] = _default_preferences("t1")
        fake_jsonb.write_fail_for.add("t1")
        resp = client.put(
            "/api/v1/notifications/t1/preferences/channel/email",
            params={"enabled": False},
        )
        assert resp.status_code == 200
        assert _prefs_store["t1"].channels[0].enabled is False

    def test_toggle_default_enabled_true(self, client, fake_jsonb):
        # ?enabled not supplied — default True
        _prefs_store["t1"] = _default_preferences("t1")
        _prefs_store["t1"].channels[1].enabled = False  # slack starts False
        resp = client.put("/api/v1/notifications/t1/preferences/channel/slack")
        assert resp.status_code == 200
        assert resp.json() == {"channel": "slack", "enabled": True}


# ---------------------------------------------------------------------------
# PUT /{tenant_id}/preferences/alert/{rule_id}
# ---------------------------------------------------------------------------


class TestToggleAlertRuleEndpoint:
    def test_toggle_known_rule_off(self, client, fake_jsonb):
        _prefs_store["t1"] = _default_preferences("t1")
        resp = client.put(
            "/api/v1/notifications/t1/preferences/alert/kde-missing",
            params={"enabled": False},
        )
        assert resp.status_code == 200
        assert resp.json() == {"rule_id": "kde-missing", "enabled": False}

    def test_toggle_unknown_rule_returns_error(self, client, fake_jsonb):
        _prefs_store["t1"] = _default_preferences("t1")
        resp = client.put(
            "/api/v1/notifications/t1/preferences/alert/phantom-rule",
            params={"enabled": True},
        )
        assert resp.status_code == 200
        assert "error" in resp.json()
        assert "phantom-rule" in resp.json()["error"]

    def test_toggle_rule_initializes_defaults_when_tenant_unseen(self, client, fake_jsonb):
        resp = client.put(
            "/api/v1/notifications/brand-new/preferences/alert/cte-overdue",
            params={"enabled": False},
        )
        assert resp.status_code == 200
        assert resp.json() == {"rule_id": "cte-overdue", "enabled": False}
        assert "brand-new" in _prefs_store

    def test_toggle_rule_uses_db_prefs_when_available(self, client, fake_jsonb):
        payload = _default_preferences("t1").model_dump(exclude={"tenant_id"})
        fake_jsonb.data[("t1", "tenant_notification_prefs", "prefs")] = payload
        resp = client.put(
            "/api/v1/notifications/t1/preferences/alert/event-volume-spike",
            params={"enabled": True},
        )
        assert resp.status_code == 200
        assert resp.json() == {"rule_id": "event-volume-spike", "enabled": True}

    def test_toggle_rule_falls_back_to_memory_on_db_failure(self, client, fake_jsonb):
        _prefs_store["t1"] = _default_preferences("t1")
        fake_jsonb.write_fail_for.add("t1")
        resp = client.put(
            "/api/v1/notifications/t1/preferences/alert/kde-missing",
            params={"enabled": False},
        )
        assert resp.status_code == 200
        kde = next(ap for ap in _prefs_store["t1"].alert_preferences if ap.rule_id == "kde-missing")
        assert kde.enabled is False

    def test_toggle_rule_default_enabled_true(self, client, fake_jsonb):
        _prefs_store["t1"] = _default_preferences("t1")
        # event-volume-spike starts disabled; toggle with no param -> True
        resp = client.put("/api/v1/notifications/t1/preferences/alert/event-volume-spike")
        assert resp.status_code == 200
        assert resp.json() == {"rule_id": "event-volume-spike", "enabled": True}


# ---------------------------------------------------------------------------
# Router surface
# ---------------------------------------------------------------------------


class TestRouterSurface:
    def test_router_prefix(self):
        assert router.prefix == "/api/v1/notifications"

    def test_router_tags(self):
        assert "Notification Preferences" in router.tags

    def test_router_routes(self):
        paths = {r.path for r in router.routes}
        assert "/api/v1/notifications/{tenant_id}/preferences" in paths
        assert "/api/v1/notifications/{tenant_id}/preferences/channel/{channel}" in paths
        assert "/api/v1/notifications/{tenant_id}/preferences/alert/{rule_id}" in paths
