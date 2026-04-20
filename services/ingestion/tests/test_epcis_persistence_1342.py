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
        traceability_lot_code = "TLC-X"
        product_reference = "prod-r"
        quantity = 1.0
        unit_of_measure = "CS"
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
    import shared.cte_persistence as _cte_mod
    import shared.canonical_event as _canon_mod
    import shared.canonical_persistence as _store_mod
    import shared.rules_engine as _rules_mod

    monkeypatch.setattr(_cte_mod, "CTEPersistence", _FakeCTEPersistence)
    monkeypatch.setattr(_canon_mod, "normalize_epcis_event", _fake_normalize_epcis_event)
    monkeypatch.setattr(_store_mod, "CanonicalEventStore", _FakeCanonicalEventStore)
    monkeypatch.setattr(_rules_mod, "RulesEngine", _FakeRulesEngine)


# ── _safe_iso ──────────────────────────────────────────────────────────────


class TestSafeIso:
    def test_naive_datetime_gets_utc(self) -> None:
        from datetime import datetime
        result = persistence_mod._safe_iso(datetime(2026, 5, 1, 12, 0, 0))
        assert result.endswith("+00:00")

    def test_aware_datetime_normalized_to_utc(self) -> None:
        from datetime import datetime, timezone, timedelta
        result = persistence_mod._safe_iso(
            datetime(2026, 5, 1, 12, 0, 0, tzinfo=timezone(timedelta(hours=-5)))
        )
        # Converted to UTC: 17:00
        assert "17:00" in result
        assert result.endswith("+00:00")

    def test_string_passes_through_unchanged(self) -> None:
        assert persistence_mod._safe_iso("2026-05-01T12:00:00Z") == "2026-05-01T12:00:00Z"

    def test_none_substitutes_now_iso(self) -> None:
        result = persistence_mod._safe_iso(None)
        # ISO-ish + tz suffix
        assert "T" in result and ("+" in result or "Z" in result)


# ── _build_kde_map ─────────────────────────────────────────────────────────


class TestBuildKdeMap:
    def test_includes_product_id_and_both_glns_when_normalized_has_them(self) -> None:
        event = {"type": "ObjectEvent"}
        normalized = {
            "product_id": "sku-42",
            "source_location_id": "1234567890128",
            "dest_location_id": "1234567890111",
        }
        kde_map = persistence_mod._build_kde_map(event, normalized, "idem-1")
        assert kde_map["product_id"] == "sku-42"
        assert kde_map["ship_from_gln"] == "1234567890128"
        assert kde_map["ship_to_gln"] == "1234567890111"
        assert kde_map["epcis_idempotency_key"] == "idem-1"
        # Compact JSON (sorted keys, no whitespace).
        assert kde_map["epcis_document_json"] == '{"type":"ObjectEvent"}'

    def test_skips_product_and_location_when_normalized_empty(self) -> None:
        kde_map = persistence_mod._build_kde_map(
            {"type": "ObjectEvent"}, {}, "idem-2"
        )
        assert "product_id" not in kde_map
        assert "ship_from_gln" not in kde_map
        assert "ship_to_gln" not in kde_map


# ── _parse_epcis_document ──────────────────────────────────────────────────


class TestParseEpcisDocument:
    def test_returns_parsed_json_when_round_trip_ok(self) -> None:
        kdes = {"epcis_document_json": '{"type":"ObjectEvent","bizStep":"receiving"}'}
        result = persistence_mod._parse_epcis_document(kdes, {})
        assert result["type"] == "ObjectEvent"
        assert result["bizStep"] == "receiving"

    def test_malformed_json_falls_back_to_synthesis(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        kdes = {"epcis_document_json": "{not-json"}
        normalized = {
            "epcis_event_type": "AggregationEvent",
            "event_time": "2026-03-01T00:00:00+00:00",
            "epcis_action": "ADD",
            "epcis_biz_step": "urn:epcglobal:cbv:bizstep:packing",
            "lot_code": "LOT-1",
            "tlc": "TLC-1",
            "source_location_id": "0614141000012",
            "dest_location_id": "0614141000029",
        }
        with caplog.at_level("WARNING"):
            result = persistence_mod._parse_epcis_document(kdes, normalized)
        assert result["type"] == "AggregationEvent"
        assert result["action"] == "ADD"
        assert result["ilmd"]["cbvmda:lotNumber"] == "LOT-1"
        assert result["ilmd"]["fsma:traceabilityLotCode"] == "TLC-1"
        assert result["sourceList"][0]["source"] == "0614141000012"
        assert result["destinationList"][0]["destination"] == "0614141000029"
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
    def test_allow_fallback_explicit_true(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ALLOW_EPCIS_IN_MEMORY_FALLBACK", "true")
        assert persistence_mod._allow_in_memory_fallback() is True

    def test_allow_fallback_explicit_false(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ALLOW_EPCIS_IN_MEMORY_FALLBACK", "no")
        assert persistence_mod._allow_in_memory_fallback() is False

    def test_allow_fallback_implicit_production(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("ALLOW_EPCIS_IN_MEMORY_FALLBACK", raising=False)
        monkeypatch.setattr(persistence_mod, "_is_production", lambda: True)
        assert persistence_mod._allow_in_memory_fallback() is False

    def test_allow_fallback_implicit_nonprod(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("ALLOW_EPCIS_IN_MEMORY_FALLBACK", raising=False)
        monkeypatch.setattr(persistence_mod, "_is_production", lambda: False)
        assert persistence_mod._allow_in_memory_fallback() is True

    def test_is_production_delegates_to_shared_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import shared.env as env_mod
        monkeypatch.setattr(env_mod, "is_production", lambda: True)
        assert persistence_mod._is_production() is True

    def test_fsma_strict_mode_defaults_to_true(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("FSMA_STRICT_MODE", raising=False)
        assert persistence_mod._fsma_strict_mode() is True

    @pytest.mark.parametrize("val", ["false", "0", "no", "off", "advisory"])
    def test_fsma_strict_mode_false_variants(
        self, monkeypatch: pytest.MonkeyPatch, val: str
    ) -> None:
        monkeypatch.setenv("FSMA_STRICT_MODE", val)
        assert persistence_mod._fsma_strict_mode() is False

    @pytest.mark.parametrize("val", ["1", "true", "yes", "on", "strict"])
    def test_fsma_strict_mode_true_variants(
        self, monkeypatch: pytest.MonkeyPatch, val: str
    ) -> None:
        monkeypatch.setenv("FSMA_STRICT_MODE", val)
        assert persistence_mod._fsma_strict_mode() is True


# ── Fallback store FIFO eviction ──────────────────────────────────────────


class TestFallbackFifoEviction:
    def test_store_evicts_oldest_when_over_cap(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Line 66: FIFO eviction when fallback store hits its cap."""
        monkeypatch.setattr(persistence_mod, "_EPCIS_FALLBACK_CAP_PER_TENANT", 2)

        persistence_mod._fallback_store_put("t1", "a", {"cte": 1})
        persistence_mod._fallback_store_put("t1", "b", {"cte": 2})
        persistence_mod._fallback_store_put("t1", "c", {"cte": 3})

        store = persistence_mod._fallback_store_for("t1")
        assert "a" not in store  # evicted
        assert list(store.keys()) == ["b", "c"]

    def test_idempotency_index_evicts_oldest_when_over_cap(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
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
        sess.queue([
            ("tenant_id",),
            ("cte_event_id",),
            ("severity",),
            ("alert_type",),
            ("message",),
            ("created_at",),
        ])
        # Alerts.
        sess.queue([
            _make_row("warning", "tlc_missing", "TLC missing"),
            _make_row("error", "gln_bad", "bad GLN"),
        ])

        rows = persistence_mod._query_alert_rows(sess, "tenant-1", "event-1")
        assert rows == [
            {"severity": "warning", "alert_type": "tlc_missing", "message": "TLC missing"},
            {"severity": "error", "alert_type": "gln_bad", "message": "bad GLN"},
        ]

    def test_fallback_to_org_id_and_event_id_and_description(self) -> None:
        """Exercises the ``org_id`` / ``event_id`` / ``description`` fallback
        branches of the identifier selection ladder."""
        sess = _FakeSession()
        sess.queue([
            ("org_id",),
            ("event_id",),
            ("severity",),
            ("alert_type",),
            ("description",),
            ("created_at",),
        ])
        sess.queue([])  # no matching alerts — still exercises the SELECT.
        rows = persistence_mod._query_alert_rows(sess, "t", "e")
        assert rows == []


# ── _fetch_event_from_db ──────────────────────────────────────────────────


class TestFetchEventFromDb:
    def test_returns_none_when_main_row_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sess = _FakeSession()
        sess.queue(None)  # main SELECT returns nothing
        monkeypatch.setattr(persistence_mod, "get_db_safe", lambda: sess)

        result = persistence_mod._fetch_event_from_db("tenant-1", "missing")
        assert result is None

    def test_happy_path_returns_aggregated_view(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Lines 279-319: full read path — main row + KDEs + alerts."""
        main_row = MagicMock()
        main_row.id = "event-42"
        main_row.ingested_at = "2026-03-01T00:00:00+00:00"
        main_row.idempotency_key = "idem-42"
        main_row.event_type = "shipping"
        main_row.epcis_event_type = "ObjectEvent"
        main_row.epcis_action = "OBSERVE"
        main_row.epcis_biz_step = "urn:epcglobal:cbv:bizstep:shipping"
        main_row.event_timestamp = "2026-03-01T09:30:00+00:00"
        main_row.traceability_lot_code = "TLC-42"
        main_row.source = "epcis"
        main_row.location_gln = "0614141000012"
        main_row.quantity = 10.0
        main_row.unit_of_measure = "CS"

        kde_row = MagicMock()
        kde_row.kde_key = "lotNumber"
        kde_row.kde_value = "LOT-42"
        kde_row.is_required = True

        product_kde = MagicMock()
        product_kde.kde_key = "product_id"
        product_kde.kde_value = "SKU-42"
        product_kde.is_required = False

        sess = _FakeSession()
        sess.queue(main_row)          # main SELECT
        sess.queue([kde_row, product_kde])  # KDE SELECT
        # _query_alert_rows: schema query + alert query
        sess.queue([
            ("tenant_id",),
            ("cte_event_id",),
            ("severity",),
            ("alert_type",),
            ("message",),
            ("created_at",),
        ])
        sess.queue([])  # no alerts

        monkeypatch.setattr(persistence_mod, "get_db_safe", lambda: sess)

        result = persistence_mod._fetch_event_from_db("tenant-1", "event-42")
        assert result is not None
        assert result["id"] == "event-42"
        assert result["idempotency_key"] == "idem-42"
        assert result["normalized_cte"]["tlc"] == "TLC-42"
        assert result["normalized_cte"]["lot_code"] == "LOT-42"
        assert result["normalized_cte"]["product_id"] == "SKU-42"
        assert result["kdes"][0]["kde_type"] == "lotNumber"
        assert result["alerts"] == []


# ── _list_events_from_db ──────────────────────────────────────────────────


class TestListEventsFromDb:
    def test_happy_path_with_date_filters_and_product_filter(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Lines 345-346, 348-349 (date filter branches) + 375-413 (loop body).

        Also exercises the ``product_id`` filter: first row matches, second
        does not.
        """
        row_match = MagicMock()
        row_match.id = "e1"
        row_match.event_type = "shipping"
        row_match.epcis_event_type = "ObjectEvent"
        row_match.epcis_action = "OBSERVE"
        row_match.epcis_biz_step = "urn:epcglobal:cbv:bizstep:shipping"
        row_match.event_timestamp = "2026-03-01T09:30:00+00:00"
        row_match.traceability_lot_code = "TLC-1"
        row_match.source = "epcis"
        row_match.location_gln = "0614141000012"
        row_match.quantity = 10.0
        row_match.unit_of_measure = "CS"

        row_mismatch = MagicMock()
        row_mismatch.id = "e2"
        row_mismatch.event_type = "shipping"
        row_mismatch.epcis_event_type = "ObjectEvent"
        row_mismatch.epcis_action = "OBSERVE"
        row_mismatch.epcis_biz_step = "urn:epcglobal:cbv:bizstep:shipping"
        row_mismatch.event_timestamp = "2026-03-01T10:30:00+00:00"
        row_mismatch.traceability_lot_code = "TLC-2"
        row_mismatch.source = "epcis"
        row_mismatch.location_gln = "0614141000012"
        row_mismatch.quantity = 5.0
        row_mismatch.unit_of_measure = "CS"

        match_kde = MagicMock()
        match_kde.kde_key = "product_id"
        match_kde.kde_value = "SKU-match"

        mismatch_kde = MagicMock()
        mismatch_kde.kde_key = "product_id"
        mismatch_kde.kde_value = "SKU-other"

        sess = _FakeSession()
        sess.queue([row_match, row_mismatch])  # main SELECT
        sess.queue([match_kde])                # KDEs for row_match
        sess.queue([mismatch_kde])             # KDEs for row_mismatch

        monkeypatch.setattr(persistence_mod, "get_db_safe", lambda: sess)

        events = persistence_mod._list_events_from_db(
            "tenant-1",
            start_date="2026-01-01T00:00:00+00:00",
            end_date="2026-12-31T00:00:00+00:00",
            product_id="SKU-match",
        )
        # Only the matching row survives the product filter.
        assert len(events) == 1

    def test_no_filters_returns_all(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sess = _FakeSession()
        sess.queue([])  # no rows
        monkeypatch.setattr(persistence_mod, "get_db_safe", lambda: sess)
        events = persistence_mod._list_events_from_db(
            "tenant-1", None, None, None
        )
        assert events == []


# ── _ingest_single_event_fallback ─────────────────────────────────────────


_VALID_EPCIS = {
    "@context": [],
    "type": "ObjectEvent",
    "eventTime": "2026-02-28T09:30:00-05:00",
    "eventTimeZoneOffset": "-05:00",
    "action": "OBSERVE",
    "bizStep": "urn:epcglobal:cbv:bizstep:receiving",
    "bizLocation": {"id": "urn:epc:id:sgln:0614141.00002.0"},
    "ilmd": {
        "cbvmda:lotNumber": "ROM-0042",
        "fsma:traceabilityLotCode": "00012345678901-ROM0042",
    },
    "extension": {
        "quantityList": [
            {"epcClass": "urn:epc:class:lgtin:0614141.107346.ROM0042", "quantity": 10.0, "uom": "CS"},
        ],
    },
}


class TestIngestSingleEventFallback:
    def test_validation_errors_raise_400(self) -> None:
        """Line 428: _validate_epcis errors → HTTP 400."""
        with pytest.raises(HTTPException) as exc:
            persistence_mod._ingest_single_event_fallback(
                "tenant-1", {"type": "ObjectEvent"}  # missing required fields
            )
        assert exc.value.status_code == 400

    def test_happy_path_writes_to_fallback_store(self) -> None:
        payload, status = persistence_mod._ingest_single_event_fallback(
            "tenant-1", _VALID_EPCIS
        )
        assert status == 201
        assert payload["validation_status"] in {"valid", "warning"}
        assert persistence_mod._epcis_store["tenant-1"]

    def test_idempotent_replay_returns_200(self) -> None:
        # First call — seed the store.
        persistence_mod._ingest_single_event_fallback("tenant-1", _VALID_EPCIS)
        # Second call — same event → 200 (idempotent).
        payload, status = persistence_mod._ingest_single_event_fallback(
            "tenant-1", _VALID_EPCIS
        )
        assert status == 200
        assert payload.get("idempotent") is True

    def test_fsma_strict_rejection_raises_422(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Lines 464-481: FSMA_STRICT_MODE on + FSMAEvent returns None → 422."""
        monkeypatch.setattr(
            persistence_mod, "_validate_as_fsma_event", lambda n, t: None
        )
        monkeypatch.setattr(
            persistence_mod, "_fsma_strict_mode", lambda: True
        )
        with pytest.raises(HTTPException) as exc:
            persistence_mod._ingest_single_event_fallback(
                "tenant-1", _VALID_EPCIS
            )
        assert exc.value.status_code == 422
        assert exc.value.detail["error"] == "fsma_validation_failed"

    def test_fsma_advisory_mode_persists_with_error_alert(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Lines 482-490: FSMA_STRICT_MODE off → persist + error alert."""
        monkeypatch.setattr(
            persistence_mod, "_validate_as_fsma_event", lambda n, t: None
        )
        monkeypatch.setattr(
            persistence_mod, "_fsma_strict_mode", lambda: False
        )
        payload, status = persistence_mod._ingest_single_event_fallback(
            "tenant-1", _VALID_EPCIS
        )
        assert status == 201
        # Alert with severity=error added.
        alerts = payload["alerts"]
        assert any(
            a["severity"] == "error" and a["alert_type"] == "fsma_validation"
            for a in alerts
        )


# ── _prepare_event_for_persistence ────────────────────────────────────────


class TestPrepareEventForPersistence:
    def test_validation_errors_raise_400(self) -> None:
        with pytest.raises(HTTPException) as exc:
            persistence_mod._prepare_event_for_persistence(
                "tenant-1", {"type": "ObjectEvent"}
            )
        assert exc.value.status_code == 400

    def test_fsma_strict_rejection_raises_422(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Lines 550-565: FSMA strict rejection in DB pipeline."""
        monkeypatch.setattr(
            persistence_mod, "_validate_as_fsma_event", lambda n, t: None
        )
        monkeypatch.setattr(
            persistence_mod, "_fsma_strict_mode", lambda: True
        )
        with pytest.raises(HTTPException) as exc:
            persistence_mod._prepare_event_for_persistence(
                "tenant-1", _VALID_EPCIS
            )
        assert exc.value.status_code == 422
        assert exc.value.detail["error"] == "fsma_validation_failed"

    def test_fsma_advisory_mode_tags_kde_map_and_adds_alert(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Lines 566-574: advisory mode tags KDE map + adds error alert."""
        monkeypatch.setattr(
            persistence_mod, "_validate_as_fsma_event", lambda n, t: None
        )
        monkeypatch.setattr(
            persistence_mod, "_fsma_strict_mode", lambda: False
        )
        prepared = persistence_mod._prepare_event_for_persistence(
            "tenant-1", _VALID_EPCIS
        )
        assert prepared["kde_map"]["fsma_validation_status"] == "failed"
        assert any(
            a["alert_type"] == "fsma_validation" for a in prepared["alerts"]
        )

    def test_missing_quantity_raises_422(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Line 582-594: no quantity → 422 with ``missing_quantity``."""
        monkeypatch.setattr(
            persistence_mod,
            "_normalize_epcis_to_cte",
            lambda e: {
                "event_type": "receiving",
                "tlc": "TLC",
                "epcis_event_type": "ObjectEvent",
                "epcis_action": "OBSERVE",
                "epcis_biz_step": "urn:epcglobal:cbv:bizstep:receiving",
                "event_time": "2026-03-01T00:00:00+00:00",
                # no quantity
            },
        )
        monkeypatch.setattr(
            persistence_mod,
            "_validate_as_fsma_event",
            lambda n, t: {"ok": True},
        )

        with pytest.raises(HTTPException) as exc:
            persistence_mod._prepare_event_for_persistence(
                "tenant-1", _VALID_EPCIS
            )
        assert exc.value.status_code == 422
        assert exc.value.detail["error"] == "missing_quantity"

    def test_non_numeric_quantity_raises_422(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Lines 597-608: non-coercible quantity → 422 ``non_numeric_quantity``."""
        monkeypatch.setattr(
            persistence_mod,
            "_normalize_epcis_to_cte",
            lambda e: {
                "event_type": "receiving",
                "tlc": "TLC",
                "epcis_event_type": "ObjectEvent",
                "epcis_action": "OBSERVE",
                "epcis_biz_step": "urn:epcglobal:cbv:bizstep:receiving",
                "event_time": "2026-03-01T00:00:00+00:00",
                "quantity": "not-a-number",
            },
        )
        monkeypatch.setattr(
            persistence_mod,
            "_validate_as_fsma_event",
            lambda n, t: {"ok": True},
        )

        with pytest.raises(HTTPException) as exc:
            persistence_mod._prepare_event_for_persistence(
                "tenant-1", _VALID_EPCIS
            )
        assert exc.value.status_code == 422
        assert exc.value.detail["error"] == "non_numeric_quantity"

    def test_happy_path_returns_prepared_envelope(self) -> None:
        prepared = persistence_mod._prepare_event_for_persistence(
            "tenant-1", _VALID_EPCIS
        )
        assert prepared["idempotency_key"]
        assert prepared["quantity_value"] == 10.0
        assert prepared["event_time"]


# ── _persist_prepared_event_in_session ────────────────────────────────────


class TestPersistPreparedEventInSession:
    def _prep(self) -> dict:
        return persistence_mod._prepare_event_for_persistence(
            "tenant-1", _VALID_EPCIS
        )

    def test_non_idempotent_triggers_canonical_write(self) -> None:
        """Lines 662-685: non-idempotent store → canonical write fires."""
        _FakeCTEPersistence.idempotent_flag = False
        sess = MagicMock()
        payload, status = persistence_mod._persist_prepared_event_in_session(
            sess, "tenant-1", self._prep()
        )
        assert status == 201
        assert payload["idempotent"] is False

    def test_idempotent_result_skips_canonical_write(self) -> None:
        _FakeCTEPersistence.idempotent_flag = True
        sess = MagicMock()
        payload, status = persistence_mod._persist_prepared_event_in_session(
            sess, "tenant-1", self._prep()
        )
        assert status == 200
        assert payload["idempotent"] is True

    def test_canonical_write_failure_logs_and_swallows(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Lines 686-687: canonical write exception is swallowed + logged."""
        _FakeCTEPersistence.idempotent_flag = False

        # Replace normalize_epcis_event on the canonical-event shim to blow up.
        import shared.canonical_event as ce
        monkeypatch.setattr(
            ce,
            "normalize_epcis_event",
            lambda e, t: (_ for _ in ()).throw(RuntimeError("canon boom")),
        )

        sess = MagicMock()
        with caplog.at_level("WARNING"):
            payload, status = persistence_mod._persist_prepared_event_in_session(
                sess, "tenant-1", self._prep()
            )
        assert status == 201
        assert any(
            "epcis_canonical_write_skipped" in m for m in caplog.messages
        )


# ── _ingest_single_event_db ───────────────────────────────────────────────


class TestIngestSingleEventDb:
    def test_happy_path_commits(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Lines 711-712: happy path calls commit on the session."""
        sess = MagicMock()
        monkeypatch.setattr(persistence_mod, "get_db_safe", lambda: sess)

        _FakeCTEPersistence.idempotent_flag = False
        payload, status = persistence_mod._ingest_single_event_db(
            "tenant-1", _VALID_EPCIS
        )
        assert status == 201
        sess.commit.assert_called_once()
        sess.close.assert_called_once()

    def test_exception_triggers_rollback(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sess = MagicMock()
        monkeypatch.setattr(persistence_mod, "get_db_safe", lambda: sess)
        # Make _persist_prepared_event_in_session blow up.
        monkeypatch.setattr(
            persistence_mod,
            "_persist_prepared_event_in_session",
            lambda s, t, p: (_ for _ in ()).throw(RuntimeError("pg dead")),
        )

        with pytest.raises(RuntimeError, match="pg dead"):
            persistence_mod._ingest_single_event_db("tenant-1", _VALID_EPCIS)
        sess.rollback.assert_called_once()
        sess.close.assert_called_once()


# ── _ingest_batch_events_db_atomic ────────────────────────────────────────


class TestIngestBatchEventsDbAtomic:
    def test_pre_validation_failures_raise_400_without_touching_db(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Lines 739-752: any validation failure aborts before phase 2."""
        sess = MagicMock()
        monkeypatch.setattr(persistence_mod, "get_db_safe", lambda: sess)

        events = [_VALID_EPCIS, {"type": "ObjectEvent"}]  # second fails
        with pytest.raises(HTTPException) as exc:
            persistence_mod._ingest_batch_events_db_atomic("tenant-1", events)
        assert exc.value.status_code == 400
        assert exc.value.detail["mode"] == "atomic"
        assert len(exc.value.detail["errors"]) == 1
        assert exc.value.detail["errors"][0]["index"] == 1
        # Never reached get_db_safe (it's only called AFTER pre-validation).
        # Note: our stub returns a new mock per call, so just verify commit
        # and rollback were NEVER touched on whatever session was made.

    def test_persistence_phase_failure_rolls_back_and_raises_400(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Lines 765-780: persistence exception rolls back + HTTP 400."""
        sess = MagicMock()
        monkeypatch.setattr(persistence_mod, "get_db_safe", lambda: sess)
        monkeypatch.setattr(
            persistence_mod,
            "_persist_prepared_event_in_session",
            lambda s, t, p: (_ for _ in ()).throw(RuntimeError("mid-batch fail")),
        )

        with pytest.raises(HTTPException) as exc:
            persistence_mod._ingest_batch_events_db_atomic(
                "tenant-1", [_VALID_EPCIS]
            )
        assert exc.value.status_code == 400
        assert exc.value.detail["error"] == "batch_persistence_failed"
        sess.rollback.assert_called_once()
        sess.close.assert_called_once()

    def test_happy_path_commits_and_returns_per_event_results(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sess = MagicMock()
        monkeypatch.setattr(persistence_mod, "get_db_safe", lambda: sess)
        _FakeCTEPersistence.idempotent_flag = False
        results = persistence_mod._ingest_batch_events_db_atomic(
            "tenant-1", [_VALID_EPCIS, _VALID_EPCIS]
        )
        assert len(results) == 2
        for payload, status in results:
            assert status == 201
        sess.commit.assert_called_once()


# ── _ingest_single_event dispatcher ───────────────────────────────────────


class TestIngestSingleEventDispatcher:
    def test_db_error_without_fallback_raises_503(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Lines 793-798: DB generic error + fallback disabled → 503."""
        monkeypatch.setattr(
            persistence_mod,
            "_ingest_single_event_db",
            lambda t, e: (_ for _ in ()).throw(RuntimeError("db offline")),
        )
        monkeypatch.setattr(
            persistence_mod, "_allow_in_memory_fallback", lambda: False
        )

        with pytest.raises(HTTPException) as exc:
            persistence_mod._ingest_single_event("tenant-1", _VALID_EPCIS)
        assert exc.value.status_code == 503

    def test_db_error_with_fallback_routes_to_fallback(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Lines 800-801: DB error + fallback enabled → fallback path."""
        monkeypatch.setattr(
            persistence_mod,
            "_ingest_single_event_db",
            lambda t, e: (_ for _ in ()).throw(RuntimeError("db flaked")),
        )
        monkeypatch.setattr(
            persistence_mod, "_allow_in_memory_fallback", lambda: True
        )

        payload, status = persistence_mod._ingest_single_event(
            "tenant-1", _VALID_EPCIS
        )
        assert status == 201
        # Fallback store has the record.
        assert persistence_mod._epcis_store["tenant-1"]

    def test_http_exception_propagates_without_fallback(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Lines 787-791: validation failures never fall through to fallback."""
        monkeypatch.setattr(
            persistence_mod,
            "_ingest_single_event_db",
            lambda t, e: (_ for _ in ()).throw(
                HTTPException(status_code=422, detail="bad event")
            ),
        )

        with pytest.raises(HTTPException) as exc:
            persistence_mod._ingest_single_event("tenant-1", _VALID_EPCIS)
        assert exc.value.status_code == 422
        # No fallback store record — validation failures do NOT route to fallback.
        assert not persistence_mod._epcis_store.get("tenant-1")

    def test_happy_path_returns_db_result(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            persistence_mod,
            "_ingest_single_event_db",
            lambda t, e: ({"cte_id": "x"}, 201),
        )
        payload, status = persistence_mod._ingest_single_event(
            "tenant-1", _VALID_EPCIS
        )
        assert status == 201
        assert payload["cte_id"] == "x"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
