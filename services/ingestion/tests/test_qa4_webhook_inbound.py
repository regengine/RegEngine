"""QA deep pass: inbound webhook surface (tenant isolation, validation, errors).

Covers ``app.webhook_models`` timestamp validation, the v2 KDE/alert
helpers, tenant resolution, the replay window, rate-limit env handling,
and canonical-record paging bounds. Fast and deterministic: no DB,
no network, no sleeps.
"""

from __future__ import annotations

import importlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

from app.authz import IngestionPrincipal  # noqa: E402
from app.webhook_models import IngestEvent, WebhookCTEType  # noqa: E402
from app.webhook_router_v2 import (
    tenant as wt,  # noqa: E402
    validation as wv,  # noqa: E402
)


def _harvest_kwargs(**overrides):
    base = {
        "cte_type": WebhookCTEType.HARVESTING,
        "traceability_lot_code": "TLC-2026-ABC",
        "product_description": "Romaine Lettuce",
        "quantity": 10,
        "unit_of_measure": "cases",
        "timestamp": "2026-04-15T12:00:00Z",
        "location_name": "Metro DC",
        "kdes": {
            "harvest_date": "2026-04-14",
            "reference_document": "PO-123",
        },
    }
    base.update(overrides)
    return base


class TestNaiveTimestamp:
    def test_naive_timestamp_accepted_as_utc(self):
        event = IngestEvent(**_harvest_kwargs(timestamp="2026-04-15T12:00:00"))
        assert event.timestamp == "2026-04-15T12:00:00"

    def test_naive_future_timestamp_rejected_as_422(self):
        future = (datetime.now(timezone.utc) + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%S")
        with pytest.raises(ValidationError):
            IngestEvent(**_harvest_kwargs(timestamp=future))

    def test_garbage_timestamp_rejected(self):
        with pytest.raises(ValidationError):
            IngestEvent(**_harvest_kwargs(timestamp="not-a-date"))

    def test_aware_future_timestamp_rejected(self):
        future = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        with pytest.raises(ValidationError):
            IngestEvent(**_harvest_kwargs(timestamp=future))


class TestEventValidation:
    def test_complete_harvest_event_passes(self):
        assert wv._validate_event_kdes(IngestEvent(**_harvest_kwargs())) == []

    def test_missing_required_kde_reported(self):
        kdes = {"harvest_date": "2026-04-14"}
        errors = wv._validate_event_kdes(IngestEvent(**_harvest_kwargs(kdes=kdes)))
        assert any("reference_document" in e for e in errors)

    def test_kdes_empty_string_does_not_clobber_top_level(self):
        # A colliding KDE key with an empty value must not erase the
        # authoritative top-level field and cause a false rejection.
        kdes = {
            "harvest_date": "2026-04-14",
            "reference_document": "PO-123",
            "location_name": "",
        }
        assert wv._validate_event_kdes(IngestEvent(**_harvest_kwargs(kdes=kdes))) == []

    def test_kdes_fills_gap_when_top_level_absent(self):
        # location_name lives only in kdes: still satisfies the requirement,
        # preserving the historical pass for KDE-carried locations.
        kwargs = _harvest_kwargs(location_name=None, location_gln="0614141000005")
        event = IngestEvent(**kwargs)
        event.kdes["location_name"] = "Metro DC"
        assert wv._validate_event_kdes(event) == []

    def test_shipping_without_route_warns(self):
        event = IngestEvent(
            **{
                **_harvest_kwargs(),
                "cte_type": WebhookCTEType.SHIPPING,
                "kdes": {
                    "ship_date": "2026-04-14",
                    "reference_document": "PO-123",
                    "tlc_source_reference": "SRC-1",
                },
            }
        )
        assert any(a["alert_type"] == "incomplete_route" for a in wv._generate_alerts(event))


class TestResolveIngestTenant:
    def _principal(self, tenant_id, scopes=("webhooks.ingest",)):
        return IngestionPrincipal(key_id="k1", scopes=list(scopes), tenant_id=tenant_id)

    def test_scoped_key_wins_over_matching_claims(self):
        principal = self._principal("tenant-a")
        assert (
            wt._resolve_ingest_tenant_id(
                payload_tenant_id="tenant-a",
                principal=principal,
                x_regengine_api_key="key",
                x_tenant_id="tenant-a",
            )
            == "tenant-a"
        )

    def test_payload_mismatch_is_403(self):
        with pytest.raises(HTTPException) as exc:
            wt._resolve_ingest_tenant_id(
                payload_tenant_id="tenant-b",
                principal=self._principal("tenant-a"),
                x_regengine_api_key="key",
                x_tenant_id=None,
            )
        assert exc.value.status_code == 403

    def test_header_mismatch_is_403(self):
        with pytest.raises(HTTPException) as exc:
            wt._resolve_ingest_tenant_id(
                payload_tenant_id=None,
                principal=self._principal("tenant-a"),
                x_regengine_api_key="key",
                x_tenant_id="tenant-b",
            )
        assert exc.value.status_code == 403

    def test_wildcard_scope_does_not_grant_tenant_breadth(self):
        with pytest.raises(HTTPException) as exc:
            wt._resolve_ingest_tenant_id(
                payload_tenant_id="tenant-b",
                principal=self._principal("tenant-a", scopes=("*",)),
                x_regengine_api_key="key",
                x_tenant_id=None,
            )
        assert exc.value.status_code == 403

    def test_legacy_fallback_prefers_payload_then_key_then_header(self, monkeypatch):
        import app.webhook_router_v2 as pkg

        calls = []

        def _fake_lookup(raw_key):
            calls.append(raw_key)
            return "tenant-from-key"

        monkeypatch.setattr(pkg, "_lookup_tenant_id_for_api_key", _fake_lookup)
        unbound = self._principal(None)
        assert (
            wt._resolve_ingest_tenant_id(
                payload_tenant_id="tenant-payload",
                principal=unbound,
                x_regengine_api_key="key",
                x_tenant_id="tenant-header",
            )
            == "tenant-payload"
        )
        assert calls == []
        assert (
            wt._resolve_ingest_tenant_id(
                payload_tenant_id=None,
                principal=unbound,
                x_regengine_api_key="key",
                x_tenant_id="tenant-header",
            )
            == "tenant-from-key"
        )
        monkeypatch.setattr(pkg, "_lookup_tenant_id_for_api_key", lambda _k: None)
        assert (
            wt._resolve_ingest_tenant_id(
                payload_tenant_id=None,
                principal=unbound,
                x_regengine_api_key="key",
                x_tenant_id="tenant-header",
            )
            == "tenant-header"
        )

    def test_legacy_without_any_tenant_is_400(self, monkeypatch):
        import app.webhook_router_v2 as pkg

        monkeypatch.setattr(pkg, "_lookup_tenant_id_for_api_key", lambda _k: None)
        with pytest.raises(HTTPException) as exc:
            wt._resolve_ingest_tenant_id(
                payload_tenant_id=None,
                principal=self._principal(None),
                x_regengine_api_key=None,
                x_tenant_id=None,
            )
        assert exc.value.status_code == 400


class TestReplayWindow:
    def test_naive_timestamp_assumed_utc(self):
        # The fresh/stale/future/unparseable matrix is locked by
        # test_webhook_hmac_and_replay.py; this pins the one case it
        # does not: naive input is read as UTC, matching the
        # IngestEvent validator fix in this PR.
        from app.webhook_router_v2 import security as sec

        naive = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        assert sec._validate_event_timestamp_window(naive) is None


class TestRateLimitEnvGuard:
    def _reload(self, monkeypatch, env):
        import app.webhook_router_v2.ratelimit as rl

        for key in (
            "WEBHOOK_INGEST_RATE_LIMIT_RPM",
            "WEBHOOK_INGEST_RATE_LIMIT_WINDOW_SECONDS",
            "WEBHOOK_READ_RATE_LIMIT_RPM",
            "WEBHOOK_READ_RATE_LIMIT_WINDOW_SECONDS",
        ):
            monkeypatch.delenv(key, raising=False)
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        return importlib.reload(rl)

    def test_garbage_env_falls_back_to_defaults(self, monkeypatch):
        rl = self._reload(monkeypatch, {"WEBHOOK_INGEST_RATE_LIMIT_RPM": "abc"})
        assert rl._WEBHOOK_RATE_LIMIT_RPM == 120
        assert rl._WEBHOOK_RATE_LIMIT_WINDOW_SECS == 60
        assert rl._WEBHOOK_READ_RATE_LIMIT_RPM == 30
        assert rl._WEBHOOK_READ_RATE_LIMIT_WINDOW_SECS == 60

    def test_valid_env_is_honored(self, monkeypatch):
        rl = self._reload(
            monkeypatch,
            {"WEBHOOK_INGEST_RATE_LIMIT_RPM": "50", "WEBHOOK_READ_RATE_LIMIT_RPM": "10"},
        )
        assert rl._WEBHOOK_RATE_LIMIT_RPM == 50
        assert rl._WEBHOOK_READ_RATE_LIMIT_RPM == 10

    def test_zero_and_negative_clamp_to_one(self, monkeypatch):
        rl = self._reload(monkeypatch, {"WEBHOOK_INGEST_RATE_LIMIT_RPM": "0"})
        assert rl._WEBHOOK_RATE_LIMIT_RPM == 1


class TestCanonicalPagingBounds:
    def _client(self):
        from app.authz import get_ingestion_principal
        from app.canonical_router import router
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from shared.database import get_db_session

        app = FastAPI()
        app.include_router(router)
        tenant_id = "tenant-a"
        app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
            key_id="k1", scopes=["records.read"], tenant_id=tenant_id
        )
        app.dependency_overrides[get_db_session] = lambda: None
        client = TestClient(app, raise_server_exceptions=False)
        return client, tenant_id

    def test_negative_limit_is_422(self):
        client, tenant_id = self._client()
        response = client.get("/api/v1/records", params={"tenant_id": tenant_id, "limit": -1})
        assert response.status_code == 422

    def test_negative_offset_is_422(self):
        client, tenant_id = self._client()
        response = client.get("/api/v1/records", params={"tenant_id": tenant_id, "offset": -5})
        assert response.status_code == 422
