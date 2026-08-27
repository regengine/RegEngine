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
  incident. The last test locks that boundary.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any, Dict, List

import pytest
from fastapi.testclient import TestClient

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

import app.webhook_router_v2 as wr  # noqa: E402

from services.ingestion.tests.test_webhook_router_v2_1342 import (  # noqa: E402
    _FakePersistence,
    _FakeSession,
    _build_app,
    _client,
    _make_shipping_event,
)

TENANT_ID = "tenant-a"

# Values that must never reach a log line. These are the customer's
# supply-chain identifiers, not diagnostics.
SECRET_TLC = "TLC-CUSTOMER-CONFIDENTIAL-0001"
SECRET_PRODUCT = "Romaine Hearts Lot 42 for Metro DC"


class _LogRecorder:
    """Stand-in for the structlog logger that records every emitted call."""

    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    def _record(self, level: str):
        def _emit(event: Any = None, *args: Any, **kwargs: Any) -> None:
            self.calls.append(
                {"level": level, "event": event, "args": args, "kwargs": kwargs}
            )

        return _emit

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        return self._record(name)

    def find(self, event: str) -> Dict[str, Any]:
        matches = [c for c in self.calls if c["event"] == event]
        assert matches, (
            f"expected a {event!r} log line; got {[c['event'] for c in self.calls]}"
        )
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
    captured = call["level"] == "exception" or bool(_fields(call).get("exc_info")) or bool(
        call["kwargs"].get("exc_info")
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
# ---------------------------------------------------------------------------


class TestIngestBatchFailureLogging:
    def _payload(self) -> dict:
        event = _make_shipping_event(tlc=SECRET_TLC)
        event["product_description"] = SECRET_PRODUCT
        return {"source": "erp-connector", "events": [event]}

    def _blow_up(self, monkeypatch, exc: Exception):
        session = _FakeSession()

        class _BoomPersistence(_FakePersistence):
            def store_events_batch(self, **kw):
                raise exc

        persistence = _BoomPersistence(session)
        return _client(monkeypatch, session=session, persistence=persistence)

    def test_logs_traceback(self, monkeypatch, recorder: _LogRecorder) -> None:
        client, _s, _p = self._blow_up(monkeypatch, SystemError("wholly unexpected"))
        resp = client.post(
            "/api/v1/webhooks/ingest",
            json=self._payload(),
            headers={"Idempotency-Key": "idem-2868-tb"},
        )
        assert resp.status_code == 500
        _assert_traceback_captured(recorder.find("ingest_batch_failed"))

    def test_logs_tenant_and_correlation_id(
        self, monkeypatch, recorder: _LogRecorder
    ) -> None:
        client, _s, _p = self._blow_up(monkeypatch, SystemError("wholly unexpected"))
        resp = client.post(
            "/api/v1/webhooks/ingest",
            json=self._payload(),
            headers={"Idempotency-Key": "idem-2868-ids"},
        )
        assert resp.status_code == 500
        fields = _fields(recorder.find("ingest_batch_failed"))
        assert fields.get("tenant_id") == TENANT_ID, (
            "without tenant_id there is no way to tell whose batch failed (#2868)"
        )
        assert fields.get("correlation_id"), (
            "the 500 body points the caller at the logs; a correlation id is "
            "what lets support join the two (#2868)"
        )

    def test_logs_error_type_so_outage_differs_from_bug(
        self, monkeypatch, recorder: _LogRecorder
    ) -> None:
        """A bare ``except Exception`` makes every failure look alike."""
        client, _s, _p = self._blow_up(monkeypatch, SystemError("wholly unexpected"))
        client.post(
            "/api/v1/webhooks/ingest",
            json=self._payload(),
            headers={"Idempotency-Key": "idem-2868-type"},
        )
        fields = _fields(recorder.find("ingest_batch_failed"))
        assert fields.get("error_type") == "SystemError", (
            "the handler catches bare Exception, so the log line must name the "
            "exception class or a DB outage is indistinguishable from a "
            "programming error (#2868)"
        )

    def test_logs_batch_shape_for_triage(
        self, monkeypatch, recorder: _LogRecorder
    ) -> None:
        client, _s, _p = self._blow_up(monkeypatch, SystemError("wholly unexpected"))
        client.post(
            "/api/v1/webhooks/ingest",
            json=self._payload(),
            headers={"Idempotency-Key": "idem-2868-shape"},
        )
        fields = _fields(recorder.find("ingest_batch_failed"))
        assert fields.get("event_count") == 1
        assert fields.get("source") == "erp-connector"

    def test_does_not_log_customer_supply_chain_data(
        self, monkeypatch, recorder: _LogRecorder
    ) -> None:
        """Diagnostics only — never the payload.

        Lot codes and product descriptions identify a specific customer's
        shipment. Fixing an under-logging bug by dumping the request body
        would trade a debuggability gap for a data-handling incident.
        """
        client, _s, _p = self._blow_up(monkeypatch, SystemError("wholly unexpected"))
        client.post(
            "/api/v1/webhooks/ingest",
            json=self._payload(),
            headers={"Idempotency-Key": "idem-2868-pii"},
        )
        logged = recorder.payload_text()
        assert SECRET_TLC not in logged, (
            "traceability lot codes are customer supply-chain data and must "
            "not be logged (#2868)"
        )
        assert SECRET_PRODUCT not in logged, (
            "product descriptions are customer supply-chain data and must not "
            "be logged (#2868)"
        )


# ---------------------------------------------------------------------------
# GET /api/v1/webhooks/chain/verify
# ---------------------------------------------------------------------------


class TestChainVerifyFailureLogging:
    def _client(self, monkeypatch) -> TestClient:
        session = _FakeSession()

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

    def test_logs_traceback_tenant_and_error_type(
        self, monkeypatch, recorder: _LogRecorder
    ) -> None:
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
            "chain verification failures must name the tenant whose hash "
            "chain could not be walked (#2868)"
        )
        assert fields.get("error_type") == "RuntimeError"
        assert fields.get("correlation_id"), (
            "a correlation id is what makes 'check server logs' actionable "
            "(#2868)"
        )
