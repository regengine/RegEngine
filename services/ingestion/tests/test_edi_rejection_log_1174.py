"""Unit tests for the EDI rejection log (#1174).

Covers the mechanism that keeps FSMA-invalid EDI documents out of the
canonical ingestion stream. The route-level assertion that
``ingest_events`` is not invoked lives in
``test_edi_ingestion_api.py::test_document_ingest_strict_false_query_advisory``;
this file focuses on the storage API so route regressions can be
diagnosed against a known-good primitive.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

from app.edi_ingestion import rejection_log
from app.edi_ingestion.rejection_log import (
    list_edi_rejections,
    record_edi_rejection,
    reset_edi_rejections,
)

TENANT = "00000000-0000-0000-0000-0000000000aa"
OTHER_TENANT = "00000000-0000-0000-0000-0000000000bb"


class _Session:
    def __init__(self, committed_rows, failure=None):
        self.committed_rows = committed_rows
        self.failure = failure
        self.statements = []
        self.pending = []
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def execute(self, statement, params):
        sql = str(statement)
        self.statements.append((sql, params))
        if "INSERT INTO" in sql:
            if self.failure == "insert":
                raise RuntimeError("simulated storage failure")
            self.pending.append(params)

    def commit(self):
        if self.failure == "commit":
            raise RuntimeError("simulated storage failure")
        self.committed_rows.extend(self.pending)
        self.committed = True

    def rollback(self):
        self.pending.clear()
        self.rolled_back = True

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def durable_store(monkeypatch):
    rows = []
    sessions = []
    failures = []

    def session_factory():
        failure = failures.pop(0) if failures else None
        if failure == "connect":
            raise RuntimeError("simulated storage failure")
        session = _Session(rows, failure=failure)
        sessions.append(session)
        return session

    database = types.ModuleType("shared.database")
    database.SessionLocal = session_factory
    monkeypatch.setitem(sys.modules, "shared.database", database)
    return rows, sessions, failures


@pytest.fixture(autouse=True)
def _clean_store() -> None:
    reset_edi_rejections()
    yield
    reset_edi_rejections()


def test_record_returns_rejection_id_and_metadata() -> None:
    record = record_edi_rejection(
        tenant_id=TENANT,
        transaction_set="856",
        traceability_lot_code="not-a-gtin-tlc",
        errors=[{"loc": ["tlc"], "msg": "bad format", "type": "value_error"}],
        extracted={"sender_id": "WALMART"},
        partner_id="WALMART",
        source="edi_inbound",
    )
    assert record["rejection_id"].startswith("edi-rej-")
    assert record["tenant_id"] == TENANT
    assert record["transaction_set"] == "856"
    assert record["traceability_lot_code"] == "not-a-gtin-tlc"
    assert record["partner_id"] == "WALMART"
    assert record["reason"] == "fsma_validation_failed"
    assert len(record["errors"]) == 1


def test_rejections_are_tenant_scoped() -> None:
    record_edi_rejection(
        tenant_id=TENANT,
        transaction_set="856",
        traceability_lot_code="tlc-a",
        errors=[{"msg": "e"}],
    )
    record_edi_rejection(
        tenant_id=OTHER_TENANT,
        transaction_set="850",
        traceability_lot_code="tlc-b",
        errors=[{"msg": "e"}],
    )
    assert len(list_edi_rejections(TENANT)) == 1
    assert list_edi_rejections(TENANT)[0]["traceability_lot_code"] == "tlc-a"
    assert len(list_edi_rejections(OTHER_TENANT)) == 1
    assert list_edi_rejections(OTHER_TENANT)[0]["traceability_lot_code"] == "tlc-b"


def test_extracted_is_scrubbed_to_json_safe_values() -> None:
    """Non-serializable objects in ``extracted`` must not crash the
    rejection write — we degrade to ``str()`` so the audit record
    survives. Regression guard for forensic-snapshot reliability.
    """

    class _Weird:
        def __str__(self) -> str:
            return "weird-value"

    record = record_edi_rejection(
        tenant_id=TENANT,
        transaction_set="810",
        traceability_lot_code="tlc-x",
        errors=[{"msg": "e"}],
        extracted={"nested": {"weird": _Weird(), "ok": "str"}},
    )
    assert record["extracted"]["nested"]["weird"] == "weird-value"
    assert record["extracted"]["nested"]["ok"] == "str"


def test_structured_warning_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    import logging as _logging

    with caplog.at_level(_logging.WARNING, logger="edi-ingestion"):
        record_edi_rejection(
            tenant_id=TENANT,
            transaction_set="861",
            traceability_lot_code="tlc-y",
            errors=[{"msg": "e"}],
        )
    assert any("edi_fsma_rejection_recorded" in rec.message for rec in caplog.records), (
        "rejection must always emit a structured warning for ops"
    )


def test_rejection_is_committed_with_tenant_context(durable_store):
    rows, sessions, _ = durable_store
    record = record_edi_rejection(
        tenant_id=TENANT,
        transaction_set="856",
        traceability_lot_code="LOT-A",
        errors=[{"msg": "missing date"}],
        extracted={"line_items": [{"traceability_lot_code": "LOT-A"}]},
    )
    assert len(rows) == 1
    assert json.loads(rows[0]["reasons"]) == record
    assert rows[0]["tenant_id"] == TENANT
    session = sessions[0]
    assert "set_config('app.tenant_id'" in session.statements[0][0]
    assert session.statements[0][1] == {"tid": TENANT}
    assert "INSERT INTO fsma.rule_rejections" in session.statements[1][0]
    assert "RETURNING" not in session.statements[1][0]
    assert "edi_rejection" in session.statements[1][0]
    assert session.committed and session.closed
    assert not session.rolled_back


def test_committed_evidence_survives_cache_eviction_and_reset(monkeypatch, durable_store):
    rows, _, _ = durable_store
    monkeypatch.setattr(rejection_log, "_EDI_REJECTION_CAP_PER_TENANT", 1)
    records = [
        record_edi_rejection(
            tenant_id=TENANT,
            transaction_set="856",
            traceability_lot_code=lot,
            errors=[{"msg": "missing date"}],
        )
        for lot in ("LOT-A", "LOT-B")
    ]
    assert list_edi_rejections(TENANT) == [records[1]]
    reset_edi_rejections()
    assert list_edi_rejections(TENANT) == []
    assert [json.loads(row["reasons"]) for row in rows] == records


def test_full_document_and_rejected_date_are_persisted(durable_store, caplog):
    rows, _, _ = durable_store
    source_document = "ST*856*0001~BSN*00*DOC-A*20261001~SE*3*0001~ST*856*0002~BSN*00*DOC-B*bad-date~SE*3*0002~"
    record = record_edi_rejection(
        tenant_id=TENANT,
        transaction_set="856",
        traceability_lot_code=None,
        errors=[{"msg": "invalid date"}],
        reason="invalid_event_date",
        rejected_date="bad-date",
        source_document=source_document,
    )
    assert json.loads(rows[0]["reasons"])["source_document"] == source_document
    assert record["rejected_date"] == "bad-date"
    assert "reason=invalid_event_date" in caplog.text
    assert "rejected_date='bad-date'" in caplog.text
    assert source_document not in caplog.text


@pytest.mark.parametrize("failure", ["connect", "insert", "commit"])
def test_storage_failure_never_returns_or_caches_a_rejection(durable_store, caplog, failure):
    rows, sessions, failures = durable_store
    failures.append(failure)
    with pytest.raises(rejection_log.EDIRejectionUnavailable, match="storage is unavailable"):
        record_edi_rejection(
            tenant_id=TENANT,
            transaction_set="856",
            traceability_lot_code="LOT-A",
            errors=[{"msg": "missing date"}],
        )
    assert rows == []
    assert list_edi_rejections(TENANT) == []
    if sessions:
        assert sessions[0].rolled_back and sessions[0].closed
    assert "edi_fsma_rejection_recorded" not in caplog.text
    assert "error_type=RuntimeError" in caplog.text
    assert "simulated storage failure" not in caplog.text
