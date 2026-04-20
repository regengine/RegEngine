"""Unit tests for ``app.settings`` — issue #1342.

Covers the tenant-settings router as an isolated unit — the Pydantic
models, the in-memory fallback cache, and each endpoint's DB-first /
memory-fallback path. No live DB, no live auth — ``get_jsonb`` /
``set_jsonb`` are swapped with in-process fakes and the
``_verify_api_key`` dependency is overridden on the FastAPI app.

The router guards the audit trail for tenant configuration changes, so
the tests pin the fallback ordering explicitly: if the DB write fails,
the in-memory cache must still reflect the mutation AND the failure
must be logged so operators know the change is not persisted to stable
storage.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

from app import settings as s  # noqa: E402
from app.settings import (  # noqa: E402
    CompanyProfile,
    DataRetention,
    IntegrationStatus,
    SettingsResponse,
    _db_get_settings,
    _db_save_settings,
    _default_settings,
    router,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_memory_store():
    """Clear the module-level in-memory cache between tests."""
    s._settings_store.clear()
    yield
    s._settings_store.clear()


@pytest.fixture
def client(monkeypatch):
    """Build a FastAPI app with the settings router and auth bypass."""
    app = FastAPI()
    app.include_router(router)

    # Bypass the API-key dependency — we test router logic, not auth.
    from app.webhook_compat import _verify_api_key
    app.dependency_overrides[_verify_api_key] = lambda: None
    return TestClient(app)


@pytest.fixture
def stubbed_jsonb(monkeypatch):
    """Swap ``get_jsonb`` / ``set_jsonb`` with in-process fakes.

    Returns a dict the test can inspect/manipulate:
        {"db": <payload store keyed by tenant_id>,
         "set_fail_for": <set of tenant_ids for which set_jsonb returns False>}
    """
    state = {"db": {}, "set_fail_for": set(), "set_calls": []}

    def _fake_get(tenant_id, table, column):
        assert table == "tenant_settings"
        assert column == "settings"
        data = state["db"].get(tenant_id)
        if data is None:
            return None
        # Simulate tenant_settings returning a copy each time (mirrors DB).
        return dict(data)

    def _fake_set(tenant_id, table, column, value):
        assert table == "tenant_settings"
        assert column == "settings"
        state["set_calls"].append((tenant_id, dict(value)))
        if tenant_id in state["set_fail_for"]:
            return False
        state["db"][tenant_id] = dict(value)
        return True

    monkeypatch.setattr(s, "get_jsonb", _fake_get)
    monkeypatch.setattr(s, "set_jsonb", _fake_set)
    return state


# ---------------------------------------------------------------------------
# Pydantic model defaults
# ---------------------------------------------------------------------------


class TestCompanyProfileDefaults:
    def test_all_strings_default_empty(self):
        profile = CompanyProfile()
        assert profile.company_name == ""
        assert profile.primary_contact == ""
        assert profile.contact_email == ""
        assert profile.phone == ""
        assert profile.address == ""
        assert profile.website == ""
        assert profile.fei_number == ""

    def test_company_type_defaults_distributor(self):
        assert CompanyProfile().company_type == "distributor"

    def test_field_override_accepted(self):
        profile = CompanyProfile(company_name="Acme", fei_number="FEI-12345")
        assert profile.company_name == "Acme"
        assert profile.fei_number == "FEI-12345"


class TestDataRetentionDefaults:
    def test_cte_retention_is_three_years(self):
        # FSMA 204 requires 2 years minimum — app defaults to 3 years.
        assert DataRetention().cte_retention_days == 1095

    def test_audit_log_retention_is_seven_years(self):
        # Aligns with common FDA audit-retention practice.
        assert DataRetention().audit_log_retention_days == 2555

    def test_export_retention_days(self):
        assert DataRetention().export_retention_days == 365

    def test_auto_archive_defaults_true(self):
        assert DataRetention().auto_archive is True


class TestIntegrationStatus:
    def test_required_fields(self):
        integ = IntegrationStatus(
            id="sensitech", name="Sensitech", category="iot", status="connected"
        )
        assert integ.id == "sensitech"
        assert integ.last_sync is None

    def test_last_sync_accepts_iso_string(self):
        integ = IntegrationStatus(
            id="x", name="y", category="iot", status="connected",
            last_sync="2026-04-17T00:00:00+00:00"
        )
        assert integ.last_sync == "2026-04-17T00:00:00+00:00"


# ---------------------------------------------------------------------------
# _default_settings
# ---------------------------------------------------------------------------


class TestDefaultSettings:
    def test_returns_settings_response(self):
        result = _default_settings("tenant-42")
        assert isinstance(result, SettingsResponse)
        assert result.tenant_id == "tenant-42"

    def test_profile_has_defaults(self):
        result = _default_settings("tenant-1")
        assert isinstance(result.profile, CompanyProfile)
        assert result.profile.company_name == ""

    def test_data_retention_has_fsma_defaults(self):
        result = _default_settings("tenant-1")
        assert result.data_retention.cte_retention_days == 1095

    def test_integrations_list_includes_sensitech_connected(self):
        result = _default_settings("tenant-1")
        integrations_by_id = {i.id: i for i in result.integrations}
        assert "sensitech" in integrations_by_id
        assert integrations_by_id["sensitech"].status == "connected"
        assert integrations_by_id["sensitech"].last_sync is not None

    def test_integrations_cover_iot_erp_retailer(self):
        result = _default_settings("tenant-1")
        categories = {i.category for i in result.integrations}
        assert {"iot", "erp", "retailer"} <= categories

    def test_api_keys_include_prod_and_dev(self):
        result = _default_settings("tenant-1")
        prefixes = {k["prefix"] for k in result.api_keys}
        assert "rge_prod_" in prefixes
        assert "rge_dev_" in prefixes

    def test_dev_key_has_never_been_used(self):
        result = _default_settings("tenant-1")
        dev_key = next(k for k in result.api_keys if k["prefix"] == "rge_dev_")
        assert dev_key["last_used"] is None

    def test_plan_is_professional(self):
        result = _default_settings("tenant-1")
        assert result.plan["id"] == "professional"
        assert result.plan["name"] == "Professional"
        assert result.plan["price_monthly"] == 499
        assert result.plan["facilities_limit"] == 5
        assert result.plan["events_limit"] == 50000


# ---------------------------------------------------------------------------
# _db_get_settings / _db_save_settings
# ---------------------------------------------------------------------------


class TestDbGetSettings:
    def test_returns_none_when_no_row(self, stubbed_jsonb):
        assert _db_get_settings("tenant-missing") is None

    def test_returns_settings_response_with_tenant_id_set(self, stubbed_jsonb):
        # Seed the fake DB with a minimal but valid payload. The function
        # always injects ``tenant_id`` from the query arg, so the stored
        # row doesn't need it.
        stubbed_jsonb["db"]["tenant-42"] = _default_settings(
            "ignored-in-storage"
        ).model_dump(exclude={"tenant_id"})

        result = _db_get_settings("tenant-42")
        assert isinstance(result, SettingsResponse)
        # tenant_id overwrite ensures a row mis-stored with the wrong ID
        # never leaks across tenants.
        assert result.tenant_id == "tenant-42"

    def test_empty_dict_treated_as_missing(self, stubbed_jsonb):
        # An empty dict is falsy — the helper must treat it as "no data".
        stubbed_jsonb["db"]["tenant-empty"] = {}
        assert _db_get_settings("tenant-empty") is None


class TestDbSaveSettings:
    def test_delegates_to_set_jsonb_and_returns_true(self, stubbed_jsonb):
        settings = _default_settings("tenant-42")
        assert _db_save_settings("tenant-42", settings) is True
        call = stubbed_jsonb["set_calls"][-1]
        tenant_id, payload = call
        assert tenant_id == "tenant-42"
        # tenant_id is excluded from the stored JSONB blob — the column
        # itself is keyed by tenant so duplicating it in the payload
        # would be redundant and risk drift.
        assert "tenant_id" not in payload

    def test_returns_false_when_set_jsonb_fails(self, stubbed_jsonb):
        stubbed_jsonb["set_fail_for"].add("tenant-42")
        settings = _default_settings("tenant-42")
        assert _db_save_settings("tenant-42", settings) is False


# ---------------------------------------------------------------------------
# GET /settings/{tenant_id}
# ---------------------------------------------------------------------------


class TestGetSettingsEndpoint:
    def test_db_hit_returns_settings_and_warms_cache(
        self, client, stubbed_jsonb
    ):
        stubbed_jsonb["db"]["tenant-42"] = _default_settings(
            "tenant-42"
        ).model_dump(exclude={"tenant_id"})

        resp = client.get("/api/v1/settings/tenant-42")
        assert resp.status_code == 200
        body = resp.json()
        assert body["tenant_id"] == "tenant-42"
        # Cache was primed for subsequent fallback reads.
        assert "tenant-42" in s._settings_store

    def test_db_miss_and_empty_cache_returns_defaults(
        self, client, stubbed_jsonb
    ):
        resp = client.get("/api/v1/settings/tenant-new")
        assert resp.status_code == 200
        body = resp.json()
        assert body["tenant_id"] == "tenant-new"
        assert body["data_retention"]["cte_retention_days"] == 1095
        # Defaults were cached so the next call is stable.
        assert "tenant-new" in s._settings_store

    def test_db_miss_uses_cached_settings_when_present(
        self, client, stubbed_jsonb
    ):
        # Pre-seed the cache with a custom company name, then confirm
        # the GET returns *that* value rather than re-computing defaults.
        custom = _default_settings("tenant-cached")
        custom.profile.company_name = "CachedCorp"
        s._settings_store["tenant-cached"] = custom

        resp = client.get("/api/v1/settings/tenant-cached")
        assert resp.status_code == 200
        assert resp.json()["profile"]["company_name"] == "CachedCorp"

    def test_response_shape_matches_settings_response(
        self, client, stubbed_jsonb
    ):
        resp = client.get("/api/v1/settings/tenant-1")
        assert resp.status_code == 200
        body = resp.json()
        # Top-level keys match SettingsResponse schema.
        assert set(body.keys()) == {
            "tenant_id", "profile", "data_retention",
            "integrations", "api_keys", "plan",
        }


# ---------------------------------------------------------------------------
# PUT /settings/{tenant_id}/profile
# ---------------------------------------------------------------------------


class TestUpdateProfileEndpoint:
    def test_db_hit_applies_update_and_saves(self, client, stubbed_jsonb):
        stubbed_jsonb["db"]["tenant-42"] = _default_settings(
            "tenant-42"
        ).model_dump(exclude={"tenant_id"})

        resp = client.put(
            "/api/v1/settings/tenant-42/profile",
            json={"company_name": "UpdatedCorp", "fei_number": "FEI-XX"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"updated": True}

        # The saved row reflects the new profile.
        saved_payload = stubbed_jsonb["db"]["tenant-42"]
        assert saved_payload["profile"]["company_name"] == "UpdatedCorp"
        assert saved_payload["profile"]["fei_number"] == "FEI-XX"
        # Memory cache was kept in sync.
        assert (
            s._settings_store["tenant-42"].profile.company_name
            == "UpdatedCorp"
        )

    def test_db_miss_and_empty_cache_creates_defaults_then_saves(
        self, client, stubbed_jsonb
    ):
        resp = client.put(
            "/api/v1/settings/tenant-new/profile",
            json={"company_name": "BrandNew", "company_type": "processor"},
        )
        assert resp.status_code == 200
        # Defaults materialized, update applied, save succeeded.
        assert "tenant-new" in stubbed_jsonb["db"]
        assert (
            stubbed_jsonb["db"]["tenant-new"]["profile"]["company_name"]
            == "BrandNew"
        )
        assert (
            stubbed_jsonb["db"]["tenant-new"]["profile"]["company_type"]
            == "processor"
        )

    def test_db_miss_with_existing_cache_updates_cached_settings(
        self, client, stubbed_jsonb
    ):
        # Cache is populated, DB has nothing → update reads cache, writes
        # to DB via set_jsonb.
        base = _default_settings("tenant-cached")
        base.profile.company_name = "BeforeUpdate"
        s._settings_store["tenant-cached"] = base

        resp = client.put(
            "/api/v1/settings/tenant-cached/profile",
            json={"company_name": "AfterUpdate"},
        )
        assert resp.status_code == 200
        assert (
            s._settings_store["tenant-cached"].profile.company_name
            == "AfterUpdate"
        )

    def test_db_save_failure_falls_back_to_memory_and_logs(
        self, client, stubbed_jsonb, caplog
    ):
        stubbed_jsonb["set_fail_for"].add("tenant-42")

        with caplog.at_level(logging.ERROR, logger="settings"):
            resp = client.put(
                "/api/v1/settings/tenant-42/profile",
                json={"company_name": "FallbackCorp"},
            )

        assert resp.status_code == 200
        assert resp.json() == {"updated": True}
        # Memory cache reflects the pending update even though DB write
        # failed — operators need the change available until storage
        # recovers.
        assert (
            s._settings_store["tenant-42"].profile.company_name
            == "FallbackCorp"
        )
        # Fallback MUST be logged at ERROR — silent memory-only writes
        # are an audit-trail regression.
        assert any(
            "db_write_failed_fallback_to_memory" in r.getMessage()
            and "endpoint=update_profile" in r.getMessage()
            for r in caplog.records
        )


# ---------------------------------------------------------------------------
# PUT /settings/{tenant_id}/retention
# ---------------------------------------------------------------------------


class TestUpdateRetentionEndpoint:
    def test_db_hit_applies_update_and_saves(self, client, stubbed_jsonb):
        stubbed_jsonb["db"]["tenant-42"] = _default_settings(
            "tenant-42"
        ).model_dump(exclude={"tenant_id"})

        resp = client.put(
            "/api/v1/settings/tenant-42/retention",
            json={
                "cte_retention_days": 1825,  # 5 years
                "audit_log_retention_days": 3650,  # 10 years
                "export_retention_days": 180,
                "auto_archive": False,
            },
        )
        assert resp.status_code == 200
        assert resp.json() == {"updated": True}

        saved = stubbed_jsonb["db"]["tenant-42"]["data_retention"]
        assert saved["cte_retention_days"] == 1825
        assert saved["audit_log_retention_days"] == 3650
        assert saved["auto_archive"] is False

    def test_db_miss_and_empty_cache_materializes_defaults(
        self, client, stubbed_jsonb
    ):
        resp = client.put(
            "/api/v1/settings/tenant-fresh/retention",
            json={
                "cte_retention_days": 2000,
                "audit_log_retention_days": 4000,
                "export_retention_days": 400,
                "auto_archive": True,
            },
        )
        assert resp.status_code == 200
        assert (
            stubbed_jsonb["db"]["tenant-fresh"]["data_retention"][
                "cte_retention_days"
            ]
            == 2000
        )
        # The profile section still carries the defaults so the row is
        # self-consistent.
        assert (
            stubbed_jsonb["db"]["tenant-fresh"]["profile"]["company_type"]
            == "distributor"
        )

    def test_db_miss_with_existing_cache_updates_cached_settings(
        self, client, stubbed_jsonb
    ):
        base = _default_settings("tenant-cached")
        s._settings_store["tenant-cached"] = base
        assert base.data_retention.cte_retention_days == 1095

        resp = client.put(
            "/api/v1/settings/tenant-cached/retention",
            json={
                "cte_retention_days": 5000,
                "audit_log_retention_days": 2555,
                "export_retention_days": 365,
                "auto_archive": True,
            },
        )
        assert resp.status_code == 200
        assert (
            s._settings_store["tenant-cached"].data_retention.cte_retention_days
            == 5000
        )

    def test_db_save_failure_falls_back_to_memory_and_logs(
        self, client, stubbed_jsonb, caplog
    ):
        stubbed_jsonb["set_fail_for"].add("tenant-42")

        with caplog.at_level(logging.ERROR, logger="settings"):
            resp = client.put(
                "/api/v1/settings/tenant-42/retention",
                json={
                    "cte_retention_days": 2555,
                    "audit_log_retention_days": 2555,
                    "export_retention_days": 365,
                    "auto_archive": True,
                },
            )

        assert resp.status_code == 200
        assert resp.json() == {"updated": True}
        assert (
            s._settings_store["tenant-42"].data_retention.cte_retention_days
            == 2555
        )
        # The endpoint tag in the log line is how audit tools bucket the
        # fallback events — pin it so we notice if someone renames it.
        assert any(
            "db_write_failed_fallback_to_memory" in r.getMessage()
            and "endpoint=update_retention" in r.getMessage()
            for r in caplog.records
        )
