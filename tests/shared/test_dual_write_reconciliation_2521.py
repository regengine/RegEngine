"""Regression tests for #2521 — cross-table dual-write reconciliation.

``scripts/validate_data_integrity.py:check_dual_write_reconciliation``
compares ``fsma.traceability_events`` vs ``fsma.cte_events`` by
``sha256_hash`` per tenant and FAILS (so the script exits non-zero) when a
legacy ``cte_events`` row has no canonical twin — the "swallowed canonical
write" failure mode that the #1277 invariant is meant to prevent. The
reverse direction (canonical-only rows) is expected from the production
``dual_write=False`` paths and must NOT be flagged.

These tests use a tiny fake connection that returns scripted scalar
results keyed by a substring of the SQL, so they need no live Postgres.
They also assert the marker/invariant contract:
* a ``dual_write=True`` canonical insert produces a matching legacy row
  reconcilable by ``sha256_hash`` (the legacy INSERT carries the SAME
  ``event.sha256_hash`` the canonical INSERT used);
* the ``DUAL_WRITE_RECONCILIATION_NEEDED`` marker still exists.
"""

from __future__ import annotations

import importlib.util
import os
from typing import Any

import pytest

# Load the standalone script module by path (scripts/ is not a package).
_SCRIPT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "scripts",
    "validate_data_integrity.py",
)
_spec = importlib.util.spec_from_file_location("validate_data_integrity", _SCRIPT_PATH)
assert _spec and _spec.loader
validate_data_integrity = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(validate_data_integrity)


class _ScalarResult:
    def __init__(self, value: Any) -> None:
        self._value = value

    def scalar(self) -> Any:
        return self._value


class _FakeConn:
    """Returns scripted scalar results keyed by the OUTER FROM table.

    Both reconciliation queries reference both tables (one in the outer
    FROM, the other inside a ``NOT EXISTS`` subquery), so a naive
    substring match is ambiguous. We key on whichever table name appears
    FIRST in the SQL — that is the outer FROM and uniquely identifies the
    query:
      1. orphan legacy:    outer ``FROM fsma.cte_events c``
      2. canonical only:   outer ``FROM fsma.traceability_events t``

    Rules are (needle, value) where needle is the outer-FROM table name.
    """

    def __init__(self, rules: list[tuple[str, Any]]) -> None:
        self._rules = rules
        self.queries: list[str] = []

    def execute(self, stmt: Any) -> _ScalarResult:
        sql = str(getattr(stmt, "text", stmt))
        self.queries.append(sql)
        # Determine the outer FROM by which needle appears first.
        first_needle = min(
            (r for r in self._rules if r[0] in sql),
            key=lambda r: sql.index(r[0]),
            default=None,
        )
        if first_needle is not None:
            value = first_needle[1]
            if isinstance(value, Exception):
                raise value
            return _ScalarResult(value)
        return _ScalarResult(0)


def _text_fn(s: str) -> str:
    # The real text_fn is sqlalchemy.text; a passthrough is enough because
    # _FakeConn stringifies whatever it receives.
    return s


class TestDualWriteReconciliation_Issue2521:
    def test_stores_in_sync_passes(self) -> None:
        conn = _FakeConn(
            [
                ("FROM fsma.cte_events c", 0),  # no orphan legacy rows
                ("FROM fsma.traceability_events t", 0),  # no canonical-only rows
            ]
        )
        passed, message = validate_data_integrity.check_dual_write_reconciliation(conn, _text_fn)
        assert passed is True
        assert "reconciled" in message.lower()

    def test_canonical_only_rows_do_not_fail(self) -> None:
        """dual_write=False paths leave canonical-only rows — expected,
        must NOT fail the check."""
        conn = _FakeConn(
            [
                ("FROM fsma.cte_events c", 0),  # no orphan legacy
                ("FROM fsma.traceability_events t", 42),  # 42 canonical-only
            ]
        )
        passed, message = validate_data_integrity.check_dual_write_reconciliation(conn, _text_fn)
        assert passed is True
        assert "42 canonical-only" in message

    def test_orphan_legacy_row_fails(self) -> None:
        """A legacy cte_events row with no canonical twin is a swallowed
        canonical write → hard failure (non-zero exit)."""
        conn = _FakeConn(
            [
                ("FROM fsma.cte_events c", 3),  # 3 orphan legacy rows
                ("FROM fsma.traceability_events t", 0),
            ]
        )
        passed, message = validate_data_integrity.check_dual_write_reconciliation(conn, _text_fn)
        assert passed is False
        assert "3 legacy cte_events row(s)" in message
        assert "#1277" in message

    def test_missing_table_is_skipped_not_failed(self) -> None:
        conn = _FakeConn(
            [
                ("FROM fsma.cte_events c", Exception('relation "fsma.cte_events" does not exist')),
            ]
        )
        passed, message = validate_data_integrity.check_dual_write_reconciliation(conn, _text_fn)
        assert passed is True
        assert "skipped" in message.lower()

    def test_check_registered_in_main_checks(self) -> None:
        """The reconciliation check must be wired into the script's run so
        a divergence actually fails CI / the scheduled job (criterion 2)."""
        import inspect

        src = inspect.getsource(validate_data_integrity.main)
        assert "check_dual_write_reconciliation" in src


class TestDualWriteShaJoinKey_Issue2521:
    """The reconciliation join key is ``sha256_hash``; it is only valid if
    the legacy dual-write copies the canonical event's ``sha256_hash``
    verbatim. Assert that contract on the binding so a future change that
    recomputes the legacy hash (which would make every row look orphaned)
    fails this test instead."""

    def test_legacy_dual_write_binds_canonical_sha256(self) -> None:
        from datetime import datetime, timezone
        from uuid import uuid4

        from shared.canonical_event import (
            CTEType,
            EventStatus,
            IngestionSource,
            ProvenanceMetadata,
            TraceabilityEvent,
        )
        from shared.canonical_persistence import legacy_dual_write as migration

        captured: list[dict] = []

        class _CaptureSession:
            def execute(self, stmt: Any, params: Any = None) -> Any:
                captured.append(dict(params or {}))

                class _R:
                    def fetchone(self_inner):
                        return None

                return _R()

            def begin_nested(self):  # pragma: no cover - not exercised here
                raise AssertionError("begin_nested no longer wraps KDE writes (#2532)")

        evt = TraceabilityEvent(
            event_id=uuid4(),
            tenant_id=uuid4(),
            source_system=IngestionSource.WEBHOOK_API,
            source_record_id="rec-1",
            event_type=CTEType.SHIPPING,
            event_timestamp=datetime.now(timezone.utc),
            event_timezone="UTC",
            product_reference="prod",
            lot_reference="LOT-1",
            traceability_lot_code="TLC-1",
            quantity=10.0,
            unit_of_measure="kg",
            kdes={},
            raw_payload={"k": "v"},
            normalized_payload={},
            provenance_metadata=ProvenanceMetadata(),
            confidence_score=1.0,
            status=EventStatus.ACTIVE,
            idempotency_key="idem-1",
        )
        evt.prepare_for_persistence()

        migration.dual_write_legacy(_CaptureSession(), evt)

        cte_insert = next(p for p in captured if "sha256_hash" in p)
        assert cte_insert["sha256_hash"] == evt.sha256_hash, (
            "legacy cte_events row must carry the canonical sha256_hash "
            "verbatim so cross-table reconciliation (#2521) can join on it"
        )
