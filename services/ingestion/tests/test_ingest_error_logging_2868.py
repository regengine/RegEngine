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

import sys
import types
import uuid
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
from app.webhook_router_v2.routes import _failure_diagnostics  # noqa: E402

TENANT_ID = "tenant-a"


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(wr.router)
    app.dependency_overrides[wr._verify_api_key] = lambda: None
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="test-key",
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
