"""Regression tests for #2868 — /ingest 500s told callers to read empty logs.

Both the batch-ingest and chain-verification handlers returned
``"... Check server logs for details."`` while logging only ``str(e)``:

    _pkg.logger.error("ingest_batch_failed", extra={"error": str(e)})

No traceback, no tenant, no correlation id, and no exception type — so the
log line held strictly *less* information than the error message the caller
already had, and there was no way to tell which tenant's batch failed or
whether the cause was a database outage or a programming error.

The corrected contract asserted here:

* the traceback is captured (``logger.exception`` / ``exc_info``),
* ``tenant_id``, ``correlation_id`` and ``error_type`` are explicit fields,
* and **no customer supply-chain data** rides along. This is a food-safety
  compliance platform: lot codes and product descriptions identify a
  specific customer's shipment, so an over-eager log line is its own
  incident. ``TestFailureDiagnostics`` locks that boundary.
"""

from __future__ import annotations

import json
import logging
import sys
import types
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

import app.webhook_router_v2 as wr  # noqa: E402
from app.authz import IngestionPrincipal, get_ingestion_principal  # noqa: E402
from app.webhook_models import WebhookCTEType  # noqa: E402
from app.webhook_router_v2.routes import _failure_diagnostics  # noqa: E402

# Identifiers are minted per test run with uuid4; nothing here is a recorded
# or invented customer value.
TENANT_ID = str(uuid.uuid4())
KEY_ID = str(uuid.uuid4())


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(wr.router)
    app.dependency_overrides[wr._verify_api_key] = lambda: None
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id=KEY_ID,
        scopes=["*"],
        tenant_id=TENANT_ID,
        auth_mode="test",
    )
    return app


class _LogRecorder:
    """Stand-in for the structlog logger that records every emitted call."""

    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    def _record(self, level: str):
        def _emit(event: Any = None, *args: Any, **kwargs: Any) -> None:
            self.calls.append({"level": level, "event": event, "args": args, "kwargs": kwargs})

        return _emit

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        return self._record(name)

    def find(self, event: str) -> Dict[str, Any]:
        matches = [c for c in self.calls if c["event"] == event]
        assert matches, f"expected a {event!r} log line; got {[c['event'] for c in self.calls]}"
        return matches[0]

    def payload_text(self) -> str:
        """Every logged value flattened to one string, for leak assertions."""
        return " ".join(repr(c) for c in self.calls)


def _fields(call: Dict[str, Any]) -> Dict[str, Any]:
    """Structured fields, whether passed as kwargs or a stdlib ``extra`` dict."""
    fields = dict(call["kwargs"])
    extra = fields.pop("extra", None)
    if isinstance(extra, dict):
        fields.update(extra)
    return fields


def _assert_traceback_captured(call: Dict[str, Any]) -> None:
    captured = (
        call["level"] == "exception" or bool(_fields(call).get("exc_info")) or bool(call["kwargs"].get("exc_info"))
    )
    assert captured, (
        "the 500 handler tells the caller to check the logs, so the log line "
        "must carry the traceback — use logger.exception(...) or "
        "exc_info=True (#2868)"
    )


@pytest.fixture()
def recorder(monkeypatch) -> _LogRecorder:
    rec = _LogRecorder()
    monkeypatch.setattr(wr, "logger", rec)
    return rec


# ---------------------------------------------------------------------------
# POST /api/v1/webhooks/ingest
#
# WebhookPayload requires at least one structurally valid event, so the
# request carries exactly one. Its lot code, product text and location are uuid4
# canaries minted at runtime (not invented supply-chain records); they exist
# only so the redaction assertion has something concrete to look for. The
# persistence stub is a MagicMock whose batch store raises, which is the
# smallest path into the handler's ``except Exception`` block.
# ---------------------------------------------------------------------------


class TestIngestBatchFailureLogging:
    def _post(self, monkeypatch, caplog):
        from app.subscription_gate import require_active_subscription
        from shared.database import get_db_session

        session = MagicMock()
        persistence = MagicMock()
        persistence.store_events_batch.side_effect = SystemError("store unavailable")
        fake_cte = types.ModuleType("shared.cte_persistence")
        fake_cte.CTEPersistence = lambda _s: persistence
        monkeypatch.setitem(sys.modules, "shared.cte_persistence", fake_cte)

        monkeypatch.setattr(wr, "consume_tenant_rate_limit", lambda **_kw: (True, 999))
        monkeypatch.setattr("app.authz.consume_tenant_rate_limit", lambda **_kw: (True, 999))
        # KDE completeness and alert generation are covered elsewhere; skip
        # them so the one event reaches the batch store without extra fields.
        monkeypatch.setattr(wr, "_validate_event_kdes", lambda _e: [])
        monkeypatch.setattr(wr, "_generate_alerts", lambda _e: [])
        monkeypatch.setattr(wr, "_rules_preeval_reject", lambda *_a, **_kw: (False, None, None))
        for var in ("API_KEY", "REGENGINE_API_KEY", "WEBHOOK_HMAC_SECRET"):
            monkeypatch.delenv(var, raising=False)

        app = _build_app()
        app.dependency_overrides[wr._verify_webhook_signature] = lambda: None
        app.dependency_overrides[require_active_subscription] = lambda: None

        def _db():
            yield session

        app.dependency_overrides[get_db_session] = _db

        canary_tlc = uuid.uuid4().hex
        canary_product = uuid.uuid4().hex
        canary_location = uuid.uuid4().hex
        source = uuid.uuid4().hex
        payload = {
            "source": source,
            "events": [
                {
                    "cte_type": WebhookCTEType.SHIPPING.value,
                    "traceability_lot_code": canary_tlc,
                    "product_description": canary_product,
                    "location_name": canary_location,
                    "quantity": 1,
                    "unit_of_measure": "",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "kdes": {},
                }
            ],
        }
        with caplog.at_level(logging.DEBUG):
            resp = TestClient(app).post(
                "/api/v1/webhooks/ingest",
                json=payload,
                headers={"Idempotency-Key": uuid.uuid4().hex},
            )
        return resp, source, (canary_tlc, canary_product, canary_location)

    def _record(self, caplog) -> logging.LogRecord:
        matches = [r for r in caplog.records if "ingest_batch_failed" in r.getMessage()]
        assert matches, f"expected an ingest_batch_failed log line; got {[r.getMessage() for r in caplog.records]}"
        return matches[0]

    def test_logs_traceback_tenant_count_and_source(self, monkeypatch, caplog) -> None:
        resp, source, _canaries = self._post(monkeypatch, caplog)
        assert resp.status_code == 500, resp.text
        record = self._record(caplog)
        fields = json.loads(record.getMessage())
        assert record.levelno == logging.ERROR
        assert "Traceback" in fields.get("exception", ""), "ingest_batch_failed must carry the traceback (#2868)"
        assert fields["tenant_id"] == TENANT_ID, "without tenant_id there is no way to tell whose batch failed (#2868)"
        assert fields["event_count"] == 1
        assert fields["source"] == source
        assert fields["error_type"] == "SystemError"
        assert fields["correlation_id"]

    def test_does_not_log_lot_code_or_product_text(self, monkeypatch, caplog) -> None:
        """Diagnostics only, never the payload (#2868)."""
        resp, _source, canaries = self._post(monkeypatch, caplog)
        assert resp.status_code == 500
        self._record(caplog)
        logged = " ".join(r.getMessage() + (caplog.text or "") for r in caplog.records)
        for canary in canaries:
            assert canary not in logged, "request-body values must not reach the log (#2868)"


# ---------------------------------------------------------------------------
# Shared 5xx diagnostics (used by POST /api/v1/webhooks/ingest)
#
# The ingest-batch route cases were removed: they needed a fabricated
# shipping event and an in-memory persistence fake, both dropped in the
# real-data-only test cleanup. The diagnostics contract the ingest handler
# relies on is checked directly, with no request body at all.
# ---------------------------------------------------------------------------


class TestFailureDiagnostics:
    def _request(self, correlation_id=None) -> MagicMock:
        request = MagicMock()
        request.state.correlation_id = correlation_id
        return request

    def test_names_error_type_so_outage_differs_from_bug(self) -> None:
        diag = _failure_diagnostics(self._request(), SystemError())
        assert diag["error_type"] == "SystemError"

    def test_always_carries_correlation_id(self) -> None:
        diag = _failure_diagnostics(self._request(), RuntimeError())
        assert diag["correlation_id"]

    def test_reuses_request_correlation_id(self) -> None:
        cid = str(uuid.uuid4())
        diag = _failure_diagnostics(self._request(cid), RuntimeError())
        assert diag["correlation_id"] == cid

    def test_only_diagnostic_fields(self) -> None:
        """Diagnostics only, never the payload (#2868)."""
        diag = _failure_diagnostics(self._request(), RuntimeError())
        assert set(diag) == {"correlation_id", "error", "error_type"}


# ---------------------------------------------------------------------------
# GET /api/v1/webhooks/chain/verify
# ---------------------------------------------------------------------------


class TestChainVerifyFailureLogging:
    def _client(self, monkeypatch) -> TestClient:
        session = MagicMock()

        class _BadPersistence:
            def __init__(self, _s):
                pass

            def verify_chain(self, _tid):
                raise RuntimeError("chain broken")

        fake_db = types.ModuleType("shared.database")
        fake_db.SessionLocal = lambda: session
        monkeypatch.setitem(sys.modules, "shared.database", fake_db)

        fake_cte = types.ModuleType("shared.cte_persistence")
        fake_cte.CTEPersistence = _BadPersistence
        monkeypatch.setitem(sys.modules, "shared.cte_persistence", fake_cte)

        monkeypatch.setattr(wr, "consume_tenant_rate_limit", lambda **_kw: (True, 999))
        monkeypatch.setattr("app.authz.consume_tenant_rate_limit", lambda **_kw: (True, 999))
        monkeypatch.delenv("API_KEY", raising=False)
        monkeypatch.delenv("REGENGINE_API_KEY", raising=False)

        app = _build_app()
        return TestClient(app)

    def test_logs_traceback_tenant_and_error_type(self, monkeypatch, recorder: _LogRecorder) -> None:
        client = self._client(monkeypatch)
        resp = client.get(
            "/api/v1/webhooks/chain/verify",
            params={"tenant_id": TENANT_ID},
        )
        assert resp.status_code == 500
        call = recorder.find("chain_verification_failed")
        _assert_traceback_captured(call)
        fields = _fields(call)
        assert fields.get("tenant_id") == TENANT_ID, (
            "chain verification failures must name the tenant whose hash chain could not be walked (#2868)"
        )
        assert fields.get("error_type") == "RuntimeError"
        assert fields.get("correlation_id"), "a correlation id is what makes 'check server logs' actionable (#2868)"
