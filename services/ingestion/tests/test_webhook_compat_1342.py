"""Coverage for app/webhook_compat.py — non-HTTP ingestion helpers.

Locks:
- ``_verify_api_key`` delegates to ``shared.auth.require_api_key``.
- ``ingest_events``:
    * missing tenant_id → ValueError (payload contract).
    * ``validate_tenant_id`` delegation.
    * ``_check_rate_limit`` delegation.
    * DB session None → RuntimeError.
    * CTEPersistence import/init errors (ImportError, RuntimeError,
      ConnectionError) → RuntimeError, generator drained even so.
    * Happy-path single event: savepoint commit, publish_graph_sync
      called, canonical + rules + exception-queue block fires,
      canon_sp.commit, response tally (accepted/rejected/total).
    * Duplicate dedup_key in same batch → second copy rejected.
    * ``_validate_event_kdes`` returning errors → rejected.
    * store_event raising (ValueError / TypeError / RuntimeError) →
      savepoint.rollback, event rejected, errors include "Storage".
    * Canonical block raising (ImportError / ValueError / TypeError /
      RuntimeError) → canon_sp.rollback, primary result unchanged.
    * Exception during iteration → db_session.rollback + re-raise.
    * Finally block always drains db_gen (close) even on error.

Issue: #1342
"""

from __future__ import annotations

import asyncio
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app import webhook_compat as wc


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeSavepoint:
    def __init__(self, recorder, name):
        self.recorder = recorder
        self.name = name
        self.committed = False
        self.rolled_back = False

    def commit(self):
        self.committed = True
        self.recorder.append(("commit", self.name))

    def rollback(self):
        self.rolled_back = True
        self.recorder.append(("rollback", self.name))


class _FakeSession:
    def __init__(self):
        self.actions: list[tuple] = []
        self.savepoints: list[_FakeSavepoint] = []
        self.commit_count = 0
        self.rollback_count = 0
        self.begin_nested_raises: Exception | None = None

    def begin_nested(self):
        if self.begin_nested_raises is not None:
            raise self.begin_nested_raises
        # Name savepoints in call order (primary, canonical, primary, canonical, ...)
        name = f"sp-{len(self.savepoints)}"
        sp = _FakeSavepoint(self.actions, name)
        self.savepoints.append(sp)
        return sp

    def commit(self):
        self.commit_count += 1
        self.actions.append(("session_commit",))

    def rollback(self):
        self.rollback_count += 1
        self.actions.append(("session_rollback",))


class _FakePersistence:
    def __init__(self, db_session):
        self.db_session = db_session
        self.store_calls: list[dict] = []
        self.store_result = SimpleNamespace(
            event_id="ev-1", sha256_hash="sha-1", chain_hash="chain-1"
        )
        self.store_raises: Exception | None = None

    def store_event(self, **kwargs):
        self.store_calls.append(kwargs)
        if self.store_raises is not None:
            raise self.store_raises
        return self.store_result


def _make_event(
    *,
    cte_value="harvesting",
    tlc="TLC-1",
    timestamp="2026-01-01T00:00:00Z",
    location_gln=None,
    location_name="Farm",
    kdes=None,
):
    """Build a SimpleNamespace that quacks like IngestEvent."""
    return SimpleNamespace(
        cte_type=SimpleNamespace(value=cte_value),
        traceability_lot_code=tlc,
        product_description="Product",
        quantity=1.0,
        unit_of_measure="kg",
        timestamp=timestamp,
        location_gln=location_gln,
        location_name=location_name,
        kdes=kdes if kdes is not None else {},
    )


def _make_payload(events, tenant_id="t-1", source="manual"):
    return SimpleNamespace(tenant_id=tenant_id, source=source, events=events)


def _install_stubs(
    monkeypatch,
    *,
    session: _FakeSession | None = None,
    persistence: _FakePersistence | None = None,
    cte_persistence_raises: Exception | None = None,
    validate_event_kdes=lambda e: [],
    generate_alerts=lambda e: [],
    rate_limit_raises: Exception | None = None,
    verify_raises: Exception | None = None,
    validate_tenant_id_raises: Exception | None = None,
    session_none: bool = False,
    canonical_raises: Exception | None = None,
    engine_compliant: bool = True,
):
    """Install the full dependency web for ``ingest_events``.

    Returns ``(session, persistence, captured)`` where ``captured``
    tracks side effects from injected stubs.
    """
    sess = session if session is not None else _FakeSession()
    persist = persistence if persistence is not None else _FakePersistence(sess)

    captured: dict = {
        "rate_limit_calls": [],
        "publish_graph_calls": [],
        "verify_calls": [],
        "validate_tenant_calls": [],
        "normalize_calls": [],
        "canonical_store_calls": [],
        "rules_evaluate_calls": [],
        "exc_queue_calls": [],
    }

    # Module-level helpers on wc (imported at module load)
    monkeypatch.setattr(wc, "_verify_api_key_sync", lambda x_regengine_api_key: (
        captured["verify_calls"].append(x_regengine_api_key)
        or (_ for _ in ()).throw(verify_raises) if verify_raises else None
    ))

    def _verify(*, x_regengine_api_key):
        captured["verify_calls"].append(x_regengine_api_key)
        if verify_raises is not None:
            raise verify_raises
    monkeypatch.setattr(wc, "_verify_api_key_sync", _verify)

    def _rate(tenant_id):
        captured["rate_limit_calls"].append(tenant_id)
        if rate_limit_raises is not None:
            raise rate_limit_raises
    monkeypatch.setattr(wc, "_check_rate_limit", _rate)

    monkeypatch.setattr(wc, "_validate_event_kdes", validate_event_kdes)
    monkeypatch.setattr(wc, "_generate_alerts", generate_alerts)

    def _publish(event_id, event, tenant_id):
        captured["publish_graph_calls"].append((event_id, tenant_id))
    monkeypatch.setattr(wc, "_publish_graph_sync", _publish)

    # _get_db_session generator factory on wc
    def _db_gen_factory():
        def _gen():
            yield None if session_none else sess
            # cleanup side effect — tests can assert generator drained
            captured.setdefault("gen_cleanup", 0)
            captured["gen_cleanup"] += 1
        return _gen()
    monkeypatch.setattr(wc, "_get_db_session", _db_gen_factory)

    # Lazy import: app.tenant_validation.validate_tenant_id
    def _validate_tenant(tenant_id):
        captured["validate_tenant_calls"].append(tenant_id)
        if validate_tenant_id_raises is not None:
            raise validate_tenant_id_raises
    tv_mod = ModuleType("app.tenant_validation")
    tv_mod.validate_tenant_id = _validate_tenant
    monkeypatch.setitem(sys.modules, "app.tenant_validation", tv_mod)

    # Lazy import: shared.cte_persistence.CTEPersistence
    def _persistence_cls(db_session):
        if cte_persistence_raises is not None:
            raise cte_persistence_raises
        persist.db_session = db_session
        return persist
    cp_mod = ModuleType("shared.cte_persistence")
    cp_mod.CTEPersistence = _persistence_cls
    monkeypatch.setitem(sys.modules, "shared.cte_persistence", cp_mod)

    # Canonical / rules / exception queue shims
    def _normalize(event, tenant_id):
        captured["normalize_calls"].append((event, tenant_id))
        if canonical_raises is not None and canonical_raises.__class__.__name__ == "_NormalizeRaises":
            raise canonical_raises
        return SimpleNamespace(
            event_id="cev-1",
            event_type=SimpleNamespace(value="harvesting"),
            traceability_lot_code=event.traceability_lot_code,
            product_reference="pref",
            quantity=event.quantity,
            unit_of_measure=event.unit_of_measure,
            from_facility_reference="ff",
            to_facility_reference="tf",
            from_entity_reference="fe",
            to_entity_reference="te",
            kdes=event.kdes,
        )
    ce_mod = ModuleType("shared.canonical_event")
    ce_mod.normalize_webhook_event = _normalize
    monkeypatch.setitem(sys.modules, "shared.canonical_event", ce_mod)

    class _FakeCanonicalStore:
        def __init__(self, db_session, dual_write):
            self.db_session = db_session
            self.dual_write = dual_write

        def persist_event(self, canonical):
            captured["canonical_store_calls"].append(canonical.event_id)
            if canonical_raises is not None:
                raise canonical_raises
    cps_mod = ModuleType("shared.canonical_persistence")
    cps_mod.CanonicalEventStore = _FakeCanonicalStore
    monkeypatch.setitem(sys.modules, "shared.canonical_persistence", cps_mod)

    class _FakeEngine:
        def __init__(self, db_session):
            self.db_session = db_session

        def evaluate_event(self, event_data, persist, tenant_id):
            captured["rules_evaluate_calls"].append(tenant_id)
            return SimpleNamespace(compliant=engine_compliant)
    re_mod = ModuleType("shared.rules_engine")
    re_mod.RulesEngine = _FakeEngine
    monkeypatch.setitem(sys.modules, "shared.rules_engine", re_mod)

    class _FakeExceptionQueue:
        def __init__(self, db_session):
            self.db_session = db_session

        def create_exceptions_from_evaluation(self, tenant_id, summary):
            captured["exc_queue_calls"].append(tenant_id)
    eq_mod = ModuleType("shared.exception_queue")
    eq_mod.ExceptionQueueService = _FakeExceptionQueue
    monkeypatch.setitem(sys.modules, "shared.exception_queue", eq_mod)

    return sess, persist, captured


@pytest.fixture(autouse=True)
def _silence_logger(monkeypatch):
    class _Silent:
        def info(self, *a, **k): pass
        def warning(self, *a, **k): pass
        def error(self, *a, **k): pass
        def debug(self, *a, **k): pass
    monkeypatch.setattr(wc, "logger", _Silent())


# ---------------------------------------------------------------------------
# _verify_api_key (async delegator)
# ---------------------------------------------------------------------------


class TestVerifyApiKeyDelegator:

    def test_delegates_to_require_api_key_with_request_and_header(self, monkeypatch):
        captured = {}

        async def _fake_require(*, request, x_regengine_api_key):
            captured["request"] = request
            captured["x"] = x_regengine_api_key

        monkeypatch.setattr(wc, "require_api_key", _fake_require)
        req = SimpleNamespace(foo=1)
        asyncio.run(wc._verify_api_key(request=req, x_regengine_api_key="k-1"))
        assert captured["request"] is req
        assert captured["x"] == "k-1"

    def test_none_header_value_delegates(self, monkeypatch):
        """Explicit None header is forwarded unchanged."""
        captured = {}

        async def _fake_require(*, request, x_regengine_api_key):
            captured["x"] = x_regengine_api_key

        monkeypatch.setattr(wc, "require_api_key", _fake_require)
        req = SimpleNamespace()
        asyncio.run(wc._verify_api_key(request=req, x_regengine_api_key=None))
        assert captured["x"] is None

    def test_require_api_key_exception_propagates(self, monkeypatch):
        async def _bad(**kwargs):
            raise RuntimeError("auth broke")
        monkeypatch.setattr(wc, "require_api_key", _bad)
        with pytest.raises(RuntimeError, match="auth broke"):
            asyncio.run(wc._verify_api_key(request=SimpleNamespace()))


# ---------------------------------------------------------------------------
# ingest_events — pre-loop gates
# ---------------------------------------------------------------------------


class TestPreLoopGates:

    def test_missing_tenant_id_raises_value_error(self, monkeypatch):
        _install_stubs(monkeypatch)
        payload = _make_payload([_make_event()], tenant_id=None)
        with pytest.raises(ValueError, match="Tenant context required"):
            asyncio.run(wc.ingest_events(payload=payload, x_regengine_api_key="k"))

    def test_empty_tenant_id_also_raises(self, monkeypatch):
        _install_stubs(monkeypatch)
        payload = _make_payload([_make_event()], tenant_id="")
        with pytest.raises(ValueError):
            asyncio.run(wc.ingest_events(payload=payload, x_regengine_api_key="k"))

    def test_validate_tenant_id_is_called(self, monkeypatch):
        _, _, cap = _install_stubs(monkeypatch)
        payload = _make_payload([], tenant_id="tenant-A")
        asyncio.run(wc.ingest_events(payload=payload, x_regengine_api_key="k"))
        assert cap["validate_tenant_calls"] == ["tenant-A"]

    def test_rate_limit_called_with_tenant(self, monkeypatch):
        _, _, cap = _install_stubs(monkeypatch)
        payload = _make_payload([], tenant_id="t-1")
        asyncio.run(wc.ingest_events(payload=payload, x_regengine_api_key="k"))
        assert cap["rate_limit_calls"] == ["t-1"]

    def test_api_key_forwarded_to_sync_verify(self, monkeypatch):
        _, _, cap = _install_stubs(monkeypatch)
        payload = _make_payload([], tenant_id="t")
        asyncio.run(wc.ingest_events(payload=payload, x_regengine_api_key="api-xyz"))
        assert cap["verify_calls"] == ["api-xyz"]

    def test_verify_failure_propagates(self, monkeypatch):
        _install_stubs(monkeypatch, verify_raises=PermissionError("bad key"))
        payload = _make_payload([_make_event()], tenant_id="t")
        with pytest.raises(PermissionError):
            asyncio.run(wc.ingest_events(payload=payload, x_regengine_api_key="k"))

    def test_session_none_raises_runtime_error(self, monkeypatch):
        _install_stubs(monkeypatch, session_none=True)
        payload = _make_payload([_make_event()], tenant_id="t")
        with pytest.raises(RuntimeError, match="Database unavailable"):
            asyncio.run(wc.ingest_events(payload=payload, x_regengine_api_key="k"))

    @pytest.mark.parametrize("exc", [
        ImportError("missing"),
        RuntimeError("conn"),
        ConnectionError("no route"),
    ])
    def test_cte_persistence_init_error_raises_runtime(self, monkeypatch, exc):
        _, _, cap = _install_stubs(monkeypatch, cte_persistence_raises=exc)
        payload = _make_payload([_make_event()], tenant_id="t")
        with pytest.raises(RuntimeError, match="Database unavailable"):
            asyncio.run(wc.ingest_events(payload=payload, x_regengine_api_key="k"))
        # Generator drained even after CTEPersistence failure
        assert cap.get("gen_cleanup") == 1


# ---------------------------------------------------------------------------
# ingest_events — per-event processing
# ---------------------------------------------------------------------------


class TestEventProcessing:

    def test_empty_events_list_returns_zero_tally(self, monkeypatch):
        _install_stubs(monkeypatch)
        payload = _make_payload([], tenant_id="t")
        resp = asyncio.run(wc.ingest_events(payload=payload, x_regengine_api_key="k"))
        assert resp.accepted == 0
        assert resp.rejected == 0
        assert resp.total == 0
        assert resp.events == []

    def test_happy_path_single_event_accepted(self, monkeypatch):
        sess, persist, cap = _install_stubs(monkeypatch)
        payload = _make_payload([_make_event(tlc="TLC-1")], tenant_id="t")
        resp = asyncio.run(wc.ingest_events(payload=payload, x_regengine_api_key="k"))

        assert resp.accepted == 1
        assert resp.rejected == 0
        assert resp.total == 1
        assert resp.events[0].status == "accepted"
        assert resp.events[0].event_id == "ev-1"
        assert resp.events[0].sha256_hash == "sha-1"
        assert resp.events[0].chain_hash == "chain-1"
        # store_event received all the expected kwargs
        call = persist.store_calls[0]
        assert call["tenant_id"] == "t"
        assert call["traceability_lot_code"] == "TLC-1"
        assert call["event_type"] == "harvesting"
        assert call["source"] == "manual"
        # Savepoint committed, session committed once at the end
        assert any(a == ("commit", "sp-0") for a in sess.actions)
        assert sess.commit_count == 1
        # Graph sync, canonical path, rules + exc queue all fire in happy path
        assert cap["publish_graph_calls"] == [("ev-1", "t")]
        assert cap["normalize_calls"] and cap["normalize_calls"][0][1] == "t"
        assert cap["canonical_store_calls"] == ["cev-1"]
        assert cap["rules_evaluate_calls"] == ["t"]
        # engine_compliant=True by default → no exception-queue invocation
        assert cap["exc_queue_calls"] == []
        # Session closed via generator drain
        assert cap.get("gen_cleanup") == 1

    def test_non_compliant_summary_triggers_exception_queue(self, monkeypatch):
        _, _, cap = _install_stubs(monkeypatch, engine_compliant=False)
        payload = _make_payload([_make_event()], tenant_id="t-x")
        asyncio.run(wc.ingest_events(payload=payload, x_regengine_api_key="k"))
        assert cap["exc_queue_calls"] == ["t-x"]

    def test_duplicate_in_batch_rejected(self, monkeypatch):
        sess, persist, _ = _install_stubs(monkeypatch)
        e1 = _make_event(tlc="TLC-DUP", timestamp="2026-01-01T00:00:00Z",
                         location_name="X")
        e2 = _make_event(tlc="TLC-DUP", timestamp="2026-01-01T00:00:00Z",
                         location_name="X")
        payload = _make_payload([e1, e2], tenant_id="t")
        resp = asyncio.run(wc.ingest_events(payload=payload, x_regengine_api_key="k"))
        assert resp.accepted == 1
        assert resp.rejected == 1
        assert resp.events[0].status == "accepted"
        assert resp.events[1].status == "rejected"
        assert "Duplicate event in batch" in resp.events[1].errors
        # store_event invoked only once (duplicate skipped before persistence)
        assert len(persist.store_calls) == 1

    def test_location_gln_used_in_dedup_key(self, monkeypatch):
        """Two events with different location_glns should NOT dedup."""
        _, persist, _ = _install_stubs(monkeypatch)
        e1 = _make_event(tlc="TLC-A", location_gln="0123456789012",
                         location_name=None)
        e2 = _make_event(tlc="TLC-A", location_gln="9876543210987",
                         location_name=None)
        payload = _make_payload([e1, e2], tenant_id="t")
        resp = asyncio.run(wc.ingest_events(payload=payload, x_regengine_api_key="k"))
        assert resp.accepted == 2
        assert resp.rejected == 0
        assert len(persist.store_calls) == 2

    def test_missing_location_fields_use_empty_string_in_dedup(self, monkeypatch):
        """location_gln=None and location_name=None → '' in dedup_key.
        Two such events with identical other fields collapse to one."""
        _, persist, _ = _install_stubs(monkeypatch)
        e1 = _make_event(tlc="TLC-Z", location_gln=None, location_name=None)
        e2 = _make_event(tlc="TLC-Z", location_gln=None, location_name=None)
        payload = _make_payload([e1, e2], tenant_id="t")
        resp = asyncio.run(wc.ingest_events(payload=payload, x_regengine_api_key="k"))
        assert resp.accepted == 1
        assert resp.rejected == 1
        assert len(persist.store_calls) == 1

    def test_validation_errors_reject_event(self, monkeypatch):
        """_validate_event_kdes returning a non-empty list rejects the event."""
        errors = ["missing harvest_date", "missing reference_document"]
        _, persist, _ = _install_stubs(
            monkeypatch, validate_event_kdes=lambda e: errors
        )
        payload = _make_payload([_make_event()], tenant_id="t")
        resp = asyncio.run(wc.ingest_events(payload=payload, x_regengine_api_key="k"))
        assert resp.accepted == 0
        assert resp.rejected == 1
        assert resp.events[0].status == "rejected"
        assert resp.events[0].errors == errors
        # Never reached persistence
        assert persist.store_calls == []

    @pytest.mark.parametrize("exc_cls", [ValueError, TypeError, RuntimeError])
    def test_store_event_error_rolls_savepoint_and_rejects(self, monkeypatch, exc_cls):
        sess = _FakeSession()
        persist = _FakePersistence(sess)
        persist.store_raises = exc_cls("boom")
        _, _, _ = _install_stubs(monkeypatch, session=sess, persistence=persist)
        payload = _make_payload([_make_event()], tenant_id="t")
        resp = asyncio.run(wc.ingest_events(payload=payload, x_regengine_api_key="k"))
        assert resp.accepted == 0
        assert resp.rejected == 1
        assert resp.events[0].status == "rejected"
        assert any("Storage error" in e for e in resp.events[0].errors)
        # Primary savepoint rolled back
        assert sess.savepoints[0].rolled_back is True
        # Session still commits at end (one successful rollback path inside loop)
        assert sess.commit_count == 1

    @pytest.mark.parametrize("exc_cls", [ImportError, ValueError, TypeError, RuntimeError])
    def test_canonical_block_error_rolls_only_canonical_savepoint(
        self, monkeypatch, exc_cls
    ):
        """A failure in the canonical/rules block must NOT reject the event.

        The primary savepoint already committed; only the canonical
        savepoint rolls back, and the result status stays "accepted".
        """
        sess = _FakeSession()

        class _FailingStore:
            def __init__(self, db_session, dual_write):
                pass
            def persist_event(self, canonical):
                raise exc_cls("canonical fail")

        # Install base stubs, then override CanonicalEventStore
        _, persist, _ = _install_stubs(monkeypatch, session=sess)
        cps_mod = sys.modules["shared.canonical_persistence"]
        monkeypatch.setattr(cps_mod, "CanonicalEventStore", _FailingStore)

        payload = _make_payload([_make_event()], tenant_id="t")
        resp = asyncio.run(wc.ingest_events(payload=payload, x_regengine_api_key="k"))

        assert resp.accepted == 1
        assert resp.rejected == 0
        assert resp.events[0].status == "accepted"
        # Primary savepoint committed, canonical savepoint rolled back
        assert sess.savepoints[0].committed is True
        assert sess.savepoints[1].rolled_back is True


# ---------------------------------------------------------------------------
# ingest_events — top-level exception handling & cleanup
# ---------------------------------------------------------------------------


class TestTopLevelExceptionAndCleanup:

    def test_unhandled_exception_rolls_session_and_reraises(self, monkeypatch):
        """If something inside the loop escapes the per-event try,
        the session is rolled back and the exception re-raised.

        We force begin_nested() to raise — that's not caught by the
        inner except and bubbles to the outer handler.
        """
        sess = _FakeSession()
        sess.begin_nested_raises = KeyError("boom")
        _, _, cap = _install_stubs(monkeypatch, session=sess)
        payload = _make_payload([_make_event()], tenant_id="t")
        with pytest.raises(KeyError):
            asyncio.run(wc.ingest_events(payload=payload, x_regengine_api_key="k"))
        assert sess.rollback_count == 1
        # Generator still drained in finally
        assert cap.get("gen_cleanup") == 1

    def test_generator_drained_on_happy_path(self, monkeypatch):
        _, _, cap = _install_stubs(monkeypatch)
        payload = _make_payload([_make_event()], tenant_id="t")
        asyncio.run(wc.ingest_events(payload=payload, x_regengine_api_key="k"))
        assert cap["gen_cleanup"] == 1
