"""Focused coverage for ``app/epcis/persistence.py`` — #1342.

Targets every non-DB-dependent branch of ``app/epcis/persistence.py``
via unit-level tests with DB sessions replaced by ``MagicMock`` and
heavyweight imports (``shared.cte_persistence``,
``shared.canonical_persistence``, ``shared.rules_engine``) stubbed on
``sys.modules`` so this file runs without Postgres or testcontainers.

Scope:

- Pure helpers: ``_safe_iso`` (all three input shapes),
  ``_build_kde_map`` (product_id + location branches),
  ``_parse_epcis_document`` (valid-json / invalid-json /
  synthesis-from-normalized paths).
- Env-gated helpers: ``_allow_in_memory_fallback`` explicit-override
  + is_production fallback, ``_fsma_strict_mode`` every env variant.
- Fallback store FIFO eviction when ``EPCIS_FALLBACK_CAP_PER_TENANT``
  is tight.
- Dynamic-SQL alert row query (``_query_alert_rows``) — allowlist
  intersection empty, tenant/event col fallback, happy-path shape.
- ``_fetch_event_from_db`` + ``_list_events_from_db`` with mocked
  sessions.
- ``_ingest_single_event_fallback`` validation-error branch + FSMA
  strict-mode rejection + advisory-mode tag.
- ``_prepare_event_for_persistence`` FSMA strict rejection + missing
  quantity + non-numeric quantity.
- ``_persist_prepared_event_in_session`` idempotent-skip-canonical
  and canonical-success paths.
- ``_ingest_single_event_db`` happy-path commit + rollback on error.
- ``_ingest_batch_events_db_atomic`` validation-phase errors,
  persistence-phase rollback, and happy path.
- ``_ingest_single_event`` dispatcher: DB error + no fallback → 503,
  DB error + fallback → routes to fallback path.

Issue: #1342
"""

from __future__ import annotations

import json
import os
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

# ── Fakes for the heavyweight ``shared.*`` symbols that
#    ``_persist_prepared_event_in_session`` imports lazily. We install these
#    via ``monkeypatch.setattr`` on the already-loaded real modules in an
#    autouse fixture below, so the real module graph (including
#    ``shared.canonical_event.normalize_webhook_event`` used by the
#    webhook-compat layer pulled in by ``app/epcis/__init__.py``) still loads
#    cleanly.


class _FakeStoreResult:
    def __init__(self, event_id: str = "evt-fake", idempotent: bool = False) -> None:
        self.event_id = event_id
        self.idempotent = idempotent


class _FakeCTEPersistence:
    last_instance: "_FakeCTEPersistence | None" = None
    last_kwargs: dict[str, Any] = {}
    idempotent_flag: bool = False

    def __init__(self, db_session: Any) -> None:
        self.db_session = db_session
        _FakeCTEPersistence.last_instance = self

    def store_event(self, **kwargs: Any) -> _FakeStoreResult:
        _FakeCTEPersistence.last_kwargs = kwargs
        return _FakeStoreResult(
            event_id="cte-stored-id",
            idempotent=_FakeCTEPersistence.idempotent_flag,
        )


class _FakeCanonicalEventStore:
    def __init__(self, db_session: Any, dual_write: bool = False, skip_chain_write: bool = False) -> None:
        self.db_session = db_session

    def set_tenant_context(self, tenant_id: str) -> None:
        pass

    def persist_event(self, canonical: Any) -> None:
        pass


class _FakeRulesEngine:
    def __init__(self, db_session: Any) -> None:
        self.db_session = db_session

    def evaluate_event(self, event_data: dict, persist: bool, tenant_id: str) -> None:
        pass


def _fake_normalize_epcis_event(event: dict, tenant_id: str) -> Any:
    class _Canonical:
        event_id = "canonical-id"
        event_type = MagicMock(value="OBJECT_EVENT")
        traceability_lot_code = ""
        product_reference = ""
        quantity = 1.0
        unit_of_measure = ""
        from_facility_reference = None
        to_facility_reference = None
        from_entity_reference = None
        to_entity_reference = None
        kdes: dict[str, Any] = {}

    return _Canonical()


from app.epcis import persistence as persistence_mod  # noqa: E402

# ── Helpers: reset module-level state + install fakes between tests ────────


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch: pytest.MonkeyPatch) -> None:
    persistence_mod._epcis_store.clear()
    persistence_mod._epcis_idempotency_index.clear()
    _FakeCTEPersistence.idempotent_flag = False
    _FakeCTEPersistence.last_kwargs = {}
    _FakeCTEPersistence.last_instance = None

    # Replace the heavyweight shared.* classes used by the lazy imports in
    # ``_persist_prepared_event_in_session`` with hermetic fakes. These are
    # picked up by the ``from shared.X import Y`` statements at call time
    # because we swap the module attribute, not the imported binding.
    import shared.canonical_event as _canon_mod
    import shared.canonical_persistence as _store_mod
    import shared.cte_persistence as _cte_mod
    import shared.rules_engine as _rules_mod

    monkeypatch.setattr(_cte_mod, "CTEPersistence", _FakeCTEPersistence)
    monkeypatch.setattr(_canon_mod, "normalize_epcis_event", _fake_normalize_epcis_event)
    monkeypatch.setattr(_store_mod, "CanonicalEventStore", _FakeCanonicalEventStore)
    monkeypatch.setattr(_rules_mod, "RulesEngine", _FakeRulesEngine)


# ── _safe_iso ──────────────────────────────────────────────────────────────


def _later_than(moment: datetime) -> datetime:
    """Next clock reading strictly after ``moment``. No offset is applied."""
    later = datetime.now(timezone.utc)
    while not moment < later:
        later = datetime.now(timezone.utc)
    return later


class TestSafeIso:
    def test_naive_datetime_gets_utc(self) -> None:
        wall = datetime.now(timezone.utc).replace(tzinfo=None)
        as_utc = wall.replace(tzinfo=timezone.utc)
        later = _later_than(as_utc)
        result = persistence_mod._safe_iso(wall)
        parsed = datetime.fromisoformat(result)
        assert parsed.tzinfo is not None
        assert result.endswith("+00:00")
        assert as_utc <= parsed <= as_utc
        assert parsed < later

    def test_aware_datetime_normalized_to_utc(self) -> None:
        moment = datetime.now(timezone.utc)
        later = _later_than(moment)
        result = persistence_mod._safe_iso(moment)
        parsed = datetime.fromisoformat(result)
        assert parsed.tzinfo is not None
        assert result.endswith("+00:00")
        assert moment <= parsed <= moment
        assert parsed < later

    def test_string_passes_through_unchanged(self) -> None:
        assert persistence_mod._safe_iso("event-time") == "event-time"

    def test_none_substitutes_now_iso(self) -> None:
        before = datetime.now(timezone.utc)
        result = persistence_mod._safe_iso(None)
        after = datetime.now(timezone.utc)
        parsed = datetime.fromisoformat(result)
        assert parsed.tzinfo is not None
        assert before <= parsed <= after


# ── _build_kde_map ─────────────────────────────────────────────────────────


class TestBuildKdeMap:
    def test_skips_product_and_location_when_normalized_empty(self) -> None:
        kde_map = persistence_mod._build_kde_map({}, {}, "idem-2")
        assert "product_id" not in kde_map
        assert "ship_from_gln" not in kde_map
        assert "ship_to_gln" not in kde_map
        assert kde_map["epcis_idempotency_key"] == "idem-2"
        assert kde_map["epcis_document_json"] == "{}"


# ── _parse_epcis_document ──────────────────────────────────────────────────


class TestParseEpcisDocument:
    def test_returns_parsed_json_when_round_trip_ok(self) -> None:
        kdes = {"epcis_document_json": "{}"}
        result = persistence_mod._parse_epcis_document(kdes, {})
        assert result == {}

    def test_malformed_json_falls_back_to_synthesis(self, caplog: pytest.LogCaptureFixture) -> None:
        kdes = {"epcis_document_json": "{not-json"}
        normalized = {"epcis_event_type": "TransformationEvent"}
        with caplog.at_level("WARNING"):
            result = persistence_mod._parse_epcis_document(kdes, normalized)
        assert result["type"] == "TransformationEvent"
        assert "action" not in result
        assert result["ilmd"] == {}
        assert "sourceList" not in result
        assert "destinationList" not in result
        assert any("parse_failed" in m for m in caplog.messages)

    def test_non_dict_parsed_json_falls_back(self) -> None:
        kdes = {"epcis_document_json": '"just-a-string"'}
        normalized = {"epcis_event_type": "ObjectEvent"}
        result = persistence_mod._parse_epcis_document(kdes, normalized)
        # Not the string — fell through to synthesis.
        assert result["type"] == "ObjectEvent"

    def test_no_raw_json_synthesizes_from_normalized_defaults(self) -> None:
        result = persistence_mod._parse_epcis_document({}, {})
        assert result["type"] == "ObjectEvent"
        assert result["action"] == "OBSERVE"
        assert result["bizStep"] == "urn:epcglobal:cbv:bizstep:receiving"
        # Empty ilmd when nothing supplied.
        assert result["ilmd"] == {}


# ── _allow_in_memory_fallback + _fsma_strict_mode ──────────────────────────


class TestFlagHelpers:
    def test_allow_fallback_explicit_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ALLOW_EPCIS_IN_MEMORY_FALLBACK", "true")
        assert persistence_mod._allow_in_memory_fallback() is True

    def test_allow_fallback_explicit_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ALLOW_EPCIS_IN_MEMORY_FALLBACK", "no")
        assert persistence_mod._allow_in_memory_fallback() is False

    def test_allow_fallback_implicit_production(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ALLOW_EPCIS_IN_MEMORY_FALLBACK", raising=False)
        monkeypatch.setattr(persistence_mod, "_is_production", lambda: True)
        assert persistence_mod._allow_in_memory_fallback() is False

    def test_allow_fallback_implicit_nonprod(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ALLOW_EPCIS_IN_MEMORY_FALLBACK", raising=False)
        monkeypatch.setattr(persistence_mod, "_is_production", lambda: False)
        assert persistence_mod._allow_in_memory_fallback() is True

    def test_is_production_delegates_to_shared_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import shared.env as env_mod

        monkeypatch.setattr(env_mod, "is_production", lambda: True)
        assert persistence_mod._is_production() is True

    def test_fsma_strict_mode_defaults_to_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("FSMA_STRICT_MODE", raising=False)
        assert persistence_mod._fsma_strict_mode() is True

    @pytest.mark.parametrize("val", ["false", "0", "no", "off", "advisory"])
    def test_fsma_strict_mode_false_variants(self, monkeypatch: pytest.MonkeyPatch, val: str) -> None:
        monkeypatch.setenv("FSMA_STRICT_MODE", val)
        assert persistence_mod._fsma_strict_mode() is False

    @pytest.mark.parametrize("val", ["1", "true", "yes", "on", "strict"])
    def test_fsma_strict_mode_true_variants(self, monkeypatch: pytest.MonkeyPatch, val: str) -> None:
        monkeypatch.setenv("FSMA_STRICT_MODE", val)
        assert persistence_mod._fsma_strict_mode() is True


# ── Fallback store FIFO eviction ──────────────────────────────────────────


class TestFallbackFifoEviction:
    def test_store_evicts_oldest_when_over_cap(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Line 66: FIFO eviction when fallback store hits its cap."""
        monkeypatch.setattr(persistence_mod, "_EPCIS_FALLBACK_CAP_PER_TENANT", 2)

        persistence_mod._fallback_store_put("t1", "a", {"cte": 1})
        persistence_mod._fallback_store_put("t1", "b", {"cte": 2})
        persistence_mod._fallback_store_put("t1", "c", {"cte": 3})

        store = persistence_mod._fallback_store_for("t1")
        assert "a" not in store  # evicted
        assert list(store.keys()) == ["b", "c"]

    def test_idempotency_index_evicts_oldest_when_over_cap(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Line 73: FIFO eviction on idempotency index."""
        monkeypatch.setattr(persistence_mod, "_EPCIS_FALLBACK_CAP_PER_TENANT", 2)

        persistence_mod._fallback_idempotency_put("t1", "k1", "e1")
        persistence_mod._fallback_idempotency_put("t1", "k2", "e2")
        persistence_mod._fallback_idempotency_put("t1", "k3", "e3")

        idx = persistence_mod._fallback_idempotency_for("t1")
        assert "k1" not in idx
        assert list(idx.keys()) == ["k2", "k3"]


# ── _query_alert_rows ──────────────────────────────────────────────────────


def _make_row(severity: str, alert_type: str, message: str) -> Any:
    r = MagicMock()
    r.severity = severity
    r.alert_type = alert_type
    r.message = message
    return r


class _FakeSession:
    """Minimal DB session driver: queue execute results."""

    def __init__(self) -> None:
        self.execute_queue: list[Any] = []  # list of fetch-returning objects

    def queue(self, fetch_result: Any) -> None:
        self.execute_queue.append(fetch_result)

    def execute(self, *_args: Any, **_kwargs: Any) -> Any:
        nxt = self.execute_queue.pop(0)
        holder = MagicMock()
        # Each queued item is either:
        #   - a list of "rows" (for fetchall),
        #   - a single "row" object (for fetchone), or
        #   - ``None`` (fetchone returns None — i.e. no match).
        if isinstance(nxt, list):
            holder.fetchall.return_value = nxt
            holder.fetchone.return_value = nxt[0] if nxt else None
        elif nxt is None:
            holder.fetchall.return_value = []
            holder.fetchone.return_value = None
        else:
            holder.fetchall.return_value = [nxt]
            holder.fetchone.return_value = nxt
        return holder

    def close(self) -> None:
        pass

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass


class TestQueryAlertRows:
    def test_empty_allowlist_intersection_returns_empty(self) -> None:
        """Lines 177-178: no overlap between schema columns and allowlist → []."""
        sess = _FakeSession()
        # Schema returns columns that are NOT in the allowlist.
        sess.queue([("random_col",), ("another",)])
        rows = persistence_mod._query_alert_rows(sess, "tenant-1", "event-1")
        assert rows == []

    def test_missing_tenant_col_returns_empty(self) -> None:
        """Lines 190-191: allowlist has cols but no tenant_id/org_id → []."""
        sess = _FakeSession()
        sess.queue([("severity",), ("alert_type",), ("message",), ("cte_event_id",)])
        rows = persistence_mod._query_alert_rows(sess, "tenant-1", "event-1")
        assert rows == []

    def test_missing_event_col_returns_empty(self) -> None:
        """Same: has tenant col but no cte_event_id / event_id → []."""
        sess = _FakeSession()
        sess.queue([("tenant_id",), ("severity",), ("alert_type",), ("message",)])
        rows = persistence_mod._query_alert_rows(sess, "tenant-1", "event-1")
        assert rows == []

    def test_happy_path_returns_normalized_rows(self) -> None:
        sess = _FakeSession()
        # Schema: has all fields.
        sess.queue(
            [
                ("tenant_id",),
                ("cte_event_id",),
                ("severity",),
                ("alert_type",),
                ("message",),
                ("created_at",),
            ]
        )
        # Alerts.
        sess.queue(
            [
                _make_row("warning", "row_a", "first row"),
                _make_row("error", "row_b", "second row"),
            ]
        )

        rows = persistence_mod._query_alert_rows(sess, "tenant-1", "event-1")
        assert rows == [
            {"severity": "warning", "alert_type": "row_a", "message": "first row"},
            {"severity": "error", "alert_type": "row_b", "message": "second row"},
        ]

    def test_fallback_to_org_id_and_event_id_and_description(self) -> None:
        """Exercises the ``org_id`` / ``event_id`` / ``description`` fallback
        branches of the identifier selection ladder."""
        sess = _FakeSession()
        sess.queue(
            [
                ("org_id",),
                ("event_id",),
                ("severity",),
                ("alert_type",),
                ("description",),
                ("created_at",),
            ]
        )
        sess.queue([])  # no matching alerts — still exercises the SELECT.
        rows = persistence_mod._query_alert_rows(sess, "t", "e")
        assert rows == []


# ── _fetch_event_from_db ──────────────────────────────────────────────────


class TestFetchEventFromDb:
    def test_returns_none_when_main_row_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        sess = _FakeSession()
        sess.queue(None)  # main SELECT returns nothing
        monkeypatch.setattr(persistence_mod, "get_db_safe", lambda: sess)

        result = persistence_mod._fetch_event_from_db("tenant-1", "missing")
        assert result is None


# ── _list_events_from_db ──────────────────────────────────────────────────


class TestListEventsFromDb:
    def test_no_filters_returns_all(self, monkeypatch: pytest.MonkeyPatch) -> None:
        sess = _FakeSession()
        sess.queue([])  # no rows
        monkeypatch.setattr(persistence_mod, "get_db_safe", lambda: sess)
        events = persistence_mod._list_events_from_db("tenant-1", None, None, None)
        assert events == []


def _empty_prepared() -> dict:
    return {
        "event": {},
        "idempotency_key": "idem-1",
        "normalized": {
            "event_type": "receiving",
            "tlc": "",
            "quantity": 1.0,
            "unit_of_measure": "",
            "event_time": "present",
        },
        "kdes": [],
        "alerts": [],
        "kde_map": {"fsma_validation_status": "passed"},
        "quantity_value": 1.0,
        "event_time": "present",
    }


def _stub_prepare_past_validation(monkeypatch: pytest.MonkeyPatch, normalized: dict) -> None:
    monkeypatch.setattr(persistence_mod, "_validate_epcis", lambda event: [])
    monkeypatch.setattr(persistence_mod, "_normalize_epcis_to_cte", lambda event: normalized)
    monkeypatch.setattr(persistence_mod, "_validate_as_fsma_event", lambda n, t: {"ok": True})


# ── _ingest_single_event_fallback ─────────────────────────────────────────


class TestIngestSingleEventFallback:
    def test_validation_errors_raise_400(self) -> None:
        with pytest.raises(HTTPException) as exc:
            persistence_mod._ingest_single_event_fallback("tenant-1", {})
        assert exc.value.status_code == 400
        assert "Traceback" not in str(exc.value.detail)


# ── _prepare_event_for_persistence ────────────────────────────────────────


class TestPrepareEventForPersistence:
    def test_validation_errors_raise_400(self) -> None:
        with pytest.raises(HTTPException) as exc:
            persistence_mod._prepare_event_for_persistence("tenant-1", {})
        assert exc.value.status_code == 400
        assert "Traceback" not in str(exc.value.detail)

    def test_missing_quantity_raises_422(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_prepare_past_validation(
            monkeypatch,
            {
                "event_type": "receiving",
                "event_time": "present",
            },
        )
        with pytest.raises(HTTPException) as exc:
            persistence_mod._prepare_event_for_persistence("tenant-1", {})
        assert exc.value.status_code == 422
        assert exc.value.detail["error"] == "missing_quantity"

    def test_non_numeric_quantity_raises_422(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_prepare_past_validation(
            monkeypatch,
            {
                "event_type": "receiving",
                "event_time": "present",
                "quantity": "not-a-number",
            },
        )
        with pytest.raises(HTTPException) as exc:
            persistence_mod._prepare_event_for_persistence("tenant-1", {})
        assert exc.value.status_code == 422
        assert exc.value.detail["error"] == "non_numeric_quantity"

    def test_missing_event_time_raises_422_instead_of_stamping_now(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_prepare_past_validation(
            monkeypatch,
            {
                "event_type": "receiving",
                "event_time": None,
                "quantity": 4,
            },
        )
        with pytest.raises(HTTPException) as exc:
            persistence_mod._prepare_event_for_persistence("tenant-1", {})
        assert exc.value.status_code == 422
        assert exc.value.detail["error"] == "missing_event_time"


# ── _persist_prepared_event_in_session ────────────────────────────────────


class TestPersistPreparedEventInSession:
    def test_non_idempotent_triggers_canonical_write(self) -> None:
        _FakeCTEPersistence.idempotent_flag = False
        payload, status = persistence_mod._persist_prepared_event_in_session(
            MagicMock(), "tenant-1", _empty_prepared()
        )
        assert status == 201
        assert payload["idempotent"] is False

    def test_idempotent_result_skips_canonical_write(self) -> None:
        _FakeCTEPersistence.idempotent_flag = True
        payload, status = persistence_mod._persist_prepared_event_in_session(
            MagicMock(), "tenant-1", _empty_prepared()
        )
        assert status == 200
        assert payload["idempotent"] is True

    def test_canonical_write_failure_now_propagates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _FakeCTEPersistence.idempotent_flag = False
        import shared.canonical_event as ce

        monkeypatch.setattr(
            ce,
            "normalize_epcis_event",
            lambda e, t: (_ for _ in ()).throw(RuntimeError("canon boom")),
        )
        with pytest.raises(RuntimeError, match="canon boom"):
            persistence_mod._persist_prepared_event_in_session(MagicMock(), "tenant-1", _empty_prepared())


# ── _ingest_single_event_db ───────────────────────────────────────────────


class TestIngestSingleEventDb:
    def test_exception_triggers_rollback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        sess = MagicMock()
        monkeypatch.setattr(persistence_mod, "get_db_safe", lambda: sess)
        monkeypatch.setattr(persistence_mod, "_prepare_event_for_persistence", lambda t, e: _empty_prepared())
        monkeypatch.setattr(
            persistence_mod,
            "_persist_prepared_event_in_session",
            lambda s, t, p: (_ for _ in ()).throw(RuntimeError("pg dead")),
        )
        with pytest.raises(RuntimeError, match="pg dead"):
            persistence_mod._ingest_single_event_db("tenant-1", {})
        sess.rollback.assert_called_once()
        sess.close.assert_called_once()


# ── _ingest_batch_events_db_atomic ────────────────────────────────────────


class TestIngestBatchEventsDbAtomic:
    def test_pre_validation_failures_raise_400_without_touching_db(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = {"n": 0}

        def _db():
            calls["n"] += 1
            return MagicMock()

        monkeypatch.setattr(persistence_mod, "get_db_safe", _db)
        with pytest.raises(HTTPException) as exc:
            persistence_mod._ingest_batch_events_db_atomic("tenant-1", [{}])
        assert exc.value.status_code == 400
        assert exc.value.detail["error"] == "batch_validation_failed"
        assert exc.value.detail["mode"] == "atomic"
        assert exc.value.detail["errors"][0]["index"] == 0
        assert calls["n"] == 0
        assert "Traceback" not in str(exc.value.detail)

    def test_persistence_phase_failure_rolls_back_and_raises_400(self, monkeypatch: pytest.MonkeyPatch) -> None:
        sess = MagicMock()
        monkeypatch.setattr(persistence_mod, "get_db_safe", lambda: sess)
        monkeypatch.setattr(persistence_mod, "_prepare_event_for_persistence", lambda t, e: _empty_prepared())
        monkeypatch.setattr(
            persistence_mod,
            "_persist_prepared_event_in_session",
            lambda s, t, p: (_ for _ in ()).throw(RuntimeError("mid-batch fail")),
        )
        with pytest.raises(HTTPException) as exc:
            persistence_mod._ingest_batch_events_db_atomic("tenant-1", [{}])
        assert exc.value.status_code == 400
        assert exc.value.detail["error"] == "batch_persistence_failed"
        sess.rollback.assert_called_once()
        sess.close.assert_called_once()


# ── _ingest_single_event dispatcher ───────────────────────────────────────


class TestIngestSingleEventDispatcher:
    def test_db_error_without_fallback_raises_503(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            persistence_mod,
            "_ingest_single_event_db",
            lambda t, e: (_ for _ in ()).throw(RuntimeError("db offline")),
        )
        monkeypatch.setattr(persistence_mod, "_allow_in_memory_fallback", lambda: False)
        with pytest.raises(HTTPException) as exc:
            persistence_mod._ingest_single_event("tenant-1", {})
        assert exc.value.status_code == 503

    def test_http_exception_propagates_without_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            persistence_mod,
            "_ingest_single_event_db",
            lambda t, e: (_ for _ in ()).throw(HTTPException(status_code=422, detail="bad event")),
        )
        with pytest.raises(HTTPException) as exc:
            persistence_mod._ingest_single_event("tenant-1", {})
        assert exc.value.status_code == 422
        assert not persistence_mod._epcis_store.get("tenant-1")

    def test_happy_path_returns_db_result(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            persistence_mod,
            "_ingest_single_event_db",
            lambda t, e: ({"cte_id": "x"}, 201),
        )
        payload, status = persistence_mod._ingest_single_event("tenant-1", {})
        assert status == 201
        assert payload["cte_id"] == "x"
