"""HTTP-level regression tests for #2901 and #2902.

Both issues are about compliance signals that the v2 webhook ingest route
computes (or should compute) and then loses before they reach the database.
Both are only visible from the route: every pre-existing test for the helpers
involved calls them directly, which is exactly why the regressions survived.

#2902 — generated alerts were dropped by the batch path. ``_generate_alerts``
runs at ``routes.py:169`` and its result is carried in ``valid_events``, but
the dict handed to ``store_events_batch`` omitted the ``alerts`` key entirely,
so ``batch.py`` derived ``validation_status='valid'`` for every event and no
``fsma.compliance_alerts`` row was ever written on the happy path. The
per-event fallback (``routes.py:328``) passes ``alerts=alerts`` and does not
have the bug, so identical input produced different persisted state depending
on which internal path ran.

#2901 — ``_check_obligations`` had zero production call sites. The evaluator
for tenant-configured obligation-CTE rules was defined, exported and
unit-tested, but nothing in the request path invoked it, so DB-driven
obligation rules were never evaluated at ingest.

A *receiving* event is the realistic trigger for the alert half: FSMA requires
``receiving_location`` but not ``ship_from_location``, so a fully valid
receiving event passes ``_validate_event_kdes`` and still trips the
``incomplete_route`` check in ``_generate_alerts``.
"""

from __future__ import annotations

import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

import services.ingestion.app.webhook_router_v2 as wr  # noqa: E402
from services.ingestion.app.authz import IngestionPrincipal, get_ingestion_principal  # noqa: E402
from shared.database import get_db_session  # noqa: E402

TENANT = "tenant-a"
STORED_EVENT_ID = "00000000-0000-0000-0000-000000000001"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _receiving_event(**overrides) -> dict:
    """A receiving CTE with every *required* KDE present.

    It carries no ``ship_from_location`` / ``ship_from_gln``, which is legal
    (neither is required for receiving) but trips ``_generate_alerts``.
    """
    payload = {
        "cte_type": "receiving",
        "traceability_lot_code": "TLC-2026-RECV",
        "product_description": "Romaine Hearts",
        "quantity": 12.5,
        "unit_of_measure": "cases",
        "location_name": "Metro DC",
        "timestamp": _now_iso(),
        "kdes": {
            "receive_date": "2026-03-10",
            "receiving_location": "Metro DC",
            "immediate_previous_source": "Valley Fresh Farms",
            "reference_document": "PO-2026-111",
            "tlc_source_reference": "SRC-2026-111",
        },
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _StoreResult:
    def __init__(self, event_id: str = STORED_EVENT_ID):
        self.event_id = event_id
        self.sha256_hash = "a" * 64
        self.chain_hash = "b" * 64


class _FakeExecuteResult:
    def __init__(self, rows: list):
        self._rows = rows

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def scalar(self):
        return self._rows[0] if self._rows else 0


class _FakeNestedTxn:
    def __init__(self):
        self.committed = False
        self.rolled_back = False

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


class _RecordingSession:
    """Records every SQL statement; optionally serves obligation-rule rows."""

    def __init__(self, obligation_rows: Optional[list] = None):
        self.calls: list[tuple[str, dict]] = []
        self.committed = False
        self._obligation_rows = obligation_rows or []
        self._nested_ctx = _FakeNestedTxn()

    def begin_nested(self):
        return self._nested_ctx

    def execute(self, stmt, params=None):
        sql = str(getattr(stmt, "text", stmt))
        self.calls.append((sql, dict(params or {})))
        if "obligation_cte_rules" in sql:
            return _FakeExecuteResult(self._obligation_rows)
        return _FakeExecuteResult([])

    def commit(self):
        self.committed = True

    def rollback(self):
        pass

    def close(self):
        pass

    def sql_matching(self, needle: str) -> list[tuple[str, dict]]:
        return [(s, p) for s, p in self.calls if needle.lower() in s.lower()]


class _FakePersistence:
    def __init__(self, _session, *, batch_raises: Optional[Exception] = None):
        self.batch_calls: list[dict] = []
        self.store_calls: list[dict] = []
        self.batch_raises = batch_raises

    def store_events_batch(self, *, tenant_id, events, source):
        self.batch_calls.append({"tenant_id": tenant_id, "events": events, "source": source})
        if self.batch_raises is not None:
            raise self.batch_raises
        return [_StoreResult() for _ in events]

    def store_event(self, **kw):
        self.store_calls.append(kw)
        return _StoreResult()


def _install_stubs(monkeypatch, session, persistence):
    fake_db = types.ModuleType("shared.database")
    fake_db.SessionLocal = lambda: session
    fake_db.get_db_session = lambda: iter([session])
    monkeypatch.setitem(sys.modules, "shared.database", fake_db)

    fake_cte = types.ModuleType("shared.cte_persistence")
    fake_cte.CTEPersistence = lambda _s: persistence
    monkeypatch.setitem(sys.modules, "shared.cte_persistence", fake_cte)

    class _FakeCanonicalStore:
        def __init__(self, *_a, **_kw):
            pass

        def persist_event(self, *_a, **_kw):
            return None

    fake_canon = types.ModuleType("shared.canonical_persistence")
    fake_canon.CanonicalEventStore = _FakeCanonicalStore
    monkeypatch.setitem(sys.modules, "shared.canonical_persistence", fake_canon)

    class _FakeSummary:
        compliant = True

    class _FakeRulesEngine:
        def __init__(self, *_a, **_kw):
            pass

        def evaluate_event(self, *_a, **_kw):
            return _FakeSummary()

    fake_rules = types.ModuleType("shared.rules_engine")
    fake_rules.RulesEngine = _FakeRulesEngine
    monkeypatch.setitem(sys.modules, "shared.rules_engine", fake_rules)

    class _FakeExceptionQueue:
        def __init__(self, *_a, **_kw):
            pass

        def create_exceptions_from_evaluation(self, *_a, **_kw):
            return None

    fake_exc = types.ModuleType("shared.exception_queue")
    fake_exc.ExceptionQueueService = _FakeExceptionQueue
    monkeypatch.setitem(sys.modules, "shared.exception_queue", fake_exc)

    fake_catalog = types.ModuleType("services.ingestion.app.product_catalog")
    fake_catalog.learn_from_event = lambda **_kw: None
    monkeypatch.setitem(sys.modules, "services.ingestion.app.product_catalog", fake_catalog)

    class _FakeCanonical:
        def __init__(self, tlc: str):
            self.event_id = "canonical-evt"
            self.event_type = types.SimpleNamespace(value="receiving")
            self.traceability_lot_code = tlc
            self.product_reference = "prod-ref"
            self.quantity = 1.0
            self.unit_of_measure = "cases"
            self.from_facility_reference = None
            self.to_facility_reference = None
            self.from_entity_reference = None
            self.to_entity_reference = None
            self.kdes: dict[str, Any] = {}

        def prepare_for_persistence(self):
            return self

    monkeypatch.setattr(
        wr, "normalize_webhook_event", lambda event, tenant_id, **_: _FakeCanonical(event.traceability_lot_code)
    )
    monkeypatch.setattr(wr, "emit_funnel_event", lambda **_kw: None)
    monkeypatch.setattr(wr, "_publish_graph_sync", lambda *_a, **_kw: None)
    monkeypatch.setattr(wr, "consume_tenant_rate_limit", lambda **_kw: (True, 999))
    monkeypatch.setattr("services.ingestion.app.authz.consume_tenant_rate_limit", lambda **_kw: (True, 999))
    for var in ("API_KEY", "REGENGINE_API_KEY", "WEBHOOK_HMAC_SECRET"):
        monkeypatch.delenv(var, raising=False)


def _client(monkeypatch, *, session=None, batch_raises=None):
    session = session or _RecordingSession()
    persistence = _FakePersistence(session, batch_raises=batch_raises)
    _install_stubs(monkeypatch, session, persistence)

    app = FastAPI()
    app.include_router(wr.router)
    app.dependency_overrides[wr._verify_api_key] = lambda: None
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="test-key", scopes=["*"], tenant_id=TENANT, auth_mode="test"
    )
    from services.ingestion.app.subscription_gate import require_active_subscription

    app.dependency_overrides[require_active_subscription] = lambda: None

    def _override_db():
        yield session

    app.dependency_overrides[get_db_session] = _override_db
    return TestClient(app), session, persistence


def _post(client, events, key="idem-1"):
    return client.post(
        "/api/v1/webhooks/ingest",
        json={"source": "test", "tenant_id": TENANT, "events": events},
        headers={"Idempotency-Key": key},
    )


# ---------------------------------------------------------------------------
# #2902 — alerts must survive the trip into the batch writer
# ---------------------------------------------------------------------------


class TestBatchIngestCarriesAlerts_Issue2902:
    def test_generated_alerts_reach_store_events_batch(self):
        """A receiving event with no ship-from generates an incomplete_route
        alert; the batch dict must carry it.

        Pre-fix the ``alerts`` key is absent from the dict entirely, so
        ``batch.py`` reads ``[]`` and derives ``validation_status='valid'``.
        """
        monkeypatch = pytest.MonkeyPatch()
        try:
            client, _session, persistence = _client(monkeypatch)
            resp = _post(client, [_receiving_event()])
            assert resp.status_code == 200
            assert resp.json()["accepted"] == 1

            assert persistence.batch_calls, "batch path should have run"
            evt = persistence.batch_calls[0]["events"][0]
            assert "alerts" in evt, (
                "batch dict must carry the 'alerts' key — without it "
                "store_events_batch derives validation_status='valid' for "
                "every event and writes no compliance_alerts row"
            )
            assert any(
                a.get("alert_type") == "incomplete_route" for a in evt["alerts"]
            ), f"expected the incomplete_route alert, got {evt['alerts']!r}"
        finally:
            monkeypatch.undo()

    def test_batch_and_fallback_paths_agree_on_alerts(self):
        """Parity: the same event through either path must carry the same alerts.

        The fallback runs only when the batch INSERT raises. Before the fix the
        two paths disagreed — the fallback passed ``alerts=alerts`` while the
        batch dropped them — so identical input produced different
        ``validation_status`` and a missing alert row.
        """
        monkeypatch = pytest.MonkeyPatch()
        try:
            client, _session, persistence = _client(monkeypatch)
            _post(client, [_receiving_event()], key="idem-batch")
            batch_alerts = persistence.batch_calls[0]["events"][0].get("alerts")
        finally:
            monkeypatch.undo()

        monkeypatch = pytest.MonkeyPatch()
        try:
            client, _session, persistence = _client(
                monkeypatch, batch_raises=RuntimeError("batch INSERT blew up")
            )
            _post(client, [_receiving_event()], key="idem-fallback")
            assert persistence.store_calls, "fallback path should have run"
            fallback_alerts = persistence.store_calls[0].get("alerts")
        finally:
            monkeypatch.undo()

        assert batch_alerts == fallback_alerts, (
            "batch and per-event fallback must persist identical alerts for "
            f"identical input; batch={batch_alerts!r} fallback={fallback_alerts!r}"
        )

    def test_clean_event_carries_an_empty_alert_list_not_a_missing_key(self):
        """Fail loud, not silent: the key is always present, even when empty.

        A missing key is indistinguishable from 'no alerts' inside the writer,
        which is precisely how this defect stayed invisible.
        """
        monkeypatch = pytest.MonkeyPatch()
        try:
            client, _session, persistence = _client(monkeypatch)
            clean = _receiving_event()
            clean["kdes"]["ship_from_location"] = "Valley Fresh Farms"
            _post(client, [clean])
            evt = persistence.batch_calls[0]["events"][0]
            assert evt.get("alerts") == []
        finally:
            monkeypatch.undo()


# ---------------------------------------------------------------------------
# #2901 — the obligation evaluator must actually run on the ingest path
# ---------------------------------------------------------------------------

# (rule_id, obligation_id, cte_type, required_kde_key, validation_rule,
#  description, obligation_text, risk_category)
_OBLIGATION_RULE_VIOLATED = (
    "rule-1",
    "11111111-1111-1111-1111-111111111111",
    "receiving",
    "cold_chain_log",
    "present",
    "Cold chain log required on receipt",
    "Receiver must retain a cold-chain log for each received lot",
    "CRITICAL",
)


class TestObligationCheckRunsOnIngest_Issue2901:
    def test_check_obligations_is_called_from_the_request_path(self):
        """The evaluator must be invoked with the *persisted* event id.

        Pre-fix this fails outright — ``_check_obligations`` has no production
        call site, so the recorder never fires.
        """
        monkeypatch = pytest.MonkeyPatch()
        try:
            client, _session, _persistence = _client(monkeypatch)
            seen: list[tuple] = []
            monkeypatch.setattr(
                wr,
                "_check_obligations",
                lambda db, event, event_id, tenant_id: seen.append(
                    (event.traceability_lot_code, event_id, tenant_id)
                )
                or [],
            )
            resp = _post(client, [_receiving_event()])
            assert resp.status_code == 200

            assert seen, (
                "_check_obligations must be called from the ingest request "
                "path — tenant-configured obligation rules are otherwise "
                "never evaluated"
            )
            tlc, event_id, tenant_id = seen[0]
            assert tlc == "TLC-2026-RECV"
            assert event_id == STORED_EVENT_ID, (
                "the obligation check must receive the id of the row that was "
                "actually persisted, so its compliance_alerts row points at a "
                "real event"
            )
            assert tenant_id == TENANT
        finally:
            monkeypatch.undo()

    def test_violated_obligation_writes_a_compliance_alert_row(self):
        """End-to-end through HTTP: seeded rule + missing KDE → alert row.

        This is the acceptance criterion for #2901 — it exercises the route,
        not the helper, with the real ``_check_obligations`` in place.
        """
        monkeypatch = pytest.MonkeyPatch()
        try:
            session = _RecordingSession(obligation_rows=[_OBLIGATION_RULE_VIOLATED])
            client, session, _persistence = _client(monkeypatch, session=session)
            resp = _post(client, [_receiving_event()])
            assert resp.status_code == 200
            assert resp.json()["accepted"] == 1

            assert session.sql_matching("FROM obligation_cte_rules"), (
                "the ingest path never queried obligation_cte_rules"
            )
            alert_inserts = session.sql_matching("INSERT INTO fsma.compliance_alerts")
            assert alert_inserts, (
                "a violated obligation must produce an fsma.compliance_alerts "
                "row — compliance_score.py counts these as open obligation gaps"
            )
            params = alert_inserts[0][1]
            assert params["eid"] == STORED_EVENT_ID
            assert params["sev"] == "critical"
            assert params["atype"] == "chain_break"
            assert "cold_chain_log" in params["msg"]
        finally:
            monkeypatch.undo()

    def test_satisfied_obligation_writes_no_alert(self):
        """No false positives: a satisfied rule must stay silent."""
        monkeypatch = pytest.MonkeyPatch()
        try:
            session = _RecordingSession(obligation_rows=[_OBLIGATION_RULE_VIOLATED])
            client, session, _persistence = _client(monkeypatch, session=session)
            event = _receiving_event()
            event["kdes"]["cold_chain_log"] = "CCL-2026-0042"
            resp = _post(client, [event])
            assert resp.status_code == 200
            assert session.sql_matching("INSERT INTO fsma.compliance_alerts") == []
        finally:
            monkeypatch.undo()

    def test_obligation_check_also_runs_on_the_per_event_fallback(self):
        """The fallback path must not be a hole in obligation coverage.

        Batch and fallback have already diverged once on alert persistence
        (#2902); the obligation check must be wired into both.
        """
        monkeypatch = pytest.MonkeyPatch()
        try:
            client, _session, persistence = _client(
                monkeypatch, batch_raises=RuntimeError("batch INSERT blew up")
            )
            seen: list[str] = []
            monkeypatch.setattr(
                wr,
                "_check_obligations",
                lambda db, event, event_id, tenant_id: seen.append(event_id) or [],
            )
            resp = _post(client, [_receiving_event()])
            assert resp.status_code == 200
            assert persistence.store_calls, "fallback path should have run"
            assert seen == [STORED_EVENT_ID], (
                "the per-event fallback must run the obligation check too"
            )
        finally:
            monkeypatch.undo()

    def test_failed_alert_write_rolls_back_to_a_savepoint(self):
        """A failing alert INSERT must not poison the ingest transaction.

        ``_check_obligations`` runs inside the request transaction. On Postgres
        a failed statement aborts the whole transaction, so catching the
        exception without rolling back to a savepoint would turn a benign
        alert-write failure into the loss of every event in the batch at
        commit time. Wiring this check back in is only safe with the guard.
        """
        monkeypatch = pytest.MonkeyPatch()
        try:

            class _AlertInsertFails(_RecordingSession):
                def execute(self, stmt, params=None):
                    sql = str(getattr(stmt, "text", stmt))
                    if "INSERT INTO fsma.compliance_alerts" in sql:
                        self.calls.append((sql, dict(params or {})))
                        raise RuntimeError("alert insert exploded")
                    return super().execute(stmt, params)

            session = _AlertInsertFails(obligation_rows=[_OBLIGATION_RULE_VIOLATED])
            client, session, _persistence = _client(monkeypatch, session=session)
            resp = _post(client, [_receiving_event()])

            # The event still lands and the request still succeeds.
            assert resp.status_code == 200
            assert resp.json()["accepted"] == 1
            assert session.committed is True
            assert session._nested_ctx.rolled_back is True, (
                "a failed compliance_alerts INSERT must roll back to its "
                "savepoint, or the outer transaction is left aborted"
            )
        finally:
            monkeypatch.undo()

    def test_obligation_failure_does_not_reject_the_event(self):
        """An obligation gap is a detection signal, not an ingest gate.

        ``_check_obligations`` emits ``severity='critical'`` for CRITICAL-risk
        obligations, and ``core._REJECT_SEVERITIES`` contains ``'critical'``.
        Feeding these alerts into the pre-persist list would silently turn
        accepted events into ``validation_status='rejected'`` — a far larger
        behavior change than restoring the missing call. The event stays
        accepted; the alert is what carries the signal.
        """
        monkeypatch = pytest.MonkeyPatch()
        try:
            session = _RecordingSession(obligation_rows=[_OBLIGATION_RULE_VIOLATED])
            client, session, persistence = _client(monkeypatch, session=session)
            resp = _post(client, [_receiving_event()])

            assert resp.status_code == 200
            body = resp.json()
            assert body["accepted"] == 1
            assert body["rejected"] == 0

            batch_alerts = persistence.batch_calls[0]["events"][0].get("alerts", [])
            assert all(a.get("severity") != "critical" for a in batch_alerts), (
                "obligation alerts must not be folded into the pre-persist "
                "alert list — that would flip validation_status to 'rejected'"
            )
        finally:
            monkeypatch.undo()
