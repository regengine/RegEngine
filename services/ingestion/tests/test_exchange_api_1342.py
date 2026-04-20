"""Unit tests for ``app.exchange_api`` targeting full-line coverage (#1342).

The existing ``tests/test_exchange_api.py`` file already covers the
in-memory fallback end-to-end flow. This file drives the remaining
branches: the helper functions that shape SQL rows into JSON packages,
the DB-backed store/load paths, and the endpoint branches that only
fire when the database is reachable *or* the fallback is explicitly
disabled.

All DB interactions go through a tiny ``_FakeSession`` stub — we never
touch a real SQLAlchemy session in these tests.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

from app.authz import IngestionPrincipal, get_ingestion_principal
import app.exchange_api as exchange_api
from app.exchange_api import (
    ExchangeSendRequest,
    _allow_in_memory_fallback,
    _build_package,
    _build_records,
    _ensure_exchange_table,
    _exchange_store,
    _is_production,
    _load_packages_db,
    _load_packages_fallback,
    _query_shipping_rows,
    _store_package_db,
    _store_package_fallback,
    router as exchange_router,
)


# ---------------------------------------------------------------------------
# Fake SQLAlchemy session
# ---------------------------------------------------------------------------


class _FakeResult:
    """Matches the ``.fetchall()`` contract used by exchange_api."""

    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def fetchall(self) -> list[Any]:
        return list(self._rows)


class _FakeSession:
    """Minimal SQLAlchemy session stub.

    ``execute_queue`` is popped from left-to-right each time ``execute``
    is called. Entries can be:
      - a list of rows  -> returned via ``fetchall``
      - ``None``        -> returned as empty ``fetchall``
      - an Exception    -> raised to simulate DB failure

    All calls are recorded in ``calls`` so tests can assert ordering /
    arguments.
    """

    def __init__(self, execute_queue: list[Any] | None = None) -> None:
        self.execute_queue: list[Any] = list(execute_queue or [])
        self.calls: list[tuple[str, Any]] = []
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def execute(self, stmt: Any, params: Any | None = None) -> _FakeResult:
        self.calls.append(("execute", (str(stmt), params)))
        if not self.execute_queue:
            # Default: succeed with no rows.
            return _FakeResult([])
        nxt = self.execute_queue.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        if nxt is None:
            return _FakeResult([])
        if isinstance(nxt, list):
            return _FakeResult(nxt)
        # Single row shorthand.
        return _FakeResult([nxt])

    def commit(self) -> None:
        self.calls.append(("commit", None))
        self.committed = True

    def rollback(self) -> None:
        self.calls.append(("rollback", None))
        self.rolled_back = True

    def close(self) -> None:
        self.calls.append(("close", None))
        self.closed = True


def _make_row(**overrides: Any) -> SimpleNamespace:
    """Build a shipping-row stand-in for ``_build_records`` / query fetch."""
    defaults = dict(
        id="00000000-0000-0000-0000-00000000abcd",
        traceability_lot_code="LOT-001",
        product_description="Romaine",
        quantity=5.0,
        unit_of_measure="case",
        event_timestamp=datetime(2026, 4, 19, 12, 0, tzinfo=timezone.utc),
        location_gln="0810000000000",
        location_name="Farm A",
        source_event_id="src-1",
        source="epcis",
        sha256_hash="hash-1",
        chain_hash="chain-1",
        kdes={
            "ship_from_gln": "0810000000001",
            "ship_from_location": "Packhouse",
            "ship_to_gln": "0810000000002",
            "ship_to_location": "Distributor",
            "receiving_location": "DC",
            "tlc_source_gln": "0810000000003",
            "tlc_source_fda_reg": "FDA-123",
            "immediate_previous_source": "Upstream",
            "reference_document_number": "PO-9",
            "carrier": "FedEx",
            "lot_size": "50",  # extra KDE that lands in additional_kdes
        },
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# `_is_production` + `_allow_in_memory_fallback`
# ---------------------------------------------------------------------------


class TestIsProduction:
    def test_delegates_to_shared_env_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import shared.env as env_mod
        monkeypatch.setattr(env_mod, "is_production", lambda: True)
        assert _is_production() is True

    def test_delegates_to_shared_env_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import shared.env as env_mod
        monkeypatch.setattr(env_mod, "is_production", lambda: False)
        assert _is_production() is False


class TestAllowInMemoryFallback:
    def test_explicit_env_var_true_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ALLOW_EXCHANGE_IN_MEMORY_FALLBACK", "TRUE")
        import shared.env as env_mod
        monkeypatch.setattr(env_mod, "is_production", lambda: True)
        assert _allow_in_memory_fallback() is True

    def test_explicit_env_var_yes_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ALLOW_EXCHANGE_IN_MEMORY_FALLBACK", "yes")
        assert _allow_in_memory_fallback() is True

    def test_explicit_env_var_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ALLOW_EXCHANGE_IN_MEMORY_FALLBACK", "false")
        import shared.env as env_mod
        monkeypatch.setattr(env_mod, "is_production", lambda: False)
        assert _allow_in_memory_fallback() is False

    def test_env_var_unknown_string_is_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ALLOW_EXCHANGE_IN_MEMORY_FALLBACK", "maybe")
        import shared.env as env_mod
        monkeypatch.setattr(env_mod, "is_production", lambda: False)
        assert _allow_in_memory_fallback() is False

    def test_no_env_var_non_prod(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ALLOW_EXCHANGE_IN_MEMORY_FALLBACK", raising=False)
        import shared.env as env_mod
        monkeypatch.setattr(env_mod, "is_production", lambda: False)
        assert _allow_in_memory_fallback() is True

    def test_no_env_var_prod(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ALLOW_EXCHANGE_IN_MEMORY_FALLBACK", raising=False)
        import shared.env as env_mod
        monkeypatch.setattr(env_mod, "is_production", lambda: True)
        assert _allow_in_memory_fallback() is False


# ---------------------------------------------------------------------------
# `_ensure_exchange_table`
# ---------------------------------------------------------------------------


class TestEnsureExchangeTable:
    def test_issues_create_schema_and_table_ddl(self) -> None:
        session = _FakeSession()
        _ensure_exchange_table(session)
        assert len(session.calls) == 1
        stmt_str, params = session.calls[0][1]
        assert "CREATE SCHEMA IF NOT EXISTS fsma" in stmt_str
        assert "fsma.exchange_packages" in stmt_str
        assert "idx_exchange_packages_receiver_status" in stmt_str
        # DDL is a one-shot execute; no bind params.
        assert params is None


# ---------------------------------------------------------------------------
# `_query_shipping_rows`
# ---------------------------------------------------------------------------


class TestQueryShippingRows:
    def test_rejects_when_no_filters_provided(self) -> None:
        session = _FakeSession()
        req = ExchangeSendRequest(receiver_tenant_id="tenant-recv")
        with pytest.raises(HTTPException) as excinfo:
            _query_shipping_rows(session, "tenant-send", req)
        assert excinfo.value.status_code == 400
        assert "traceability_lot_code" in str(excinfo.value.detail)
        # The helper bails before running SQL.
        assert session.calls == []

    def test_raises_404_when_no_matches(self) -> None:
        session = _FakeSession(execute_queue=[[]])
        req = ExchangeSendRequest(
            receiver_tenant_id="tenant-recv",
            traceability_lot_code="LOT-001",
        )
        with pytest.raises(HTTPException) as excinfo:
            _query_shipping_rows(session, "tenant-send", req)
        assert excinfo.value.status_code == 404
        assert "No shipping CTEs" in str(excinfo.value.detail)

    def test_happy_path_includes_all_filters(self) -> None:
        row = _make_row()
        session = _FakeSession(execute_queue=[[row]])
        req = ExchangeSendRequest(
            receiver_tenant_id="tenant-recv",
            traceability_lot_code="LOT-001",
            lot_codes=["LOT-002", "LOT-001", ""],  # dedup + drop blanks
            event_ids=["evt-a", "", "evt-b"],
            date_from="2026-01-01T00:00:00Z",
            date_to="2026-04-19T00:00:00Z",
            max_events=42,
        )
        rows = _query_shipping_rows(session, "tenant-send", req)
        assert rows == [row]
        # Introspect the query that was sent.
        stmt_str, params = session.calls[0][1]
        assert "e.traceability_lot_code = ANY(:tlcs)" in stmt_str
        assert "e.id::text = ANY(:event_ids)" in stmt_str
        assert "e.event_timestamp >= :date_from" in stmt_str
        assert "e.event_timestamp <= :date_to" in stmt_str
        assert params["tenant_id"] == "tenant-send"
        assert params["limit"] == 42
        assert params["tlcs"] == ["LOT-001", "LOT-002"]  # sorted + deduped
        assert params["event_ids"] == ["evt-a", "evt-b"]
        assert params["date_from"] == "2026-01-01T00:00:00Z"
        assert params["date_to"] == "2026-04-19T00:00:00Z"

    def test_only_event_ids_omits_tlc_clause(self) -> None:
        row = _make_row(traceability_lot_code=None)
        session = _FakeSession(execute_queue=[[row]])
        req = ExchangeSendRequest(
            receiver_tenant_id="tenant-recv",
            event_ids=["evt-1"],
        )
        rows = _query_shipping_rows(session, "tenant-send", req)
        assert rows == [row]
        stmt_str, params = session.calls[0][1]
        assert "e.traceability_lot_code = ANY(:tlcs)" not in stmt_str
        assert "tlcs" not in params

    def test_only_tlc_omits_event_id_clause(self) -> None:
        row = _make_row()
        session = _FakeSession(execute_queue=[[row]])
        req = ExchangeSendRequest(
            receiver_tenant_id="tenant-recv",
            traceability_lot_code="LOT-001",
        )
        rows = _query_shipping_rows(session, "tenant-send", req)
        assert rows == [row]
        stmt_str, params = session.calls[0][1]
        assert "e.id::text = ANY(:event_ids)" not in stmt_str
        assert "event_ids" not in params
        assert "date_from" not in params
        assert "date_to" not in params


# ---------------------------------------------------------------------------
# `_build_records`
# ---------------------------------------------------------------------------


class TestBuildRecords:
    def test_basic_record_shape(self) -> None:
        row = _make_row()
        records = _build_records([row])
        assert len(records) == 1
        record = records[0]
        assert record["cte_event_id"] == row.id
        assert record["traceability_lot_code"] == "LOT-001"
        assert record["event_type"] == "shipping"
        assert record["event_timestamp"] == row.event_timestamp.isoformat()
        assert record["product_description"] == "Romaine"
        assert record["quantity"] == 5.0
        assert record["unit_of_measure"] == "case"
        # KDEs > row fallbacks.
        assert record["ship_from"] == {
            "gln": "0810000000001",
            "name": "Packhouse",
        }
        assert record["ship_to"] == {
            "gln": "0810000000002",
            "name": "Distributor",
        }
        assert record["tlc_source"] == {
            "gln": "0810000000003",
            "fda_registration": "FDA-123",
            "immediate_previous_source": "Upstream",
        }
        assert record["reference_document_number"] == "PO-9"
        assert record["carrier"] == "FedEx"
        assert record["integrity"] == {
            "record_hash": "hash-1",
            "chain_hash": "chain-1",
        }
        # Only unknown KDEs survive in additional_kdes.
        assert record["additional_kdes"] == {"lot_size": "50"}
        assert record["source"] == "epcis"

    def test_ship_from_falls_back_to_location_fields(self) -> None:
        row = _make_row(kdes={})
        records = _build_records([row])
        record = records[0]
        assert record["ship_from"] == {
            "gln": row.location_gln,
            "name": row.location_name,
        }
        # No ship_to_location / receiving_location -> both None.
        assert record["ship_to"] == {"gln": None, "name": None}
        assert record["tlc_source"] == {
            "gln": None,
            "fda_registration": None,
            "immediate_previous_source": None,
        }
        # reference_document_number falls back to source_event_id.
        assert record["reference_document_number"] == row.source_event_id
        assert record["carrier"] is None
        assert record["additional_kdes"] == {}

    def test_ship_to_name_falls_back_to_receiving_location(self) -> None:
        row = _make_row(kdes={"receiving_location": "Fallback DC"})
        records = _build_records([row])
        assert records[0]["ship_to"]["name"] == "Fallback DC"

    def test_handles_missing_timestamp_and_quantity(self) -> None:
        row = _make_row(event_timestamp=None, quantity=None, kdes=None)
        records = _build_records([row])
        record = records[0]
        assert record["event_timestamp"] is None
        assert record["quantity"] is None

    def test_empty_rows_returns_empty_list(self) -> None:
        assert _build_records([]) == []


# ---------------------------------------------------------------------------
# `_build_package`
# ---------------------------------------------------------------------------


class TestBuildPackage:
    def test_returns_uuid_hash_and_package(self) -> None:
        row_a = _make_row(traceability_lot_code="LOT-B")
        row_b = _make_row(traceability_lot_code="LOT-A")
        req = ExchangeSendRequest(
            receiver_tenant_id="tenant-recv",
            traceability_lot_code="LOT-A",
            receiver_email="to@example.com",
        )
        package_id, package_hash, package = _build_package(
            "tenant-send", req, [row_a, row_b]
        )
        # UUID format.
        assert len(package_id) == 36 and package_id.count("-") == 4
        assert len(package_hash) == 64
        assert package["package_id"] == package_id
        assert package["package_hash"] == package_hash
        assert package["package_version"] == "1.0"
        assert package["sender_tenant_id"] == "tenant-send"
        assert package["receiver_tenant_id"] == "tenant-recv"
        assert package["notification_target"] == "to@example.com"
        assert package["summary"]["event_count"] == 2
        # Lot codes are sorted, deduped.
        assert package["summary"]["traceability_lot_codes"] == ["LOT-A", "LOT-B"]
        assert package["summary"]["tlc_source_propagated"] is True
        assert package["summary"]["generated_from"] == "shipping_ctes"
        assert len(package["records"]) == 2

    def test_hash_is_stable_for_same_input(self) -> None:
        row = _make_row()
        req = ExchangeSendRequest(
            receiver_tenant_id="tenant-recv",
            traceability_lot_code="LOT-001",
        )
        _, hash_a, pkg_a = _build_package("tenant-send", req, [row])
        _, hash_b, pkg_b = _build_package("tenant-send", req, [row])
        # Hashes differ because package_id (UUID) is part of the payload —
        # but the non-id fields must be identical.
        assert hash_a != hash_b
        for key in ("summary", "records", "sender_tenant_id", "receiver_tenant_id"):
            assert pkg_a[key] == pkg_b[key]


# ---------------------------------------------------------------------------
# `_store_package_db`
# ---------------------------------------------------------------------------


class TestStorePackageDb:
    def test_happy_path_commits_and_closes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        session = _FakeSession()
        monkeypatch.setattr(exchange_api, "get_db_safe", lambda: session)
        req = ExchangeSendRequest(
            receiver_tenant_id="tenant-recv",
            traceability_lot_code="LOT-001",
            receiver_email="n@x.io",
        )
        package = {
            "package_id": "pkg-1",
            "summary": {
                "event_count": 3,
                "traceability_lot_codes": ["LOT-001"],
            },
            "sender_tenant_id": "tenant-send",
            "receiver_tenant_id": "tenant-recv",
        }
        _store_package_db(
            "tenant-send", req, "pkg-1", "deadbeef", package
        )
        assert session.committed is True
        assert session.rolled_back is False
        assert session.closed is True
        # DDL + INSERT -> exactly two execute calls.
        execute_calls = [c for c in session.calls if c[0] == "execute"]
        assert len(execute_calls) == 2
        insert_stmt, insert_params = execute_calls[1][1]
        assert "INSERT INTO fsma.exchange_packages" in insert_stmt
        assert insert_params["id"] == "pkg-1"
        assert insert_params["sender_tenant_id"] == "tenant-send"
        assert insert_params["package_hash"] == "deadbeef"
        assert insert_params["notification_target"] == "n@x.io"
        # Payload is JSON-serialized.
        assert json.loads(insert_params["payload"]) == package

    def test_rolls_back_and_closes_on_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        boom = RuntimeError("boom")
        # First execute is DDL (ok), second raises.
        session = _FakeSession(execute_queue=[None, boom])
        monkeypatch.setattr(exchange_api, "get_db_safe", lambda: session)
        req = ExchangeSendRequest(
            receiver_tenant_id="tenant-recv",
            traceability_lot_code="LOT-001",
        )
        package = {
            "package_id": "pkg-1",
            "summary": {"event_count": 0, "traceability_lot_codes": []},
            "sender_tenant_id": "tenant-send",
            "receiver_tenant_id": "tenant-recv",
        }
        with pytest.raises(RuntimeError, match="boom"):
            _store_package_db("tenant-send", req, "pkg-1", "hh", package)
        assert session.committed is False
        assert session.rolled_back is True
        assert session.closed is True


# ---------------------------------------------------------------------------
# `_store_package_fallback`
# ---------------------------------------------------------------------------


class TestStorePackageFallback:
    def setup_method(self) -> None:
        _exchange_store.clear()

    def teardown_method(self) -> None:
        _exchange_store.clear()

    def test_writes_expected_envelope(self) -> None:
        package = {
            "package_id": "pkg-fb",
            "sender_tenant_id": "tenant-send",
            "receiver_tenant_id": "tenant-recv",
            "summary": {
                "event_count": 1,
                "traceability_lot_codes": ["LOT-007"],
            },
            "notification_target": "ship@example.com",
            "package_hash": "hash-fb",
            "created_at": "2026-04-19T12:00:00+00:00",
        }
        _store_package_fallback(package)
        assert "pkg-fb" in _exchange_store
        stored = _exchange_store["pkg-fb"]
        assert stored["status"] == "pending"
        assert stored["traceability_lot_codes"] == ["LOT-007"]
        assert stored["event_count"] == 1
        assert stored["notification_target"] == "ship@example.com"
        assert stored["package_hash"] == "hash-fb"
        assert stored["payload"] is package
        assert stored["received_at"] is None

    def test_missing_notification_target_defaults_none(self) -> None:
        package = {
            "package_id": "pkg-no-email",
            "sender_tenant_id": "tenant-send",
            "receiver_tenant_id": "tenant-recv",
            "summary": {"event_count": 0, "traceability_lot_codes": []},
            "package_hash": "hash",
            "created_at": "now",
        }
        _store_package_fallback(package)
        assert _exchange_store["pkg-no-email"]["notification_target"] is None


# ---------------------------------------------------------------------------
# `_load_packages_db`
# ---------------------------------------------------------------------------


_UNSET = object()


def _db_row(
    package_id: str = "pkg-1",
    sender: str = "tenant-send",
    receiver: str = "tenant-recv",
    status: str = "pending",
    tlcs: Any = _UNSET,
    event_count: int = 3,
    notification: str | None = "n@x.io",
    package_hash: str = "h",
    payload: Any = _UNSET,
    created_at: Any = _UNSET,
    received_at: datetime | None = None,
) -> tuple:
    return (
        package_id,
        sender,
        receiver,
        status,
        ["LOT-1"] if tlcs is _UNSET else tlcs,
        event_count,
        notification,
        package_hash,
        {"records": []} if payload is _UNSET else payload,
        datetime(2026, 4, 19, 10, tzinfo=timezone.utc) if created_at is _UNSET else created_at,
        received_at,
    )


class TestLoadPackagesDb:
    def test_list_without_package_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        row1 = _db_row(package_id="pkg-a", created_at=datetime(2026, 4, 19, 12, tzinfo=timezone.utc))
        row2 = _db_row(package_id="pkg-b", created_at=datetime(2026, 4, 18, 12, tzinfo=timezone.utc))
        # DDL then SELECT.
        session = _FakeSession(execute_queue=[None, [row1, row2]])
        monkeypatch.setattr(exchange_api, "get_db_safe", lambda: session)
        result = _load_packages_db(
            receiver_tenant_id="tenant-recv",
            package_id=None,
            limit=10,
            include_payload=False,
            mark_received=False,
        )
        assert session.closed is True
        assert [r["package_id"] for r in result] == ["pkg-a", "pkg-b"]
        assert "payload" not in result[0]
        assert result[0]["traceability_lot_codes"] == ["LOT-1"]
        assert result[0]["created_at"] == "2026-04-19T12:00:00+00:00"
        assert result[0]["received_at"] is None
        # SELECT was a list query against receiver_tenant_id.
        _, params = [c for c in session.calls if c[0] == "execute"][1][1]
        assert params == {"receiver_tenant_id": "tenant-recv", "limit": 10}

    def test_includes_payload_when_requested(self, monkeypatch: pytest.MonkeyPatch) -> None:
        payload = {"records": [{"cte_event_id": "evt-1"}]}
        row = _db_row(payload=payload)
        session = _FakeSession(execute_queue=[None, [row]])
        monkeypatch.setattr(exchange_api, "get_db_safe", lambda: session)
        result = _load_packages_db(
            receiver_tenant_id="tenant-recv",
            package_id=None,
            limit=1,
            include_payload=True,
            mark_received=False,
        )
        assert result[0]["payload"] == payload

    def test_handles_nulls_in_row(self, monkeypatch: pytest.MonkeyPatch) -> None:
        row = _db_row(tlcs=None, created_at=None, received_at=None)
        session = _FakeSession(execute_queue=[None, [row]])
        monkeypatch.setattr(exchange_api, "get_db_safe", lambda: session)
        result = _load_packages_db(
            receiver_tenant_id="tenant-recv",
            package_id=None,
            limit=5,
            include_payload=False,
            mark_received=False,
        )
        assert result[0]["traceability_lot_codes"] == []
        assert result[0]["created_at"] is None
        assert result[0]["received_at"] is None

    def test_single_package_without_mark_received(self, monkeypatch: pytest.MonkeyPatch) -> None:
        row = _db_row(package_id="pkg-single", status="pending")
        session = _FakeSession(execute_queue=[None, [row]])
        monkeypatch.setattr(exchange_api, "get_db_safe", lambda: session)
        result = _load_packages_db(
            receiver_tenant_id="tenant-recv",
            package_id="pkg-single",
            limit=1,
            include_payload=False,
            mark_received=False,
        )
        assert len(result) == 1
        assert result[0]["status"] == "pending"
        # Only DDL + one SELECT.
        assert len([c for c in session.calls if c[0] == "execute"]) == 2
        assert session.committed is False

    def test_mark_received_runs_update_and_refetch(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        row_before = _db_row(package_id="pkg-mark", status="pending")
        row_after = _db_row(
            package_id="pkg-mark",
            status="received",
            received_at=datetime(2026, 4, 19, 13, tzinfo=timezone.utc),
        )
        # DDL, initial SELECT, UPDATE, re-SELECT.
        session = _FakeSession(execute_queue=[None, [row_before], None, [row_after]])
        monkeypatch.setattr(exchange_api, "get_db_safe", lambda: session)
        result = _load_packages_db(
            receiver_tenant_id="tenant-recv",
            package_id="pkg-mark",
            limit=1,
            include_payload=True,
            mark_received=True,
        )
        assert session.committed is True
        assert result[0]["status"] == "received"
        assert result[0]["received_at"] == "2026-04-19T13:00:00+00:00"
        # Assert the second execute was the UPDATE.
        execute_calls = [c for c in session.calls if c[0] == "execute"]
        update_stmt, _ = execute_calls[2][1]
        assert "UPDATE fsma.exchange_packages" in update_stmt
        assert "SET status = 'received'" in update_stmt

    def test_mark_received_with_empty_result_skips_update(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # DDL, initial SELECT returns no rows.
        session = _FakeSession(execute_queue=[None, []])
        monkeypatch.setattr(exchange_api, "get_db_safe", lambda: session)
        result = _load_packages_db(
            receiver_tenant_id="tenant-recv",
            package_id="pkg-missing",
            limit=1,
            include_payload=False,
            mark_received=True,
        )
        assert result == []
        assert session.committed is False
        # Exactly 2 execute calls (DDL + SELECT), not the UPDATE path.
        assert len([c for c in session.calls if c[0] == "execute"]) == 2

    def test_close_always_runs_on_exception(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        boom = RuntimeError("db down")
        # DDL ok, SELECT blows up.
        session = _FakeSession(execute_queue=[None, boom])
        monkeypatch.setattr(exchange_api, "get_db_safe", lambda: session)
        with pytest.raises(RuntimeError, match="db down"):
            _load_packages_db(
                receiver_tenant_id="tenant-recv",
                package_id=None,
                limit=5,
                include_payload=False,
                mark_received=False,
            )
        assert session.closed is True


# ---------------------------------------------------------------------------
# `_load_packages_fallback`
# ---------------------------------------------------------------------------


class TestLoadPackagesFallback:
    def setup_method(self) -> None:
        _exchange_store.clear()

    def teardown_method(self) -> None:
        _exchange_store.clear()

    def test_filters_by_receiver_and_sorts_desc(self) -> None:
        _exchange_store["pkg-old"] = {
            "id": "pkg-old",
            "sender_tenant_id": "s1",
            "receiver_tenant_id": "tenant-recv",
            "status": "pending",
            "traceability_lot_codes": ["LOT-1"],
            "event_count": 1,
            "notification_target": None,
            "package_hash": "h-old",
            "payload": {"records": []},
            "created_at": "2026-04-18T10:00:00+00:00",
            "received_at": None,
        }
        _exchange_store["pkg-new"] = {
            "id": "pkg-new",
            "sender_tenant_id": "s2",
            "receiver_tenant_id": "tenant-recv",
            "status": "pending",
            "traceability_lot_codes": None,
            "event_count": None,
            "notification_target": "x@y",
            "package_hash": "h-new",
            "payload": {"records": [{"e": 1}]},
            "created_at": "2026-04-19T10:00:00+00:00",
            "received_at": None,
        }
        # Another tenant should be filtered out.
        _exchange_store["pkg-other"] = {
            "id": "pkg-other",
            "sender_tenant_id": "s3",
            "receiver_tenant_id": "other",
            "status": "pending",
            "traceability_lot_codes": [],
            "event_count": 0,
            "notification_target": None,
            "package_hash": "h-other",
            "payload": {},
            "created_at": "2026-04-19T11:00:00+00:00",
            "received_at": None,
        }
        result = _load_packages_fallback(
            receiver_tenant_id="tenant-recv",
            package_id=None,
            limit=10,
            include_payload=False,
            mark_received=False,
        )
        ids = [p["package_id"] for p in result]
        assert ids == ["pkg-new", "pkg-old"]
        # None values normalize to list/0.
        assert result[0]["traceability_lot_codes"] == []
        assert result[0]["event_count"] == 0

    def test_filter_by_package_id_and_mark_received(self) -> None:
        _exchange_store["pkg-1"] = {
            "id": "pkg-1",
            "sender_tenant_id": "s",
            "receiver_tenant_id": "tenant-recv",
            "status": "pending",
            "traceability_lot_codes": ["LOT-A"],
            "event_count": 2,
            "notification_target": None,
            "package_hash": "h",
            "payload": {"foo": "bar"},
            "created_at": "2026-04-19T10:00:00+00:00",
            "received_at": None,
        }
        result = _load_packages_fallback(
            receiver_tenant_id="tenant-recv",
            package_id="pkg-1",
            limit=10,
            include_payload=True,
            mark_received=True,
        )
        assert len(result) == 1
        assert result[0]["status"] == "received"
        assert result[0]["received_at"] is not None
        assert result[0]["payload"] == {"foo": "bar"}
        # Underlying store was mutated too.
        assert _exchange_store["pkg-1"]["status"] == "received"

    def test_mark_received_no_match_noop(self) -> None:
        _exchange_store["pkg-1"] = {
            "id": "pkg-1",
            "sender_tenant_id": "s",
            "receiver_tenant_id": "tenant-recv",
            "status": "pending",
            "traceability_lot_codes": ["LOT-A"],
            "event_count": 2,
            "notification_target": None,
            "package_hash": "h",
            "payload": {},
            "created_at": "2026-04-19T10:00:00+00:00",
            "received_at": None,
        }
        result = _load_packages_fallback(
            receiver_tenant_id="tenant-recv",
            package_id="does-not-exist",
            limit=10,
            include_payload=False,
            mark_received=True,
        )
        assert result == []
        # Original package untouched.
        assert _exchange_store["pkg-1"]["status"] == "pending"

    def test_limit_truncates_results(self) -> None:
        for i in range(5):
            _exchange_store[f"pkg-{i}"] = {
                "id": f"pkg-{i}",
                "sender_tenant_id": "s",
                "receiver_tenant_id": "tenant-recv",
                "status": "pending",
                "traceability_lot_codes": ["LOT"],
                "event_count": 1,
                "notification_target": None,
                "package_hash": "h",
                "payload": {},
                "created_at": f"2026-04-1{i}T10:00:00+00:00",
                "received_at": None,
            }
        result = _load_packages_fallback(
            receiver_tenant_id="tenant-recv",
            package_id=None,
            limit=2,
            include_payload=False,
            mark_received=False,
        )
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Endpoint coverage: DB success + 503 no-fallback
# ---------------------------------------------------------------------------


def _auth_override_factory(scopes: list[str]):
    return lambda: IngestionPrincipal(
        key_id="test-key",
        scopes=scopes,
        auth_mode="test",
    )


@pytest.fixture()
def app_with_scopes() -> FastAPI:
    app = FastAPI()
    app.include_router(exchange_router)
    app.dependency_overrides[get_ingestion_principal] = _auth_override_factory(["*"])
    return app


class TestSendEndpointDbSuccessPath:
    def test_send_exercises_full_db_pipeline(
        self, app_with_scopes: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # First session: _query_shipping_rows -> returns a single row.
        row = _make_row(traceability_lot_code="LOT-HAPPY")
        query_session = _FakeSession(execute_queue=[[row]])
        # Second session (inside _store_package_db): DDL + INSERT.
        store_session = _FakeSession()
        sessions = iter([query_session, store_session])

        def _fake_get_db_safe():
            return next(sessions)

        monkeypatch.setattr(exchange_api, "get_db_safe", _fake_get_db_safe)

        with TestClient(app_with_scopes) as client:
            response = client.post(
                "/api/v1/exchange/send",
                params={"tenant_id": "00000000-0000-0000-0000-000000000111"},
                json={
                    "receiver_tenant_id": "00000000-0000-0000-0000-000000000222",
                    "traceability_lot_code": "LOT-HAPPY",
                    "receiver_email": "a@b.com",
                },
            )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "queued"
        assert body["event_count"] == 1
        assert body["traceability_lot_codes"] == ["LOT-HAPPY"]
        assert body["notification"]["status"] == "queued"
        # Both DB sessions were closed, and the store session committed.
        assert query_session.closed is True
        assert store_session.committed is True
        assert store_session.closed is True

    def test_send_503_when_fallback_disabled(
        self, app_with_scopes: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Query session raises a non-HTTP exception.
        failing_session = _FakeSession(execute_queue=[RuntimeError("db exploded")])
        monkeypatch.setattr(exchange_api, "get_db_safe", lambda: failing_session)
        monkeypatch.setenv("ALLOW_EXCHANGE_IN_MEMORY_FALLBACK", "false")

        with TestClient(app_with_scopes) as client:
            response = client.post(
                "/api/v1/exchange/send",
                params={"tenant_id": "00000000-0000-0000-0000-000000000111"},
                json={
                    "receiver_tenant_id": "00000000-0000-0000-0000-000000000222",
                    "event_ids": ["evt-1"],
                },
            )

        assert response.status_code == 503
        assert response.json()["detail"] == "Exchange service unavailable"

    def test_send_reraises_httpexception_without_fallback(
        self, app_with_scopes: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Query session returns no rows -> _query_shipping_rows raises 404.
        # The endpoint must re-raise that HTTPException verbatim (line 519).
        empty_session = _FakeSession(execute_queue=[[]])
        monkeypatch.setattr(exchange_api, "get_db_safe", lambda: empty_session)

        with TestClient(app_with_scopes) as client:
            response = client.post(
                "/api/v1/exchange/send",
                params={"tenant_id": "00000000-0000-0000-0000-000000000111"},
                json={
                    "receiver_tenant_id": "00000000-0000-0000-0000-000000000222",
                    "traceability_lot_code": "LOT-MISSING",
                },
            )

        assert response.status_code == 404
        assert "No shipping CTEs" in response.json()["detail"]


class TestReceiveEndpointDbSuccessPath:
    def test_receive_uses_db_when_healthy(
        self, app_with_scopes: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        row = _db_row(package_id="pkg-db", status="pending")
        session = _FakeSession(execute_queue=[None, [row]])
        monkeypatch.setattr(exchange_api, "get_db_safe", lambda: session)

        with TestClient(app_with_scopes) as client:
            response = client.get(
                "/api/v1/exchange/receive",
                params={
                    "tenant_id": "00000000-0000-0000-0000-000000000222",
                    "include_payload": "false",
                },
            )
        assert response.status_code == 200
        body = response.json()
        assert body["count"] == 1
        assert body["packages"][0]["package_id"] == "pkg-db"
        assert session.closed is True

    def test_receive_503_when_fallback_disabled(
        self, app_with_scopes: FastAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        failing_session = _FakeSession(execute_queue=[RuntimeError("boom"), RuntimeError("boom")])
        monkeypatch.setattr(exchange_api, "get_db_safe", lambda: failing_session)
        monkeypatch.setenv("ALLOW_EXCHANGE_IN_MEMORY_FALLBACK", "false")

        with TestClient(app_with_scopes) as client:
            response = client.get(
                "/api/v1/exchange/receive",
                params={"tenant_id": "00000000-0000-0000-0000-000000000222"},
            )
        assert response.status_code == 503
        assert response.json()["detail"] == "Exchange service unavailable"
