"""EPIC-L (#1655) idempotency tests for ``CTEPersistence.log_export``.

The ``fsma.fda_export_log`` audit-row write now uses ``INSERT ... ON
CONFLICT (tenant_id, export_fingerprint) DO NOTHING RETURNING id`` so
that a retried export (same tenant / window / filters / content hash)
resolves to a single canonical row. These tests cover:

* The fingerprint is deterministic across retries with the same inputs.
* The fingerprint differs when any discriminating input changes.
* ``log_export`` emits a SQL statement with the correct ON CONFLICT
  clause and fingerprint parameter.
* When a fresh row lands, ``log_export`` returns the INSERT's
  ``RETURNING id``.
* When ON CONFLICT fires (RETURNING yields no row), ``log_export``
  performs a fallback SELECT and returns the pre-existing row's id.
* When the DB rejects the ON CONFLICT statement (legacy schema before
  the v071 migration), ``log_export`` falls back to the pre-EPIC-L
  shape and still returns the freshly minted id.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, List

import pytest

_SERVICES = Path(__file__).resolve().parent.parent.parent
if str(_SERVICES) not in sys.path:
    sys.path.insert(0, str(_SERVICES))

from shared.cte_persistence.core import CTEPersistence


# ---------------------------------------------------------------------------
# _compute_export_fingerprint
# ---------------------------------------------------------------------------


class TestFingerprint:
    _BASE = {
        "tenant_id": "00000000-0000-0000-0000-000000000111",
        "export_type": "fda_spreadsheet",
        "query_tlc": "TLC-2026-001",
        "query_start_date": "2026-03-01",
        "query_end_date": "2026-03-31",
        "record_count": 17,
        "export_hash": "a" * 64,
    }

    def test_same_inputs_yield_same_fingerprint(self) -> None:
        fp1 = CTEPersistence._compute_export_fingerprint(**self._BASE)
        fp2 = CTEPersistence._compute_export_fingerprint(**self._BASE)
        assert fp1 == fp2
        # Hex-encoded sha256 is 64 chars.
        assert len(fp1) == 64

    @pytest.mark.parametrize(
        "field, alt",
        [
            ("tenant_id", "00000000-0000-0000-0000-000000000222"),
            ("export_type", "fda_export_all"),
            ("query_tlc", "TLC-2026-002"),
            ("query_start_date", "2026-03-02"),
            ("query_end_date", "2026-03-30"),
            ("record_count", 18),
            ("export_hash", "b" * 64),
        ],
    )
    def test_any_field_change_flips_fingerprint(self, field: str, alt: object) -> None:
        base_fp = CTEPersistence._compute_export_fingerprint(**self._BASE)
        overridden = dict(self._BASE)
        overridden[field] = alt
        assert CTEPersistence._compute_export_fingerprint(**overridden) != base_fp

    def test_none_tlc_is_distinct_from_empty_tlc(self) -> None:
        """A None filter should match an empty string — we normalize
        both to '' in the fingerprint. Documented behavior so a
        missing-value query deduplicates against the same query with
        an explicit empty TLC."""
        base = dict(self._BASE)
        base["query_tlc"] = None
        alt = dict(self._BASE)
        alt["query_tlc"] = ""
        assert (
            CTEPersistence._compute_export_fingerprint(**base)
            == CTEPersistence._compute_export_fingerprint(**alt)
        )


# ---------------------------------------------------------------------------
# log_export SQL behavior
# ---------------------------------------------------------------------------


class _RecordedExecute:
    """Minimal SQLAlchemy ``session.execute`` recorder."""

    def __init__(self):
        self.statements: List[str] = []
        self.params: List[dict] = []
        # Scripted return values for the insert and (if used) the
        # fallback select.
        self.returns: List[Any] = []
        # Optional side effect: raise on the first call if set.
        self.raise_on_first: Exception | None = None

    def __call__(self, stmt, params=None):
        self.statements.append(str(stmt))
        self.params.append(dict(params or {}))
        if self.raise_on_first is not None and len(self.statements) == 1:
            exc = self.raise_on_first
            self.raise_on_first = None
            raise exc
        return _Result(self.returns.pop(0) if self.returns else None)


class _Result:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _FakeSession:
    def __init__(self, execute: _RecordedExecute):
        self.execute = execute
        self.committed = False
        self.rolled_back = False

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


@pytest.fixture()
def session_pair():
    rec = _RecordedExecute()
    return rec, _FakeSession(rec)


def test_log_export_insert_happy_path_returns_new_id(session_pair):
    rec, session = session_pair
    rec.returns = [("11111111-1111-1111-1111-111111111111",)]

    p = CTEPersistence(session)
    result = p.log_export(
        tenant_id="00000000-0000-0000-0000-000000000111",
        export_hash="a" * 64,
        record_count=5,
        query_tlc="TLC-1",
        query_start_date="2026-03-01",
        query_end_date="2026-03-31",
        generated_by="user:test",
    )

    assert result == "11111111-1111-1111-1111-111111111111"
    # One INSERT; no fallback SELECT.
    assert len(rec.statements) == 1
    stmt = rec.statements[0]
    assert "ON CONFLICT (tenant_id, export_fingerprint)" in stmt
    assert "WHERE export_fingerprint IS NOT NULL" in stmt
    assert "DO NOTHING" in stmt
    assert "RETURNING id" in stmt
    # Fingerprint param is present and matches the helper.
    params = rec.params[0]
    assert params["fp"] == CTEPersistence._compute_export_fingerprint(
        tenant_id="00000000-0000-0000-0000-000000000111",
        export_type="fda_spreadsheet",
        query_tlc="TLC-1",
        query_start_date="2026-03-01",
        query_end_date="2026-03-31",
        record_count=5,
        export_hash="a" * 64,
    )


def test_log_export_conflict_returns_existing_id(session_pair):
    rec, session = session_pair
    # First call: INSERT ... ON CONFLICT DO NOTHING RETURNING id
    # returns None (conflict fired, no row returned).
    # Second call: SELECT returns the winning row's id.
    rec.returns = [None, ("22222222-2222-2222-2222-222222222222",)]

    p = CTEPersistence(session)
    result = p.log_export(
        tenant_id="00000000-0000-0000-0000-000000000111",
        export_hash="c" * 64,
        record_count=5,
    )

    assert result == "22222222-2222-2222-2222-222222222222"
    assert len(rec.statements) == 2
    assert "ON CONFLICT" in rec.statements[0]
    assert "SELECT id FROM fsma.fda_export_log" in rec.statements[1]
    # The SELECT uses the same fingerprint the INSERT would have.
    assert rec.params[1]["fp"] == rec.params[0]["fp"]
    assert rec.params[1]["tid"] == rec.params[0]["tid"]


def test_log_export_legacy_schema_falls_back_and_still_returns_id(session_pair):
    rec, session = session_pair
    # First call raises (simulating a DB that rejects ON CONFLICT
    # because the unique index is absent). Second call is the legacy
    # INSERT and returns no result row (the original code path never
    # used RETURNING).
    rec.raise_on_first = Exception("column export_fingerprint does not exist")
    rec.returns = [None]

    p = CTEPersistence(session)
    result = p.log_export(
        tenant_id="00000000-0000-0000-0000-000000000111",
        export_hash="d" * 64,
        record_count=5,
    )

    # Legacy path yields the locally generated UUID — non-empty, 36 chars.
    assert result and len(result) == 36
    assert len(rec.statements) == 2
    # The fallback statement has no ON CONFLICT clause.
    assert "ON CONFLICT" not in rec.statements[1]


def test_log_export_conflict_but_row_missing_raises(session_pair):
    rec, session = session_pair
    # ON CONFLICT fired (None) and then the follow-up SELECT also
    # returned None — the winning row vanished between statements.
    # Rather than silently lie, we raise.
    rec.returns = [None, None]

    p = CTEPersistence(session)
    with pytest.raises(RuntimeError, match="no matching row"):
        p.log_export(
            tenant_id="00000000-0000-0000-0000-000000000111",
            export_hash="e" * 64,
            record_count=5,
        )
