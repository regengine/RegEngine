"""Data-free inbound webhook validation and error-path checks."""

from __future__ import annotations

import importlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

from app.authz import IngestionPrincipal  # noqa: E402
from app.webhook_models import REQUIRED_KDES_BY_CTE, IngestEvent, WebhookCTEType  # noqa: E402
from app.webhook_router_v2 import (  # noqa: E402
    tenant as wt,
    validation as wv,
)


class TestTimestampValidator:
    def test_naive_timestamp_accepted_as_utc(self):
        naive = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        assert IngestEvent.validate_timestamp(naive) == naive

    def test_naive_future_timestamp_rejected(self):
        future = (datetime.now(timezone.utc) + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%S")
        with pytest.raises(ValueError, match="future"):
            IngestEvent.validate_timestamp(future)

    def test_empty_timestamp_rejected(self):
        with pytest.raises(ValueError, match="Invalid ISO 8601 timestamp"):
            IngestEvent.validate_timestamp("")

    def test_aware_future_timestamp_rejected(self):
        future = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        with pytest.raises(ValueError, match="future"):
            IngestEvent.validate_timestamp(future)


class TestEventValidation:
    def _empty_event(self, cte_type: WebhookCTEType):
        return IngestEvent.model_construct(
            cte_type=cte_type,
            traceability_lot_code=None,
            product_description=None,
            quantity=None,
            unit_of_measure=None,
            timestamp=None,
            location_name=None,
            location_gln=None,
            kdes={},
        )

    def test_missing_required_kdes_reported_from_empty_model(self):
        event = self._empty_event(WebhookCTEType.HARVESTING)
        errors = wv._validate_event_kdes(event)
        assert len(errors) == len(REQUIRED_KDES_BY_CTE[WebhookCTEType.HARVESTING])
        assert all("Missing required KDE" in error for error in errors)

    def test_empty_kde_does_not_satisfy_requirement(self):
        event = self._empty_event(WebhookCTEType.HARVESTING)
        event.kdes["location_name"] = ""
        errors = wv._validate_event_kdes(event)
        assert any("location_name" in error for error in errors)

    def test_shipping_without_route_warns(self):
        event = self._empty_event(WebhookCTEType.SHIPPING)
        assert any(alert["alert_type"] == "incomplete_route" for alert in wv._generate_alerts(event))


class TestResolveIngestTenant:
    def _principal_with_sentinel(self, scopes=("webhooks.ingest",)):
        return SimpleNamespace(tenant_id=object(), scopes=scopes)

    def test_payload_mismatch_is_403(self):
        with pytest.raises(HTTPException) as exc:
            wt._resolve_ingest_tenant_id(
                payload_tenant_id=object(),
                principal=self._principal_with_sentinel(),
                x_regengine_api_key=None,
                x_tenant_id=None,
            )
        assert exc.value.status_code == 403

    def test_header_mismatch_is_403(self):
        with pytest.raises(HTTPException) as exc:
            wt._resolve_ingest_tenant_id(
                payload_tenant_id=None,
                principal=self._principal_with_sentinel(),
                x_regengine_api_key=None,
                x_tenant_id=object(),
            )
        assert exc.value.status_code == 403

    def test_wildcard_scope_does_not_grant_tenant_breadth(self):
        with pytest.raises(HTTPException) as exc:
            wt._resolve_ingest_tenant_id(
                payload_tenant_id=object(),
                principal=self._principal_with_sentinel(scopes=("*",)),
                x_regengine_api_key=None,
                x_tenant_id=None,
            )
        assert exc.value.status_code == 403

    def test_legacy_without_any_tenant_is_400(self):
        with pytest.raises(HTTPException) as exc:
            wt._resolve_ingest_tenant_id(
                payload_tenant_id=None,
                principal=IngestionPrincipal(key_id="", scopes=[], tenant_id=None),
                x_regengine_api_key=None,
                x_tenant_id=None,
            )
        assert exc.value.status_code == 400


class TestReplayWindow:
    def test_naive_timestamp_assumed_utc(self):
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
        rl = self._reload(monkeypatch, {"WEBHOOK_INGEST_RATE_LIMIT_RPM": ""})
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
        app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
            key_id="", scopes=["records.read"], tenant_id=None
        )
        app.dependency_overrides[get_db_session] = lambda: None
        return TestClient(app, raise_server_exceptions=False)

    def test_negative_limit_is_422(self):
        response = self._client().get("/api/v1/records", params={"limit": -1})
        assert response.status_code == 422

    def test_negative_offset_is_422(self):
        response = self._client().get("/api/v1/records", params={"offset": -1})
        assert response.status_code == 422
