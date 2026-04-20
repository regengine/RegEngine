"""Coverage sweep for ``services/ingestion/app/webhook_router_v2.py``.

Targets every branch of the module — from small helpers (``_verify_api_key``,
``_check_rate_limit``, replay-window classification, Redis sync counters)
up through the full ``/api/v1/webhooks/ingest`` pipeline with DB-backed
persistence, obligation checks, canonical mirroring, rules engine,
exception queue, graph sync, and product-catalog learning all stubbed
so the test runs offline.

The file avoids patching the real ``shared.database`` / ``shared.cte_persistence``
/ ``shared.canonical_persistence`` modules. Instead, we install fake
submodules into ``sys.modules`` for the lifetime of each test via
``monkeypatch.setitem`` — the router's ``from shared.X import Y`` lookups
then resolve against our fakes on first call.

See #1342 for the overall coverage sweep plan.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

import app.webhook_router_v2 as wr
from app.authz import IngestionPrincipal, get_ingestion_principal
from app.webhook_models import IngestEvent, WebhookCTEType, WebhookPayload
from shared.database import get_db_session


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_shipping_event(
    *,
    tlc: str = "TLC-2026-ABC",
    timestamp: Optional[str] = None,
    include_kdes: bool = True,
) -> dict:
    """Return a shipping-CTE dict accepted by ``IngestEvent``."""
    payload = {
        "cte_type": "shipping",
        "traceability_lot_code": tlc,
        "product_description": "Romaine Hearts",
        "quantity": 12.5,
        "unit_of_measure": "cases",
        "location_gln": None,
        "location_name": "Valley Fresh Farms",
        "timestamp": timestamp or _now_iso(),
        "kdes": {},
    }
    if include_kdes:
        payload["kdes"] = {
            "ship_date": "2026-03-10",
            "ship_from_location": "Valley Fresh Farms",
            "ship_to_location": "Metro DC",
            "reference_document": "PO-2026-111",
            "tlc_source_reference": "SRC-2026-111",
        }
    return payload


class _StoreResult:
    def __init__(self, event_id: str = "evt-new", sha: str = "a" * 64, chain: str = "b" * 64):
        self.event_id = event_id
        self.sha256_hash = sha
        self.chain_hash = chain


class _FakeChainVerification:
    def __init__(self, valid: bool = True):
        self.valid = valid
        self.chain_length = 3
        self.errors: list[str] = []
        self.checked_at = "2026-03-10T10:00:00+00:00"


class _FakePersistence:
    """CTE persistence stub — records batch / per-event calls."""

    def __init__(
        self,
        _session,
        *,
        batch_raises: Optional[Exception] = None,
        store_raises: Optional[Exception] = None,
    ):
        self._session = _session
        self.batch_calls: list[dict] = []
        self.store_calls: list[dict] = []
        self.batch_raises = batch_raises
        self.store_raises = store_raises

    def store_events_batch(self, *, tenant_id, events, source):
        self.batch_calls.append({"tenant_id": tenant_id, "events": events, "source": source})
        if self.batch_raises is not None:
            raise self.batch_raises
        return [
            _StoreResult(event_id=f"evt-{i}", sha="a" * 64, chain="b" * 64)
            for i, _ in enumerate(events)
        ]

    def store_event(self, *, tenant_id, event_type, traceability_lot_code, **_kw):
        self.store_calls.append(
            {"tenant_id": tenant_id, "event_type": event_type, "tlc": traceability_lot_code}
        )
        if self.store_raises is not None:
            raise self.store_raises
        return _StoreResult(event_id=f"evt-{traceability_lot_code}")

    def verify_chain(self, tenant_id: str):
        _ = tenant_id
        return _FakeChainVerification(valid=True)


class _FakeSession:
    """Just enough ``Session`` API for the ingest/verify handlers."""

    def __init__(self):
        self.committed = False
        self.rolled_back = False
        self.closed = False
        self._nested_ctx = _FakeNestedTxn()
        self._exec_queue: list[Any] = []

    def begin_nested(self):
        return self._nested_ctx

    def execute(self, *args, **kwargs):
        return _FakeExecuteResult([])

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


class _FakeNestedTxn:
    def __init__(self):
        self.rolled_back = False

    def rollback(self):
        self.rolled_back = True


class _FakeExecuteResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def scalar(self):
        return self._rows[0] if self._rows else 0


def _install_shared_stubs(
    monkeypatch: pytest.MonkeyPatch,
    *,
    session: Optional[_FakeSession] = None,
    persistence: Optional[_FakePersistence] = None,
) -> tuple[_FakeSession, _FakePersistence]:
    """Install fake ``shared.database`` / ``shared.cte_persistence`` /
    ``shared.canonical_persistence`` / ``shared.rules_engine`` /
    ``shared.exception_queue`` / ``app.product_catalog`` so the real DB
    imports don't fire during the test.
    """
    session = session or _FakeSession()
    persistence = persistence or _FakePersistence(session)

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

    fake_catalog = types.ModuleType("app.product_catalog")
    fake_catalog.learn_from_event = lambda **_kw: None
    monkeypatch.setitem(sys.modules, "app.product_catalog", fake_catalog)

    # The router looks up ``normalize_webhook_event`` via the already-imported
    # module reference, so patching ``wr.normalize_webhook_event`` is enough.
    class _FakeCanonical:
        def __init__(self, tlc: str):
            self.event_id = "canonical-evt"
            self.event_type = types.SimpleNamespace(value="shipping")
            self.traceability_lot_code = tlc
            self.product_reference = "prod-ref"
            self.quantity = 1.0
            self.unit_of_measure = "cases"
            self.from_facility_reference = None
            self.to_facility_reference = None
            self.from_entity_reference = None
            self.to_entity_reference = None
            self.kdes = {}

    monkeypatch.setattr(
        wr, "normalize_webhook_event", lambda event, tenant_id: _FakeCanonical(event.traceability_lot_code)
    )
    monkeypatch.setattr(wr, "emit_funnel_event", lambda **_kw: None)

    return session, persistence


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(wr.router)
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="test-key",
        scopes=["*"],
        tenant_id=None,
        auth_mode="test",
    )
    from app.subscription_gate import require_active_subscription
    app.dependency_overrides[require_active_subscription] = lambda: None
    return app


def _client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    session: Optional[_FakeSession] = None,
    persistence: Optional[_FakePersistence] = None,
) -> tuple[TestClient, _FakeSession, _FakePersistence]:
    session, persistence = _install_shared_stubs(
        monkeypatch, session=session, persistence=persistence
    )
    # Defang rate limiting everywhere it matters.
    monkeypatch.setattr(wr, "consume_tenant_rate_limit", lambda **_kw: (True, 999))
    monkeypatch.setattr("app.authz.consume_tenant_rate_limit", lambda **_kw: (True, 999))
    # No API-key gate.
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("WEBHOOK_HMAC_SECRET", raising=False)

    app = _build_app()

    # Override the DB-session dependency with our fake.
    def _override_db():
        yield session
    app.dependency_overrides[get_db_session] = _override_db
    return TestClient(app), session, persistence


# ---------------------------------------------------------------------------
# Small helpers: _is_production, _verify_api_key, _get_persistence
# ---------------------------------------------------------------------------


class TestSmallHelpers:
    def test_is_production_true(self, monkeypatch):
        monkeypatch.setenv("REGENGINE_ENV", "production")
        assert wr._is_production() is True

    def test_is_production_false(self, monkeypatch):
        monkeypatch.delenv("REGENGINE_ENV", raising=False)
        monkeypatch.delenv("ENV", raising=False)
        monkeypatch.delenv("DATABASE_URL", raising=False)
        assert wr._is_production() is False

    def test_verify_api_key_accepts_matching_key(self, monkeypatch):
        class _S:
            api_key = "correct-key"

        monkeypatch.setattr(wr, "get_settings", lambda: _S())
        wr._verify_api_key("correct-key")  # must not raise

    def test_verify_api_key_rejects_mismatch(self, monkeypatch):
        class _S:
            api_key = "correct-key"

        monkeypatch.setattr(wr, "get_settings", lambda: _S())
        with pytest.raises(Exception) as exc:
            wr._verify_api_key("wrong-key")
        assert "401" in str(exc.value) or "Invalid" in str(exc.value.detail)

    def test_verify_api_key_no_configured_key_non_prod_ok(self, monkeypatch):
        class _S:
            api_key = None

        monkeypatch.setattr(wr, "get_settings", lambda: _S())
        monkeypatch.setattr(wr, "_is_production", lambda: False)
        wr._verify_api_key(None)  # no raise

    def test_verify_api_key_production_without_configured_key_rejects(self, monkeypatch):
        class _S:
            api_key = None

        monkeypatch.setattr(wr, "get_settings", lambda: _S())
        monkeypatch.setattr(wr, "_is_production", lambda: True)
        with pytest.raises(Exception) as exc:
            wr._verify_api_key(None)
        assert exc.value.status_code == 401

    def test_get_persistence_none_session_returns_none(self):
        assert wr._get_persistence(None) is None

    def test_get_persistence_happy_path(self, monkeypatch):
        fake_cte = types.ModuleType("shared.cte_persistence")
        fake_cte.CTEPersistence = lambda s: ("p", s)
        monkeypatch.setitem(sys.modules, "shared.cte_persistence", fake_cte)
        result = wr._get_persistence("session-x")
        assert result == ("p", "session-x")

    def test_get_persistence_importerror_returns_none(self, monkeypatch):
        # Force the import inside _get_persistence to raise ImportError
        original_cte = sys.modules.get("shared.cte_persistence")
        monkeypatch.setitem(sys.modules, "shared.cte_persistence", None)
        try:
            assert wr._get_persistence("session-x") is None
        finally:
            if original_cte is not None:
                sys.modules["shared.cte_persistence"] = original_cte


# ---------------------------------------------------------------------------
# Env helpers — _max_event_age_days / _max_event_future_hours
# ---------------------------------------------------------------------------


class TestReplayWindowEnvHelpers:
    def test_max_event_age_days_default(self, monkeypatch):
        monkeypatch.delenv("WEBHOOK_MAX_EVENT_AGE_DAYS", raising=False)
        assert wr._max_event_age_days() == 90

    def test_max_event_age_days_override(self, monkeypatch):
        monkeypatch.setenv("WEBHOOK_MAX_EVENT_AGE_DAYS", "7")
        assert wr._max_event_age_days() == 7

    def test_max_event_age_days_invalid_falls_back(self, monkeypatch):
        monkeypatch.setenv("WEBHOOK_MAX_EVENT_AGE_DAYS", "not-a-number")
        assert wr._max_event_age_days() == 90

    def test_max_event_future_hours_default(self, monkeypatch):
        monkeypatch.delenv("WEBHOOK_MAX_EVENT_FUTURE_HOURS", raising=False)
        assert wr._max_event_future_hours() == 24

    def test_max_event_future_hours_invalid_falls_back(self, monkeypatch):
        monkeypatch.setenv("WEBHOOK_MAX_EVENT_FUTURE_HOURS", "bogus")
        assert wr._max_event_future_hours() == 24

    def test_validate_event_timestamp_window_naive_tz_is_treated_as_utc(self):
        """A naive (no-tz) timestamp is coerced to UTC and accepted when fresh."""
        naive_now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        assert wr._validate_event_timestamp_window(naive_now) is None


# ---------------------------------------------------------------------------
# Replay-rejection metric — _classify_replay_rejection / _record_replay_rejection
# ---------------------------------------------------------------------------


class TestReplayMetricClassification:
    def test_unparseable_timestamp_classified(self):
        assert wr._classify_replay_rejection("not-a-timestamp") == ("unparseable", "na")

    def test_future_lt_48h(self):
        ts = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        reason, bucket = wr._classify_replay_rejection(ts)
        assert reason == "future"
        assert bucket == "lt_48h"

    def test_future_lt_30d(self):
        ts = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
        reason, bucket = wr._classify_replay_rejection(ts)
        assert reason == "future"
        assert bucket == "lt_30d"

    def test_future_gte_30d(self):
        ts = (datetime.now(timezone.utc) + timedelta(days=60)).isoformat()
        reason, bucket = wr._classify_replay_rejection(ts)
        assert reason == "future"
        assert bucket == "gte_30d"

    def test_stale_lt_180d(self):
        ts = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        reason, bucket = wr._classify_replay_rejection(ts)
        assert reason == "stale"
        assert bucket == "lt_180d"

    def test_stale_lt_1y(self):
        ts = (datetime.now(timezone.utc) - timedelta(days=300)).isoformat()
        reason, bucket = wr._classify_replay_rejection(ts)
        assert reason == "stale"
        assert bucket == "lt_1y"

    def test_stale_gte_1y(self):
        ts = (datetime.now(timezone.utc) - timedelta(days=500)).isoformat()
        reason, bucket = wr._classify_replay_rejection(ts)
        assert reason == "stale"
        assert bucket == "gte_1y"

    def test_classify_naive_timestamp_is_treated_as_utc(self):
        naive = (datetime.now(timezone.utc) + timedelta(hours=2)).replace(tzinfo=None).isoformat()
        reason, _bucket = wr._classify_replay_rejection(naive)
        assert reason == "future"

    def test_record_replay_rejection_no_op_when_disabled(self, monkeypatch):
        """When metrics are disabled the helper returns silently."""
        monkeypatch.setattr(wr, "_WEBHOOK_METRICS_ENABLED", False)
        wr._record_replay_rejection("not-a-timestamp")  # no raise

    def test_record_replay_rejection_records_when_enabled(self, monkeypatch):
        calls: list[dict] = []

        class _FakeCounter:
            def labels(self, **kw):
                calls.append(kw)
                return self

            def inc(self):
                calls.append({"_inc": True})

        monkeypatch.setattr(wr, "_WEBHOOK_METRICS_ENABLED", True)
        monkeypatch.setattr(wr, "WEBHOOK_REPLAY_REJECTED", _FakeCounter())
        wr._record_replay_rejection("not-a-timestamp")
        assert any("reason" in c for c in calls)


# ---------------------------------------------------------------------------
# Rate limiting helper
# ---------------------------------------------------------------------------


class TestCheckRateLimit:
    def test_allow_records_remaining(self, monkeypatch):
        captured = {}

        def _allow(**kw):
            captured.update(kw)
            return True, 12

        monkeypatch.setattr(wr, "consume_tenant_rate_limit", _allow)
        wr._check_rate_limit("tenant-x")
        assert captured["tenant_id"] == "tenant-x"
        assert captured["bucket_suffix"] == "webhooks.ingest"

    def test_block_raises_429(self, monkeypatch):
        monkeypatch.setattr(
            wr, "consume_tenant_rate_limit", lambda **kw: (False, 0)
        )
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            wr._check_rate_limit("tenant-x")
        assert exc.value.status_code == 429


# ---------------------------------------------------------------------------
# KDE validation
# ---------------------------------------------------------------------------


class TestValidateEventKdes:
    def test_all_required_present_no_errors(self):
        event = IngestEvent(**_make_shipping_event())
        assert wr._validate_event_kdes(event) == []

    def test_missing_required_kde_reported(self):
        data = _make_shipping_event()
        data["kdes"].pop("ship_to_location")
        event = IngestEvent(**data)
        errors = wr._validate_event_kdes(event)
        assert any("ship_to_location" in e for e in errors)

    def test_empty_string_counts_as_missing(self):
        data = _make_shipping_event()
        data["kdes"]["ship_from_location"] = "   "
        event = IngestEvent(**data)
        errors = wr._validate_event_kdes(event)
        assert any("ship_from_location" in e for e in errors)


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------


class TestGenerateAlerts:
    def test_shipping_event_missing_route_emits_alert(self):
        data = _make_shipping_event()
        data["kdes"].pop("ship_from_location")
        event = IngestEvent(**data)
        alerts = wr._generate_alerts(event)
        assert any(a["alert_type"] == "incomplete_route" for a in alerts)

    def test_shipping_event_with_full_route_no_alert(self):
        event = IngestEvent(**_make_shipping_event())
        assert wr._generate_alerts(event) == []

    def test_non_shipping_event_returns_empty(self):
        data = _make_shipping_event()
        data["cte_type"] = "harvesting"
        data["kdes"] = {
            "harvest_date": "2026-03-10",
            "reference_document": "HD-1",
        }
        event = IngestEvent(**data)
        assert wr._generate_alerts(event) == []


# ---------------------------------------------------------------------------
# Obligation checks
# ---------------------------------------------------------------------------


class TestCheckObligations:
    def _event(self, **overrides) -> IngestEvent:
        data = _make_shipping_event()
        data.update(overrides)
        return IngestEvent(**data)

    def test_no_session_returns_empty(self):
        assert wr._check_obligations(None, self._event(), "evt-1", "tenant-a") == []

    def test_no_rows_returns_empty(self):
        s = _FakeSession()
        result = wr._check_obligations(s, self._event(), "evt-1", "tenant-a")
        assert result == []

    def test_nested_query_failure_rolls_back_and_returns_empty(self):
        class _FailingExecSession(_FakeSession):
            def __init__(self):
                super().__init__()
                self.calls = 0

            def execute(self, *a, **kw):
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("bad UUID cast")
                return _FakeExecuteResult([])

        s = _FailingExecSession()
        assert wr._check_obligations(s, self._event(), "evt-1", "tenant-a") == []
        assert s._nested_ctx.rolled_back is True

    def test_validation_rule_present_passes(self):
        """A rule requiring a present KDE passes when the KDE is there."""

        class _RulesSession(_FakeSession):
            def execute(self, *a, **kw):
                rows = [
                    (
                        "rule-1", "obl-1", "shipping", "ship_to_location",
                        "present", "desc", "Ship-to required", "LOW",
                    )
                ]
                return _FakeExecuteResult(rows)

        alerts = wr._check_obligations(_RulesSession(), self._event(), "evt-1", "tenant-a")
        assert alerts == []

    def test_validation_rule_present_fails_and_writes_alert(self):
        """Missing KDE → critical alert + INSERT into compliance_alerts."""
        inserts: list[str] = []

        class _RulesSession(_FakeSession):
            def __init__(self):
                super().__init__()
                self._first = True

            def execute(self, stmt, params=None):
                sql = str(stmt).lower() if hasattr(stmt, "__str__") else ""
                if "insert into fsma.compliance_alerts" in sql:
                    inserts.append(sql)
                    return _FakeExecuteResult([])
                if self._first:
                    self._first = False
                    rows = [
                        (
                            "rule-1", "obl-1", "shipping", "ship_to_location",
                            "present", "desc", "Ship-to required", "CRITICAL",
                        )
                    ]
                    return _FakeExecuteResult(rows)
                return _FakeExecuteResult([])

        data = _make_shipping_event()
        data["kdes"].pop("ship_to_location")
        alerts = wr._check_obligations(
            _RulesSession(), IngestEvent(**data), "evt-1", "tenant-a"
        )
        assert alerts and alerts[0]["severity"] == "critical"
        assert inserts  # the INSERT was executed

    def test_tlc_assigned_rule(self):
        class _RulesSession(_FakeSession):
            def execute(self, *a, **kw):
                rows = [
                    (
                        "rule-1", "obl-1", "shipping", None,
                        "tlc_assigned", "desc", "TLC must exist", "LOW",
                    )
                ]
                return _FakeExecuteResult(rows)

        alerts = wr._check_obligations(_RulesSession(), self._event(), "evt-1", "tenant-a")
        assert alerts == []

    def test_tlc_not_reassigned_shipping_without_prior_fails(self):
        class _RulesSession(_FakeSession):
            def __init__(self):
                super().__init__()
                self._rules_served = False

            def execute(self, stmt, params=None):
                sql = str(stmt).lower()
                if not self._rules_served:
                    self._rules_served = True
                    rows = [
                        (
                            "rule-1", "obl-1", "shipping", None,
                            "tlc_not_reassigned", "desc", "No reassign", "LOW",
                        )
                    ]
                    return _FakeExecuteResult(rows)
                if "count(*) from fsma.cte_events" in sql:
                    return _FakeExecuteResult([0])
                if "insert into fsma.compliance_alerts" in sql:
                    return _FakeExecuteResult([])
                return _FakeExecuteResult([])

        alerts = wr._check_obligations(_RulesSession(), self._event(), "evt-1", "tenant-a")
        assert alerts and alerts[0]["severity"] == "warning"

    def test_tlc_not_reassigned_non_shipping_passes(self):
        class _RulesSession(_FakeSession):
            def execute(self, *a, **kw):
                rows = [
                    (
                        "rule-1", "obl-1", "all", None,
                        "tlc_not_reassigned", "desc", "No reassign", "LOW",
                    )
                ]
                return _FakeExecuteResult(rows)

        data = _make_shipping_event()
        data["cte_type"] = "harvesting"
        data["kdes"] = {"harvest_date": "2026-03-10", "reference_document": "HD"}
        alerts = wr._check_obligations(
            _RulesSession(), IngestEvent(**data), "evt-1", "tenant-a"
        )
        assert alerts == []

    def test_downstream_transmitted_receiving_with_source_passes(self):
        class _RulesSession(_FakeSession):
            def execute(self, *a, **kw):
                rows = [
                    (
                        "rule-1", "obl-1", "receiving", None,
                        "downstream_transmitted", "desc", "Upstream ok", "LOW",
                    )
                ]
                return _FakeExecuteResult(rows)

        data = _make_shipping_event()
        data["cte_type"] = "receiving"
        data["kdes"] = {
            "receive_date": "2026-03-10",
            "receiving_location": "Metro DC",
            "immediate_previous_source": "Upstream Farm",
            "reference_document": "PO-1",
            "tlc_source_reference": "SRC-1",
            "ship_from_location": "Upstream Farm",
        }
        alerts = wr._check_obligations(
            _RulesSession(), IngestEvent(**data), "evt-1", "tenant-a"
        )
        assert alerts == []

    def test_downstream_transmitted_shipping_with_dest_passes(self):
        class _RulesSession(_FakeSession):
            def execute(self, *a, **kw):
                rows = [
                    (
                        "rule-1", "obl-1", "shipping", None,
                        "downstream_transmitted", "desc", "Dest ok", "LOW",
                    )
                ]
                return _FakeExecuteResult(rows)

        alerts = wr._check_obligations(_RulesSession(), self._event(), "evt-1", "tenant-a")
        assert alerts == []

    def test_downstream_transmitted_non_routing_cte_passes(self):
        class _RulesSession(_FakeSession):
            def execute(self, *a, **kw):
                rows = [
                    (
                        "rule-1", "obl-1", "all", None,
                        "downstream_transmitted", "desc", "N/A", "LOW",
                    )
                ]
                return _FakeExecuteResult(rows)

        data = _make_shipping_event()
        data["cte_type"] = "harvesting"
        data["kdes"] = {"harvest_date": "2026-03-10", "reference_document": "HD"}
        alerts = wr._check_obligations(
            _RulesSession(), IngestEvent(**data), "evt-1", "tenant-a"
        )
        assert alerts == []

    def test_record_exists_rule_always_passes(self):
        class _RulesSession(_FakeSession):
            def __init__(self):
                super().__init__()
                self._first = True

            def execute(self, *a, **kw):
                if self._first:
                    self._first = False
                    rows = [
                        (
                            "rule-1", "obl-1", "shipping", None,
                            "record_exists", "desc", "Chain ok", "LOW",
                        )
                    ]
                    return _FakeExecuteResult(rows)
                return _FakeExecuteResult([3])

        alerts = wr._check_obligations(_RulesSession(), self._event(), "evt-1", "tenant-a")
        assert alerts == []

    def test_alert_insert_failure_logged_not_raised(self, monkeypatch):
        class _RulesSession(_FakeSession):
            def __init__(self):
                super().__init__()
                self._rules_served = False

            def execute(self, stmt, params=None):
                sql = str(stmt).lower()
                if not self._rules_served:
                    self._rules_served = True
                    rows = [
                        (
                            "rule-1", "obl-1", "shipping", "ship_to_location",
                            "present", "desc", "Need ship-to", "LOW",
                        )
                    ]
                    return _FakeExecuteResult(rows)
                if "insert into fsma.compliance_alerts" in sql:
                    raise ValueError("INSERT failed")
                return _FakeExecuteResult([])

        data = _make_shipping_event()
        data["kdes"].pop("ship_to_location")
        alerts = wr._check_obligations(
            _RulesSession(), IngestEvent(**data), "evt-1", "tenant-a"
        )
        assert alerts and alerts[0]["severity"] == "warning"

    def test_outer_exception_returns_empty(self, monkeypatch):
        class _BoomSession(_FakeSession):
            def begin_nested(self):
                raise RuntimeError("savepoint unsupported")

        assert wr._check_obligations(_BoomSession(), self._event(), "evt-1", "tenant-a") == []


# ---------------------------------------------------------------------------
# Redis / graph sync helpers
# ---------------------------------------------------------------------------


class TestRedisHelpers:
    def test_get_redis_client_error_returns_none(self, monkeypatch):
        """redis.from_url raising → None."""
        fake_redis = types.ModuleType("redis")

        def _boom(*a, **kw):
            raise ConnectionError("no redis")

        fake_redis.from_url = _boom
        monkeypatch.setitem(sys.modules, "redis", fake_redis)
        assert wr._get_redis_client() is None

    def test_get_redis_client_success(self, monkeypatch):
        fake_redis = types.ModuleType("redis")
        fake_redis.from_url = lambda *a, **kw: "client-x"
        monkeypatch.setitem(sys.modules, "redis", fake_redis)
        assert wr._get_redis_client() == "client-x"

    def test_incr_sync_counter_uses_redis_when_available(self, monkeypatch):
        captured: list[str] = []

        class _RedisClient:
            def incr(self, key):
                captured.append(key)

        monkeypatch.setattr(wr, "_get_redis_client", lambda: _RedisClient())
        wr._incr_sync_counter("successes")
        assert captured == [f"{wr._SYNC_COUNTER_PREFIX}:successes"]

    def test_incr_sync_counter_falls_back_on_failures_key(self, monkeypatch):
        monkeypatch.setattr(wr, "_get_redis_client", lambda: None)
        before = wr._graph_sync_failures
        wr._incr_sync_counter("failures")
        assert wr._graph_sync_failures == before + 1

    def test_incr_sync_counter_falls_back_on_successes_key(self, monkeypatch):
        monkeypatch.setattr(wr, "_get_redis_client", lambda: None)
        before = wr._graph_sync_successes
        wr._incr_sync_counter("successes")
        assert wr._graph_sync_successes == before + 1

    def test_incr_sync_counter_redis_raise_falls_back(self, monkeypatch):
        class _FlakyClient:
            def incr(self, key):
                raise RuntimeError("redis hiccup")

        monkeypatch.setattr(wr, "_get_redis_client", lambda: _FlakyClient())
        before = wr._graph_sync_successes
        wr._incr_sync_counter("successes")
        assert wr._graph_sync_successes == before + 1

    def test_get_graph_sync_stats_reads_from_redis(self, monkeypatch):
        class _RedisClient:
            def get(self, key):
                return "5" if key.endswith(":successes") else "1"

        monkeypatch.setattr(wr, "_get_redis_client", lambda: _RedisClient())
        stats = wr.get_graph_sync_stats()
        assert stats == {"successes": 5, "failures": 1}

    def test_get_graph_sync_stats_redis_none_returns_in_memory(self, monkeypatch):
        monkeypatch.setattr(wr, "_get_redis_client", lambda: None)
        stats = wr.get_graph_sync_stats()
        assert "successes" in stats and "failures" in stats

    def test_get_graph_sync_stats_redis_raises_returns_in_memory(self, monkeypatch):
        class _BrokenClient:
            def get(self, key):
                raise RuntimeError("broken redis")

        monkeypatch.setattr(wr, "_get_redis_client", lambda: _BrokenClient())
        stats = wr.get_graph_sync_stats()
        assert "successes" in stats

    def test_publish_graph_sync_no_redis_url_is_noop(self, monkeypatch):
        # Even with the producer opted in, missing REDIS_URL must short-circuit.
        monkeypatch.setenv("ENABLE_NEO4J_SYNC", "true")
        monkeypatch.delenv("REDIS_URL", raising=False)
        event = IngestEvent(**_make_shipping_event())
        # Must not raise.
        wr._publish_graph_sync("evt-1", event, "tenant-a")

    def test_publish_graph_sync_disabled_by_default_is_noop(self, monkeypatch):
        """#1378 — default off: no Redis traffic, no counter increment.

        The ``neo4j-sync`` consumer is not in any deployment manifest,
        so the producer must default to disabled to avoid unbounded
        Redis growth. Importing ``redis`` here would fail the test if
        the gate were missing, since the rpush call site would attempt
        the import despite there being no consumer.
        """
        monkeypatch.delenv("ENABLE_NEO4J_SYNC", raising=False)
        monkeypatch.setenv("REDIS_URL", "redis://fake:6379/0")
        pushed: list[tuple[str, str]] = []

        class _Client:
            def rpush(self, topic, payload):
                pushed.append((topic, payload))

            def ltrim(self, *_args, **_kwargs):
                pushed.append(("__ltrim__", ""))

        fake_redis = types.ModuleType("redis")
        fake_redis.from_url = lambda *a, **kw: _Client()
        monkeypatch.setitem(sys.modules, "redis", fake_redis)

        monkeypatch.setattr(wr, "_get_redis_client", lambda: None)
        before_success = wr._graph_sync_successes
        before_failure = wr._graph_sync_failures
        event = IngestEvent(**_make_shipping_event())
        wr._publish_graph_sync("evt-1", event, "tenant-a")
        assert pushed == [], "producer must not contact Redis when ENABLE_NEO4J_SYNC is off"
        assert wr._graph_sync_successes == before_success
        assert wr._graph_sync_failures == before_failure

    @pytest.mark.parametrize("falsey", ["false", "0", "no", "off", "", " "])
    def test_publish_graph_sync_falsey_env_values_are_noop(self, monkeypatch, falsey):
        """A falsey ``ENABLE_NEO4J_SYNC`` keeps the producer off."""
        monkeypatch.setenv("ENABLE_NEO4J_SYNC", falsey)
        monkeypatch.setenv("REDIS_URL", "redis://fake:6379/0")
        pushed: list[tuple[str, str]] = []

        class _Client:
            def rpush(self, topic, payload):
                pushed.append((topic, payload))

            def ltrim(self, *_args, **_kwargs):
                pushed.append(("__ltrim__", ""))

        fake_redis = types.ModuleType("redis")
        fake_redis.from_url = lambda *a, **kw: _Client()
        monkeypatch.setitem(sys.modules, "redis", fake_redis)
        monkeypatch.setattr(wr, "_get_redis_client", lambda: None)
        event = IngestEvent(**_make_shipping_event())
        wr._publish_graph_sync("evt-1", event, "tenant-a")
        assert pushed == []

    def test_publish_graph_sync_success(self, monkeypatch):
        monkeypatch.setenv("ENABLE_NEO4J_SYNC", "true")
        monkeypatch.setenv("REDIS_URL", "redis://fake:6379/0")
        pushed: list[tuple[str, str]] = []
        ltrimmed: list[tuple[str, int, int]] = []

        class _Client:
            def rpush(self, topic, payload):
                pushed.append((topic, payload))

            def ltrim(self, topic, start, stop):
                ltrimmed.append((topic, start, stop))

        fake_redis = types.ModuleType("redis")
        fake_redis.from_url = lambda *a, **kw: _Client()
        monkeypatch.setitem(sys.modules, "redis", fake_redis)

        before = wr._graph_sync_successes
        monkeypatch.setattr(wr, "_get_redis_client", lambda: None)  # force in-mem counter
        event = IngestEvent(**_make_shipping_event())
        wr._publish_graph_sync("evt-1", event, "tenant-a")
        assert pushed and pushed[0][0] == "neo4j-sync"
        assert wr._graph_sync_successes == before + 1
        # LTRIM bound applied — keeps the newest NEO4J_SYNC_MAX_QUEUE entries.
        assert ltrimmed and ltrimmed[0][0] == "neo4j-sync"
        assert ltrimmed[0][2] == -1

    def test_publish_graph_sync_ltrim_failure_does_not_count_as_publish_failure(
        self, monkeypatch
    ):
        """LTRIM bound is best-effort; the rpush already succeeded."""
        monkeypatch.setenv("ENABLE_NEO4J_SYNC", "true")
        monkeypatch.setenv("REDIS_URL", "redis://fake:6379/0")
        pushed: list[tuple[str, str]] = []

        class _Client:
            def rpush(self, topic, payload):
                pushed.append((topic, payload))

            def ltrim(self, *_args, **_kwargs):
                raise RuntimeError("ltrim broken")

        fake_redis = types.ModuleType("redis")
        fake_redis.from_url = lambda *a, **kw: _Client()
        monkeypatch.setitem(sys.modules, "redis", fake_redis)
        monkeypatch.setattr(wr, "_get_redis_client", lambda: None)
        before_success = wr._graph_sync_successes
        before_failure = wr._graph_sync_failures
        event = IngestEvent(**_make_shipping_event())
        wr._publish_graph_sync("evt-1", event, "tenant-a")
        assert pushed and pushed[0][0] == "neo4j-sync"
        assert wr._graph_sync_successes == before_success + 1
        assert wr._graph_sync_failures == before_failure

    def test_publish_graph_sync_max_queue_invalid_env_falls_back_to_default(
        self, monkeypatch
    ):
        """A garbage ``NEO4J_SYNC_MAX_QUEUE`` falls back to 100k."""
        monkeypatch.setenv("NEO4J_SYNC_MAX_QUEUE", "not-a-number")
        assert wr._neo4j_sync_max_queue() == 100_000

    def test_publish_graph_sync_failure_logged_and_counted(self, monkeypatch):
        monkeypatch.setenv("ENABLE_NEO4J_SYNC", "true")
        monkeypatch.setenv("REDIS_URL", "redis://fake:6379/0")

        fake_redis = types.ModuleType("redis")

        def _boom(*a, **kw):
            raise ConnectionError("redis down")

        fake_redis.from_url = _boom
        monkeypatch.setitem(sys.modules, "redis", fake_redis)
        monkeypatch.setattr(wr, "_get_redis_client", lambda: None)
        before = wr._graph_sync_failures
        event = IngestEvent(**_make_shipping_event())
        wr._publish_graph_sync("evt-1", event, "tenant-a")
        assert wr._graph_sync_failures == before + 1

    # ----------------------------------------------------------------
    # #1378 — producer gating + LTRIM bound
    # ----------------------------------------------------------------

    def test_publish_graph_sync_disabled_by_default(self, monkeypatch):
        """With ENABLE_NEO4J_SYNC unset the producer must NOT rpush.

        This is the core #1378 invariant: the consumer at
        ``services/graph/scripts/fsma_sync_worker.py`` is not in any
        deployment manifest, so rpush'ing without a reader grows
        Redis unbounded.  Default OFF prevents that.
        """
        monkeypatch.delenv("ENABLE_NEO4J_SYNC", raising=False)
        monkeypatch.setenv("REDIS_URL", "redis://fake:6379/0")

        pushed: list[tuple[str, str]] = []

        class _Client:
            def rpush(self, topic, payload):  # pragma: no cover - must not run
                pushed.append((topic, payload))

            def ltrim(self, *a, **kw):  # pragma: no cover - must not run
                return True

        fake_redis = types.ModuleType("redis")
        fake_redis.from_url = lambda *a, **kw: _Client()
        monkeypatch.setitem(sys.modules, "redis", fake_redis)
        monkeypatch.setattr(wr, "_get_redis_client", lambda: None)

        event = IngestEvent(**_make_shipping_event())
        wr._publish_graph_sync("evt-1", event, "tenant-a")
        assert pushed == []

    def test_publish_graph_sync_disabled_with_false_flag(self, monkeypatch):
        """Explicit ENABLE_NEO4J_SYNC=false must also disable."""
        monkeypatch.setenv("ENABLE_NEO4J_SYNC", "false")
        monkeypatch.setenv("REDIS_URL", "redis://fake:6379/0")

        pushed: list[tuple[str, str]] = []

        class _Client:
            def rpush(self, topic, payload):  # pragma: no cover
                pushed.append((topic, payload))

            def ltrim(self, *a, **kw):  # pragma: no cover
                return True

        fake_redis = types.ModuleType("redis")
        fake_redis.from_url = lambda *a, **kw: _Client()
        monkeypatch.setitem(sys.modules, "redis", fake_redis)
        monkeypatch.setattr(wr, "_get_redis_client", lambda: None)

        event = IngestEvent(**_make_shipping_event())
        wr._publish_graph_sync("evt-1", event, "tenant-a")
        assert pushed == []

    @pytest.mark.parametrize("truthy", ["1", "true", "True", "YES", "on"])
    def test_publish_graph_sync_truthy_values_enable(self, monkeypatch, truthy):
        monkeypatch.setenv("ENABLE_NEO4J_SYNC", truthy)
        monkeypatch.setenv("REDIS_URL", "redis://fake:6379/0")

        pushed: list[tuple[str, str]] = []

        class _Client:
            def rpush(self, topic, payload):
                pushed.append((topic, payload))

            def ltrim(self, *a, **kw):
                return True

        fake_redis = types.ModuleType("redis")
        fake_redis.from_url = lambda *a, **kw: _Client()
        monkeypatch.setitem(sys.modules, "redis", fake_redis)
        monkeypatch.setattr(wr, "_get_redis_client", lambda: None)

        event = IngestEvent(**_make_shipping_event())
        wr._publish_graph_sync("evt-1", event, "tenant-a")
        assert len(pushed) == 1

    def test_publish_graph_sync_ltrim_bounds_queue_to_default(self, monkeypatch):
        """When publish succeeds the producer must LTRIM to bound
        the list so a stalled consumer cannot grow it without limit."""
        monkeypatch.setenv("ENABLE_NEO4J_SYNC", "true")
        monkeypatch.setenv("REDIS_URL", "redis://fake:6379/0")
        monkeypatch.delenv("NEO4J_SYNC_MAX_QUEUE", raising=False)

        trims: list[tuple[str, int, int]] = []

        class _Client:
            def rpush(self, topic, payload):
                return 1

            def ltrim(self, topic, start, stop):
                trims.append((topic, start, stop))
                return True

        fake_redis = types.ModuleType("redis")
        fake_redis.from_url = lambda *a, **kw: _Client()
        monkeypatch.setitem(sys.modules, "redis", fake_redis)
        monkeypatch.setattr(wr, "_get_redis_client", lambda: None)

        event = IngestEvent(**_make_shipping_event())
        wr._publish_graph_sync("evt-1", event, "tenant-a")
        assert trims, "producer must LTRIM after rpush to bound the list"
        topic, start, stop = trims[0]
        assert topic == "neo4j-sync"
        # Keep the newest 100k entries by default.
        assert start == -100_000
        assert stop == -1

    def test_publish_graph_sync_ltrim_honors_max_queue_override(self, monkeypatch):
        """Operators can tune NEO4J_SYNC_MAX_QUEUE without code change."""
        monkeypatch.setenv("ENABLE_NEO4J_SYNC", "true")
        monkeypatch.setenv("REDIS_URL", "redis://fake:6379/0")
        monkeypatch.setenv("NEO4J_SYNC_MAX_QUEUE", "500")

        trims: list[tuple[str, int, int]] = []

        class _Client:
            def rpush(self, topic, payload):
                return 1

            def ltrim(self, topic, start, stop):
                trims.append((topic, start, stop))
                return True

        fake_redis = types.ModuleType("redis")
        fake_redis.from_url = lambda *a, **kw: _Client()
        monkeypatch.setitem(sys.modules, "redis", fake_redis)
        monkeypatch.setattr(wr, "_get_redis_client", lambda: None)

        event = IngestEvent(**_make_shipping_event())
        wr._publish_graph_sync("evt-1", event, "tenant-a")
        assert trims
        _, start, _ = trims[0]
        assert start == -500

    def test_publish_graph_sync_invalid_max_queue_falls_back(self, monkeypatch):
        """Garbage in NEO4J_SYNC_MAX_QUEUE must not crash the producer."""
        monkeypatch.setenv("ENABLE_NEO4J_SYNC", "true")
        monkeypatch.setenv("REDIS_URL", "redis://fake:6379/0")
        monkeypatch.setenv("NEO4J_SYNC_MAX_QUEUE", "not-a-number")

        trims: list[tuple[str, int, int]] = []

        class _Client:
            def rpush(self, topic, payload):
                return 1

            def ltrim(self, topic, start, stop):
                trims.append((topic, start, stop))
                return True

        fake_redis = types.ModuleType("redis")
        fake_redis.from_url = lambda *a, **kw: _Client()
        monkeypatch.setitem(sys.modules, "redis", fake_redis)
        monkeypatch.setattr(wr, "_get_redis_client", lambda: None)

        event = IngestEvent(**_make_shipping_event())
        wr._publish_graph_sync("evt-1", event, "tenant-a")
        assert trims
        _, start, _ = trims[0]
        # Falls back to 100k default on bad input.
        assert start == -100_000

    def test_publish_graph_sync_ltrim_failure_is_non_fatal(self, monkeypatch):
        """If LTRIM fails after a successful rpush, we must still
        mark the publish as a success — the message is on the list,
        a later publish (or operator action) will bound it."""
        monkeypatch.setenv("ENABLE_NEO4J_SYNC", "true")
        monkeypatch.setenv("REDIS_URL", "redis://fake:6379/0")

        pushed: list[tuple[str, str]] = []

        class _Client:
            def rpush(self, topic, payload):
                pushed.append((topic, payload))
                return 1

            def ltrim(self, topic, start, stop):
                raise ConnectionError("trim failed")

        fake_redis = types.ModuleType("redis")
        fake_redis.from_url = lambda *a, **kw: _Client()
        monkeypatch.setitem(sys.modules, "redis", fake_redis)
        monkeypatch.setattr(wr, "_get_redis_client", lambda: None)

        before_success = wr._graph_sync_successes
        before_failure = wr._graph_sync_failures
        event = IngestEvent(**_make_shipping_event())
        wr._publish_graph_sync("evt-1", event, "tenant-a")
        assert len(pushed) == 1
        # Trim failure should NOT flip the publish to a failure — the
        # message is on the list regardless.
        assert wr._graph_sync_successes == before_success + 1
        assert wr._graph_sync_failures == before_failure


# ---------------------------------------------------------------------------
# /api/v1/webhooks/ingest — end-to-end through the FastAPI app
# ---------------------------------------------------------------------------


class TestIngestEndpoint:
    def _payload(self, *, events: Optional[list[dict]] = None, tenant_id: str = "tenant-a") -> dict:
        return {
            "source": "test",
            "tenant_id": tenant_id,
            "events": events or [_make_shipping_event()],
        }

    def test_happy_path_accepts_events(self, monkeypatch):
        client, session, persistence = _client(monkeypatch)
        resp = client.post(
            "/api/v1/webhooks/ingest",
            json=self._payload(),
            headers={"Idempotency-Key": "idem-1"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["accepted"] == 1
        assert body["rejected"] == 0
        assert persistence.batch_calls
        assert session.committed is True

    def test_tenant_resolved_from_api_key_lookup(self, monkeypatch):
        """Payload without tenant_id falls back to the API-key → tenant lookup."""
        client, _session, persistence = _client(monkeypatch)

        def _api_key_lookup_session():
            sess = _FakeSession()

            def _exec(stmt, params=None):
                sql = str(stmt).lower()
                if "from api_keys" in sql:
                    return _FakeExecuteResult([("tenant-from-key",)])
                return _FakeExecuteResult([])

            sess.execute = _exec  # type: ignore[assignment]
            return sess

        fake_db = sys.modules["shared.database"]
        fake_db.SessionLocal = _api_key_lookup_session  # type: ignore[attr-defined]

        payload = self._payload()
        payload.pop("tenant_id")
        resp = client.post(
            "/api/v1/webhooks/ingest",
            json=payload,
            headers={
                "Idempotency-Key": "idem-2",
                "X-RegEngine-API-Key": "the-key",
            },
        )
        assert resp.status_code == 200
        # Persistence was called with the tenant the key resolved to.
        assert persistence.batch_calls[0]["tenant_id"] == "tenant-from-key"

    def test_tenant_key_lookup_failure_falls_through(self, monkeypatch):
        """If the API-key lookup raises, we continue on to principal.tenant_id."""
        client, _session, persistence = _client(monkeypatch)

        def _boom_session():
            sess = _FakeSession()

            def _exec(stmt, params=None):
                raise RuntimeError("db blip")

            sess.execute = _exec  # type: ignore[assignment]
            return sess

        fake_db = sys.modules["shared.database"]
        fake_db.SessionLocal = _boom_session  # type: ignore[attr-defined]

        # Override principal so it carries the fallback tenant_id.
        app = client.app
        app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
            key_id="test-key",
            scopes=["*"],
            tenant_id="tenant-from-principal",
            auth_mode="test",
        )

        payload = self._payload()
        payload.pop("tenant_id")
        resp = client.post(
            "/api/v1/webhooks/ingest",
            json=payload,
            headers={"Idempotency-Key": "idem-3", "X-RegEngine-API-Key": "the-key"},
        )
        assert resp.status_code == 200
        assert persistence.batch_calls[0]["tenant_id"] == "tenant-from-principal"

    def test_missing_tenant_returns_400(self, monkeypatch):
        client, _session, _persistence = _client(monkeypatch)
        payload = self._payload()
        payload.pop("tenant_id")

        resp = client.post(
            "/api/v1/webhooks/ingest",
            json=payload,
            headers={"Idempotency-Key": "idem-4"},
        )
        assert resp.status_code == 400
        assert "Tenant context required" in resp.json()["detail"]

    def test_db_session_none_returns_503(self, monkeypatch):
        """FastAPI yields ``None`` for db_session when DB is down → 503."""
        session, persistence = _install_shared_stubs(monkeypatch)
        monkeypatch.setattr(wr, "consume_tenant_rate_limit", lambda **_kw: (True, 999))
        monkeypatch.setattr("app.authz.consume_tenant_rate_limit", lambda **_kw: (True, 999))
        monkeypatch.delenv("WEBHOOK_HMAC_SECRET", raising=False)
        app = _build_app()

        def _yield_none():
            yield None

        app.dependency_overrides[get_db_session] = _yield_none
        client = TestClient(app)
        resp = client.post(
            "/api/v1/webhooks/ingest",
            json=self._payload(),
            headers={"Idempotency-Key": "idem-none"},
        )
        assert resp.status_code == 503

    def test_cte_persistence_import_fails_returns_503(self, monkeypatch):
        """If ``from shared.cte_persistence import CTEPersistence`` raises
        we return 503 rather than silently accepting data."""
        session = _FakeSession()
        _install_shared_stubs(monkeypatch, session=session)
        # Clobber the import so the next ``from shared.cte_persistence`` raises.
        monkeypatch.setitem(sys.modules, "shared.cte_persistence", None)
        monkeypatch.setattr(wr, "consume_tenant_rate_limit", lambda **_kw: (True, 999))
        monkeypatch.setattr("app.authz.consume_tenant_rate_limit", lambda **_kw: (True, 999))
        monkeypatch.delenv("WEBHOOK_HMAC_SECRET", raising=False)
        app = _build_app()

        def _override_db():
            yield session

        app.dependency_overrides[get_db_session] = _override_db
        client = TestClient(app)
        resp = client.post(
            "/api/v1/webhooks/ingest",
            json=self._payload(),
            headers={"Idempotency-Key": "idem-imp"},
        )
        assert resp.status_code == 503

    def test_duplicate_events_in_batch_are_rejected(self, monkeypatch):
        client, _session, _persistence = _client(monkeypatch)
        ev = _make_shipping_event()
        resp = client.post(
            "/api/v1/webhooks/ingest",
            json=self._payload(events=[ev, dict(ev)]),
            headers={"Idempotency-Key": "idem-dup"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["accepted"] == 1
        assert body["rejected"] == 1
        assert any(
            r["status"] == "rejected" and "Duplicate event in batch" in r["errors"][0]
            for r in body["events"]
        )

    def test_replay_window_rejects_stale_events(self, monkeypatch):
        client, _session, _persistence = _client(monkeypatch)
        stale_ts = (datetime.now(timezone.utc) - timedelta(days=180)).isoformat()
        stale = _make_shipping_event(timestamp=stale_ts)
        resp = client.post(
            "/api/v1/webhooks/ingest",
            json=self._payload(events=[stale]),
            headers={"Idempotency-Key": "idem-stale"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["rejected"] == 1
        assert any("older than" in r["errors"][0] for r in body["events"])

    def test_missing_kdes_rejected(self, monkeypatch):
        client, _session, _persistence = _client(monkeypatch)
        bad = _make_shipping_event()
        # Drop a required KDE after the pydantic validator runs.
        bad["kdes"].pop("ship_date")
        resp = client.post(
            "/api/v1/webhooks/ingest",
            json=self._payload(events=[bad]),
            headers={"Idempotency-Key": "idem-kde"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["rejected"] == 1
        assert any("ship_date" in r["errors"][0] for r in body["events"])

    def test_batch_persist_failure_falls_back_to_per_event_and_accepts(
        self, monkeypatch
    ):
        """When ``store_events_batch`` raises, we fall through to
        ``store_event`` per record and still record ``accepted``."""
        session = _FakeSession()
        persistence = _FakePersistence(session, batch_raises=ValueError("batch broke"))
        client, _sess, persistence = _client(monkeypatch, session=session, persistence=persistence)
        resp = client.post(
            "/api/v1/webhooks/ingest",
            json=self._payload(),
            headers={"Idempotency-Key": "idem-fb1"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["accepted"] == 1
        assert persistence.store_calls  # fallback executed

    def test_per_event_fallback_records_failure(self, monkeypatch):
        """Both batch AND per-event raise → event ends up rejected with storage error."""
        session = _FakeSession()
        persistence = _FakePersistence(
            session,
            batch_raises=ValueError("batch broke"),
            store_raises=ValueError("per-event broke"),
        )
        client, _sess, _persistence = _client(monkeypatch, session=session, persistence=persistence)
        resp = client.post(
            "/api/v1/webhooks/ingest",
            json=self._payload(),
            headers={"Idempotency-Key": "idem-fb2"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["rejected"] == 1
        assert any("Storage error" in r["errors"][0] for r in body["events"])

    def test_outer_exception_returns_500_and_rolls_back(self, monkeypatch):
        """An un-caught exception in the per-event path bubbles to the outer
        handler → 500 + db.rollback()."""
        session = _FakeSession()

        class _BoomPersistence(_FakePersistence):
            def store_events_batch(self, **kw):
                raise SystemError("wholly unexpected")

        persistence = _BoomPersistence(session)
        client, sess, _persistence = _client(monkeypatch, session=session, persistence=persistence)
        resp = client.post(
            "/api/v1/webhooks/ingest",
            json=self._payload(),
            headers={"Idempotency-Key": "idem-500"},
        )
        assert resp.status_code == 500
        assert sess.rolled_back is True
        assert sess.closed is True

    def test_rules_engine_non_compliant_triggers_exception_queue(self, monkeypatch):
        """If the rules-engine reports non-compliance, the ExceptionQueue is invoked."""
        session, persistence = _install_shared_stubs(monkeypatch)

        class _NonCompliant:
            compliant = False

        class _Engine:
            def __init__(self, *_a, **_kw):
                pass

            def evaluate_event(self, *_a, **_kw):
                return _NonCompliant()

        sys.modules["shared.rules_engine"].RulesEngine = _Engine

        exc_calls: list = []

        class _ExcQueue:
            def __init__(self, *_a, **_kw):
                pass

            def create_exceptions_from_evaluation(self, *a, **kw):
                exc_calls.append((a, kw))

        sys.modules["shared.exception_queue"].ExceptionQueueService = _ExcQueue

        monkeypatch.setattr(wr, "consume_tenant_rate_limit", lambda **_kw: (True, 999))
        monkeypatch.setattr("app.authz.consume_tenant_rate_limit", lambda **_kw: (True, 999))
        monkeypatch.delenv("WEBHOOK_HMAC_SECRET", raising=False)
        app = _build_app()

        def _override_db():
            yield session

        app.dependency_overrides[get_db_session] = _override_db
        client = TestClient(app)
        resp = client.post(
            "/api/v1/webhooks/ingest",
            json=self._payload(),
            headers={"Idempotency-Key": "idem-rules"},
        )
        assert resp.status_code == 200
        assert exc_calls  # ExceptionQueue.create_exceptions_from_evaluation was called

    def test_canonical_mirror_failure_is_silently_skipped(self, monkeypatch):
        """A broken canonical mirror must not fail the ingest."""
        session, persistence = _install_shared_stubs(monkeypatch)

        class _BrokenCanonical:
            def __init__(self, *_a, **_kw):
                pass

            def persist_event(self, *_a, **_kw):
                raise RuntimeError("canonical broke")

        sys.modules["shared.canonical_persistence"].CanonicalEventStore = _BrokenCanonical

        monkeypatch.setattr(wr, "consume_tenant_rate_limit", lambda **_kw: (True, 999))
        monkeypatch.setattr("app.authz.consume_tenant_rate_limit", lambda **_kw: (True, 999))
        monkeypatch.delenv("WEBHOOK_HMAC_SECRET", raising=False)
        app = _build_app()

        def _override_db():
            yield session

        app.dependency_overrides[get_db_session] = _override_db
        client = TestClient(app)
        resp = client.post(
            "/api/v1/webhooks/ingest",
            json=self._payload(),
            headers={"Idempotency-Key": "idem-canon"},
        )
        assert resp.status_code == 200
        # Still accepted despite the broken canonical mirror.
        assert resp.json()["accepted"] == 1

    def test_per_event_fallback_non_compliant_triggers_exception_queue(self, monkeypatch):
        """Covers lines 974-978: in the per-event fallback path, a non-compliant
        rules-engine verdict routes through ExceptionQueueService."""
        session = _FakeSession()
        persistence = _FakePersistence(session, batch_raises=ValueError("batch fail"))
        _install_shared_stubs(monkeypatch, session=session, persistence=persistence)

        class _NonCompliant:
            compliant = False

        class _Engine:
            def __init__(self, *_a, **_kw):
                pass

            def evaluate_event(self, *_a, **_kw):
                return _NonCompliant()

        sys.modules["shared.rules_engine"].RulesEngine = _Engine

        exc_calls: list = []

        class _ExcQueue:
            def __init__(self, *_a, **_kw):
                pass

            def create_exceptions_from_evaluation(self, *a, **kw):
                exc_calls.append((a, kw))

        sys.modules["shared.exception_queue"].ExceptionQueueService = _ExcQueue

        monkeypatch.setattr(wr, "consume_tenant_rate_limit", lambda **_kw: (True, 999))
        monkeypatch.setattr("app.authz.consume_tenant_rate_limit", lambda **_kw: (True, 999))
        monkeypatch.delenv("WEBHOOK_HMAC_SECRET", raising=False)
        app = _build_app()

        def _override_db():
            yield session

        app.dependency_overrides[get_db_session] = _override_db
        client = TestClient(app)
        resp = client.post(
            "/api/v1/webhooks/ingest",
            json=self._payload(),
            headers={"Idempotency-Key": "idem-fb-rules"},
        )
        assert resp.status_code == 200
        # The per-event fallback hit the non-compliant branch.
        assert exc_calls

    def test_per_event_fallback_canonical_failure_is_silently_skipped(self, monkeypatch):
        """Covers lines 977-978: the canonical-persist/rules-engine failure in
        the per-event fallback path lands in the except clause, is logged, and
        does not fail the overall ingest."""
        session = _FakeSession()
        persistence = _FakePersistence(session, batch_raises=ValueError("batch fail"))
        _install_shared_stubs(monkeypatch, session=session, persistence=persistence)

        class _BrokenCanonical:
            def __init__(self, *_a, **_kw):
                pass

            def persist_event(self, *_a, **_kw):
                raise RuntimeError("canonical broke in fallback")

        sys.modules["shared.canonical_persistence"].CanonicalEventStore = _BrokenCanonical

        monkeypatch.setattr(wr, "consume_tenant_rate_limit", lambda **_kw: (True, 999))
        monkeypatch.setattr("app.authz.consume_tenant_rate_limit", lambda **_kw: (True, 999))
        monkeypatch.delenv("WEBHOOK_HMAC_SECRET", raising=False)
        app = _build_app()

        def _override_db():
            yield session

        app.dependency_overrides[get_db_session] = _override_db
        client = TestClient(app)
        resp = client.post(
            "/api/v1/webhooks/ingest",
            json=self._payload(),
            headers={"Idempotency-Key": "idem-fb-canon"},
        )
        assert resp.status_code == 200
        # Still accepted despite the broken canonical mirror in the fallback.
        assert resp.json()["accepted"] == 1

    def test_per_event_fallback_catalog_failure_is_silently_skipped(self, monkeypatch):
        """Covers lines 992-993: the catalog-learn failure in the per-event
        fallback is swallowed so ingest still succeeds."""
        session = _FakeSession()
        persistence = _FakePersistence(session, batch_raises=ValueError("batch fail"))
        _install_shared_stubs(monkeypatch, session=session, persistence=persistence)

        def _learn_bang(**_kw):
            raise ValueError("catalog learn broke")

        sys.modules["app.product_catalog"].learn_from_event = _learn_bang

        monkeypatch.setattr(wr, "consume_tenant_rate_limit", lambda **_kw: (True, 999))
        monkeypatch.setattr("app.authz.consume_tenant_rate_limit", lambda **_kw: (True, 999))
        monkeypatch.delenv("WEBHOOK_HMAC_SECRET", raising=False)
        app = _build_app()

        def _override_db():
            yield session

        app.dependency_overrides[get_db_session] = _override_db
        client = TestClient(app)
        resp = client.post(
            "/api/v1/webhooks/ingest",
            json=self._payload(),
            headers={"Idempotency-Key": "idem-fb-catalog"},
        )
        assert resp.status_code == 200
        # Despite the per-event catalog failure, the event was accepted.
        assert resp.json()["accepted"] == 1

    def test_product_catalog_failure_is_silently_skipped(self, monkeypatch):
        session, persistence = _install_shared_stubs(monkeypatch)

        def _learn_bang(**_kw):
            raise RuntimeError("catalog broke")

        sys.modules["app.product_catalog"].learn_from_event = _learn_bang

        monkeypatch.setattr(wr, "consume_tenant_rate_limit", lambda **_kw: (True, 999))
        monkeypatch.setattr("app.authz.consume_tenant_rate_limit", lambda **_kw: (True, 999))
        monkeypatch.delenv("WEBHOOK_HMAC_SECRET", raising=False)
        app = _build_app()

        def _override_db():
            yield session

        app.dependency_overrides[get_db_session] = _override_db
        client = TestClient(app)
        resp = client.post(
            "/api/v1/webhooks/ingest",
            json=self._payload(),
            headers={"Idempotency-Key": "idem-catalog"},
        )
        assert resp.status_code == 200
        assert resp.json()["accepted"] == 1


# ---------------------------------------------------------------------------
# /api/v1/webhooks/recent
# ---------------------------------------------------------------------------


class TestRecentEventsEndpoint:
    def test_happy_path_returns_rows(self, monkeypatch):
        session = _FakeSession()

        class _Row:
            pass

        row = (
            "evt-1", "shipping", "TLC-1", "Romaine",
            12.0, "cases", "Valley Fresh", "test",
            datetime(2026, 3, 10, 10, 0, 0, tzinfo=timezone.utc),
        )

        def _exec(stmt, params=None):
            return _FakeExecuteResult([row])

        session.execute = _exec  # type: ignore[assignment]

        fake_db = types.ModuleType("shared.database")
        fake_db.SessionLocal = lambda: session
        fake_db.get_db_session = lambda: iter([session])
        monkeypatch.setitem(sys.modules, "shared.database", fake_db)

        app = _build_app()
        client = TestClient(app)
        resp = client.get(
            "/api/v1/webhooks/recent",
            params={"tenant_id": "00000000-0000-0000-0000-000000000111", "limit": 5},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["events"][0]["event_id"] == "evt-1"
        assert session.closed is True

    def test_query_error_returns_empty_response(self, monkeypatch):
        session = _FakeSession()

        def _exec(stmt, params=None):
            raise RuntimeError("db blip")

        session.execute = _exec  # type: ignore[assignment]
        fake_db = types.ModuleType("shared.database")
        fake_db.SessionLocal = lambda: session
        monkeypatch.setitem(sys.modules, "shared.database", fake_db)

        app = _build_app()
        client = TestClient(app)
        resp = client.get(
            "/api/v1/webhooks/recent",
            params={"tenant_id": "00000000-0000-0000-0000-000000000111"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["events"] == []


# ---------------------------------------------------------------------------
# /api/v1/webhooks/chain/verify
# ---------------------------------------------------------------------------


class TestChainVerifyEndpoint:
    def test_happy_path(self, monkeypatch):
        session = _FakeSession()
        persistence = _FakePersistence(session)
        _install_shared_stubs(monkeypatch, session=session, persistence=persistence)
        app = _build_app()
        client = TestClient(app)
        resp = client.get(
            "/api/v1/webhooks/chain/verify",
            params={"tenant_id": "00000000-0000-0000-0000-000000000111"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["chain_valid"] is True
        assert body["chain_length"] == 3

    def test_error_returns_500(self, monkeypatch):
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

        app = _build_app()
        client = TestClient(app)
        resp = client.get(
            "/api/v1/webhooks/chain/verify",
            params={"tenant_id": "00000000-0000-0000-0000-000000000111"},
        )
        assert resp.status_code == 500
