"""The FDA spreadsheet marks rows whose lot and CTE have an open data gap.

Locks:
- Open Data Gaps is the last column in the v1 and v2 sheets, and no earlier
  column moves.
- A row with a gap names it; a row without one is unchanged and its cell blank.
- Gaps match on lot and CTE, so another CTE of the same lot stays blank.
- A failed lookup stops the export: a blank cell states no gap was open.
- /export/verify reads gaps as of the export, so a gap that closed later is not
  reported as tampering, and an export from before the column still verifies.
"""

from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import json
import sys
import zipfile
from datetime import datetime, timezone
from types import ModuleType, SimpleNamespace

import pytest
from app import fda_export_service as svc
from app.fda_export import verification as v
from app.fda_export.queries import attach_open_gaps
from fastapi import HTTPException
from shared.data_gap_tracking import fetch_gaps_open_at
from sqlalchemy.exc import ProgrammingError

TENANT = "7b6f7f0e-6f0a-4a5e-9d0b-1f2f7c1f0a11"
EXPORTED_AT = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
GAP_LABEL = "missing_kde: tlc_source_reference"


def _event(tlc="LOT-1", event_type="shipping") -> dict:
    return {
        "id": f"{tlc}-{event_type}",
        "traceability_lot_code": tlc,
        "product_description": "Romaine",
        "quantity": 10,
        "unit_of_measure": "cases",
        "event_type": event_type,
        "event_timestamp": "2026-10-30T10:00:00+00:00",
        "sha256_hash": "a" * 64,
        "chain_hash": "b" * 64,
        "kdes": {},
    }


def _rows(csv_content: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(csv_content)))


class _Result:
    def __init__(self, rows=(), row=None):
        self._rows = list(rows)
        self._row = row

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._row


class _GapSession:
    """Answers the gap query from ``gap_rows`` and records its parameters."""

    def __init__(self, gap_rows=(), audit_row=None):
        self.gap_rows = gap_rows
        self.audit_row = audit_row
        self.gap_params: list[dict] = []
        self.gap_sql: list[str] = []

    def execute(self, stmt, params=None):
        sql = str(stmt)
        if "public.data_gap_events" in sql:
            self.gap_params.append(dict(params))
            self.gap_sql.append(sql)
            return _Result(self.gap_rows)
        if "fda_export_log" in sql:
            return _Result(row=self.audit_row)
        return _Result()

    def close(self):
        pass


# ---------------------------------------------------------------------------
# Spreadsheet
# ---------------------------------------------------------------------------


def test_column_is_last_and_no_earlier_column_moves() -> None:
    assert svc.FDA_COLUMNS[-1] == svc.OPEN_GAPS_COLUMN
    assert svc.FDA_COLUMNS_V2[-1] == svc.OPEN_GAPS_COLUMN
    assert svc.FDA_COLUMNS[:-1] == svc.FDA_COLUMNS_WITHOUT_OPEN_GAPS
    assert svc.FDA_COLUMNS_V2[:-1] == svc.FDA_COLUMNS_V2_WITHOUT_OPEN_GAPS
    assert svc.FDA_COLUMNS_V2_WITHOUT_OPEN_GAPS[: len(svc.FDA_COLUMNS_WITHOUT_OPEN_GAPS)] == (
        svc.FDA_COLUMNS_WITHOUT_OPEN_GAPS
    )


@pytest.mark.parametrize("generate", [svc._generate_csv, svc._generate_csv_v2])
def test_row_with_a_gap_is_marked_and_row_without_is_blank(generate) -> None:
    marked = {**_event("LOT-1"), "open_data_gaps": [GAP_LABEL, "missing_kde: other"]}
    clean = {**_event("LOT-2"), "open_data_gaps": []}

    rows = _rows(generate([marked, clean]))

    assert rows[0][svc.OPEN_GAPS_COLUMN] == f"{GAP_LABEL}; missing_kde: other"
    assert rows[1][svc.OPEN_GAPS_COLUMN] == ""


@pytest.mark.parametrize(
    ("generate", "columns", "v2"),
    [
        (svc._generate_csv, svc.FDA_COLUMNS_WITHOUT_OPEN_GAPS, False),
        (svc._generate_csv_v2, svc.FDA_COLUMNS_V2_WITHOUT_OPEN_GAPS, True),
    ],
)
def test_no_gap_row_keeps_every_other_cell(generate, columns, v2) -> None:
    """Only the new cell differs from the layout before the column."""
    event = {**_event(), "open_data_gaps": []}

    current = _rows(generate([event]))[0]
    older = _rows(svc._generate_csv_before_open_gaps([event], include_pii=False, v2=v2))[0]

    assert list(older) == columns
    assert {column: current[column] for column in columns} == older


def test_cell_is_sanitized() -> None:
    """A gap key can echo a validator message, so it gets the same formula guard."""
    event = {**_event(), "open_data_gaps": ['=HYPERLINK("http://x")']}

    assert not _rows(svc._generate_csv([event]))[0][svc.OPEN_GAPS_COLUMN].startswith("=")


def test_pii_redaction_leaves_the_marker() -> None:
    event = {**_event(), "open_data_gaps": [GAP_LABEL]}

    assert _rows(svc._generate_csv([event], include_pii=False))[0][svc.OPEN_GAPS_COLUMN] == GAP_LABEL


# ---------------------------------------------------------------------------
# Lookup
# ---------------------------------------------------------------------------


def test_lookup_is_tenant_scoped_and_as_of_the_export() -> None:
    session = _GapSession()

    fetch_gaps_open_at(session, TENANT, ["LOT-2", " LOT-1 ", "LOT-2", ""], EXPORTED_AT)

    assert session.gap_params == [{"tid": TENANT, "lots": ["LOT-1", "LOT-2"], "as_of": EXPORTED_AT}]
    assert "tenant_id = CAST(:tid AS uuid)" in session.gap_sql[0]


def test_lookup_labels_are_sorted_so_bytes_are_stable() -> None:
    session = _GapSession(
        [
            ("LOT-1", "shipping", "missing_kde", "z_field"),
            ("LOT-1", "shipping", "cte_validation_failed", "rule-7"),
            ("LOT-1", "shipping", "missing_kde", "a_field"),
        ]
    )

    gaps = fetch_gaps_open_at(session, TENANT, ["LOT-1"], EXPORTED_AT)

    assert gaps == {
        ("LOT-1", "shipping"): (
            "cte_validation_failed: rule-7",
            "missing_kde: a_field",
            "missing_kde: z_field",
        )
    }


def test_no_lots_runs_no_query() -> None:
    session = _GapSession()

    assert fetch_gaps_open_at(session, TENANT, ["", "  "], EXPORTED_AT) == {}
    assert session.gap_params == []


def test_attach_matches_lot_and_cte() -> None:
    session = _GapSession([("LOT-1", "shipping", "missing_kde", "tlc_source_reference")])
    shipped = _event("LOT-1", "SHIPPING")
    received = _event("LOT-1", "receiving")
    other_lot = _event("LOT-2", "shipping")

    returned = attach_open_gaps(session, TENANT, [shipped, received, other_lot], as_of=EXPORTED_AT)

    assert returned == EXPORTED_AT
    assert shipped["open_data_gaps"] == [GAP_LABEL]
    assert received["open_data_gaps"] == []
    assert other_lot["open_data_gaps"] == []


def test_attach_binds_the_tenant_for_rls() -> None:
    calls: list[dict] = []

    class Session(_GapSession):
        def execute(self, stmt, params=None):
            if "set_config" in str(stmt):
                calls.append(dict(params))
            return super().execute(stmt, params)

    attach_open_gaps(Session(), TENANT, [_event()], as_of=EXPORTED_AT)

    assert any(TENANT in call.values() for call in calls)


def test_failed_lookup_stops_the_export() -> None:
    class Denied(_GapSession):
        def execute(self, stmt, params=None):
            if "public.data_gap_events" in str(stmt):
                raise ProgrammingError("SELECT", {}, Exception("permission denied"))
            return super().execute(stmt, params)

    event = _event()

    with pytest.raises(HTTPException) as exc:
        attach_open_gaps(Denied(), TENANT, [event], as_of=EXPORTED_AT)

    assert exc.value.status_code == 503
    assert "open_data_gaps" not in event


# ---------------------------------------------------------------------------
# Package
# ---------------------------------------------------------------------------


def test_package_counts_marked_rows_in_the_hashed_evidence() -> None:
    events = [{**_event("LOT-1"), "open_data_gaps": [GAP_LABEL]}, {**_event("LOT-2"), "open_data_gaps": []}]
    csv_content = svc._generate_csv(events)
    csv_hash = hashlib.sha256(csv_content.encode("utf-8")).hexdigest()
    chain = SimpleNamespace(valid=True, chain_length=2, errors=[], checked_at="now")
    completeness = svc._build_completeness_summary(events)
    chain_payload = svc._build_chain_verification_payload(
        tenant_id=TENANT,
        tlc=None,
        events=events,
        csv_hash=csv_hash,
        chain_verification=chain,
        completeness_summary=completeness,
    )

    package_bytes, meta = svc._build_fda_package(
        events=events,
        csv_content=csv_content,
        csv_hash=csv_hash,
        chain_payload=chain_payload,
        completeness_summary=completeness,
        tenant_id=TENANT,
        tlc=None,
        query_start_date=None,
        query_end_date=None,
    )

    with zipfile.ZipFile(io.BytesIO(package_bytes)) as archive:
        evidence = json.loads(archive.read(meta["evidence_context_name"]))
        readme = archive.read("README.txt").decode("utf-8")
    assert evidence["known_gaps"]["events_with_open_data_gaps"] == 1
    assert svc.OPEN_GAPS_COLUMN in readme


# ---------------------------------------------------------------------------
# /export/verify
# ---------------------------------------------------------------------------


def _audit_row(export_hash: str) -> tuple:
    return ("fda_spreadsheet", "LOT-1", None, None, 1, export_hash, EXPORTED_AT, False, None)


def _verify(monkeypatch, session: _GapSession) -> dict:
    db_module = ModuleType("shared.database")
    db_module.SessionLocal = lambda: session
    cte_module = ModuleType("shared.cte_persistence")
    cte_module.CTEPersistence = lambda db: SimpleNamespace(query_events_by_tlc=lambda **_: [_event("LOT-1")])
    monkeypatch.setitem(sys.modules, "shared.database", db_module)
    monkeypatch.setitem(sys.modules, "shared.cte_persistence", cte_module)
    return asyncio.run(v.verify_export_handler("exp-1", TENANT))


def test_verify_reads_gaps_as_of_the_export(monkeypatch) -> None:
    """The stored moment is what a gap closed since then is judged against."""
    marked = svc._generate_csv([{**_event("LOT-1"), "open_data_gaps": [GAP_LABEL]}])
    session = _GapSession(
        gap_rows=[("LOT-1", "shipping", "missing_kde", "tlc_source_reference")],
        audit_row=_audit_row(hashlib.sha256(marked.encode("utf-8")).hexdigest()),
    )

    out = _verify(monkeypatch, session)

    assert session.gap_params[0]["as_of"] == EXPORTED_AT
    assert out["data_integrity"] == "VERIFIED"


def test_verify_accepts_an_export_from_before_the_column(monkeypatch) -> None:
    older = svc._generate_csv_before_open_gaps([_event("LOT-1")], include_pii=False, v2=False)
    original_hash = hashlib.sha256(older.encode("utf-8")).hexdigest()

    out = _verify(monkeypatch, _GapSession(audit_row=_audit_row(original_hash)))

    assert out["hashes_match"] is True
    assert out["regenerated_hash"] == original_hash


def test_verify_still_reports_a_real_mismatch(monkeypatch) -> None:
    out = _verify(monkeypatch, _GapSession(audit_row=_audit_row("0" * 64)))

    assert out["data_integrity"] == "MISMATCH_DETECTED"
    assert out["regenerated_hash"] != "0" * 64
