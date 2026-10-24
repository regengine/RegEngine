"""EPCIS document receipts: hashing, sanitized summaries, fail open writes.

No database. Fake sessions record what the writer and the count reader send.
"""

from __future__ import annotations

import hashlib
import uuid
from contextlib import nullcontext
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from shared.epcis_receipts import (
    MAX_ERROR_SUMMARY_LENGTH,
    RECEIPT_ACCEPTED,
    RECEIPT_REJECTED,
    RECEIPT_STATUSES,
    document_sha256,
    fetch_receipt_counts,
    record_epcis_receipt,
    summarize_error,
    summarize_failed_events,
)


class FakeSession:
    def __init__(self, fail_on_insert: bool = False) -> None:
        self.statements: list[tuple[str, dict]] = []
        self.fail_on_insert = fail_on_insert
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def execute(self, statement, params=None):
        sql = str(statement)
        if self.fail_on_insert and "INSERT" in sql:
            raise RuntimeError(str(uuid.uuid4()))
        self.statements.append((sql, dict(params or {})))

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def _raw() -> bytes:
    return uuid.uuid4().hex.encode()


# --- hashing and summaries ---------------------------------------------------


def test_document_sha256_is_hex_digest_of_raw_body():
    raw = _raw()
    assert document_sha256(raw) == hashlib.sha256(raw).hexdigest()


def test_statuses_match_the_table_check_constraint():
    assert RECEIPT_STATUSES == ("accepted", "rejected")


def test_summary_keeps_class_status_and_error_code_only():
    secret = str(uuid.uuid4())
    exc = HTTPException(status_code=422, detail={"error": "fsma_validation_failed", "message": secret})
    assert summarize_error(exc) == "HTTPException 422 fsma_validation_failed"


@pytest.mark.parametrize(
    "detail_template",
    ["Unmapped bizStep: {}", "EPCIS event '{}' not found", "{}", "Unsupported event type {}"],
)
def test_summary_drops_string_details(detail_template):
    # Plain words included: a string detail can interpolate a payload value
    # with no punctuation around it.
    value = uuid.uuid4().hex
    summary = summarize_error(HTTPException(status_code=400, detail=detail_template.format(value)))
    assert value not in summary
    assert summary == "HTTPException 400"


def test_summary_drops_an_error_code_that_is_not_a_code():
    value = f"{uuid.uuid4()} {uuid.uuid4()}"
    summary = summarize_error(HTTPException(status_code=400, detail={"error": value}))
    assert summary == "HTTPException 400"


def test_summary_of_plain_exception_is_class_name_only():
    value = str(uuid.uuid4())
    assert summarize_error(ValueError(value)) == ValueError.__name__


def test_summary_is_truncated():
    long_name = "E" * (MAX_ERROR_SUMMARY_LENGTH * 2)
    exc = type(long_name, (Exception,), {})()
    assert len(summarize_error(exc)) == MAX_ERROR_SUMMARY_LENGTH


def test_failed_event_summary_counts_only():
    failed, total = len(RECEIPT_STATUSES), MAX_ERROR_SUMMARY_LENGTH
    assert summarize_failed_events(failed, total) == f"{failed} of {total} events failed"


# --- writer ------------------------------------------------------------------


def test_record_sets_tenant_guc_then_inserts_and_commits():
    tenant = str(uuid.uuid4())
    raw = _raw()
    session = FakeSession()

    assert record_epcis_receipt(tenant, raw, RECEIPT_ACCEPTED, session_factory=lambda: session) is True

    (guc_sql, guc_params), (insert_sql, insert_params) = session.statements
    assert "set_config('app.tenant_id'" in guc_sql
    assert tenant in guc_params.values()
    assert "fsma.epcis_document_receipts" in insert_sql
    assert insert_params == {
        "tenant_id": tenant,
        "document_sha256": document_sha256(raw),
        "status": RECEIPT_ACCEPTED,
        "error_summary": None,
    }
    assert session.committed and session.closed


def test_record_truncates_error_summary():
    session = FakeSession()
    summary = "x" * (MAX_ERROR_SUMMARY_LENGTH * 2)
    record_epcis_receipt(str(uuid.uuid4()), _raw(), RECEIPT_REJECTED, summary, session_factory=lambda: session)
    assert len(session.statements[-1][1]["error_summary"]) == MAX_ERROR_SUMMARY_LENGTH


def test_record_never_raises_on_insert_failure():
    session = FakeSession(fail_on_insert=True)
    assert record_epcis_receipt(str(uuid.uuid4()), _raw(), RECEIPT_REJECTED, session_factory=lambda: session) is False
    assert session.rolled_back and session.closed and not session.committed


def test_record_never_raises_when_session_factory_fails():
    def _broken():
        raise ConnectionError(str(uuid.uuid4()))

    assert record_epcis_receipt(str(uuid.uuid4()), _raw(), RECEIPT_ACCEPTED, session_factory=_broken) is False


def test_record_without_session_is_skipped():
    assert record_epcis_receipt(str(uuid.uuid4()), _raw(), RECEIPT_ACCEPTED, session_factory=lambda: None) is False


def test_record_skips_non_uuid_tenant_without_opening_a_session():
    def _must_not_open():  # pragma: no cover (must not run)
        raise AssertionError("no session expected")

    assert record_epcis_receipt(uuid.uuid4().hex[:8], _raw(), RECEIPT_ACCEPTED, session_factory=_must_not_open) is False


def test_record_rejects_unknown_status():
    session = FakeSession()
    status = uuid.uuid4().hex
    assert record_epcis_receipt(str(uuid.uuid4()), _raw(), status, session_factory=lambda: session) is False
    assert session.statements == []


# --- count reader ------------------------------------------------------------


class CountSession:
    def __init__(self, row: dict | None = None, error: Exception | None = None) -> None:
        self.row = row
        self.error = error
        self.params: dict | None = None

    def begin_nested(self):
        return nullcontext()

    def execute(self, statement, params):
        if self.error:
            raise self.error
        self.params = params
        row = self.row
        return type("Result", (), {"mappings": lambda _self: type("M", (), {"one": lambda _m: row})()})()


def test_counts_are_tenant_and_window_scoped():
    tenant = str(uuid.uuid4())
    since = datetime.now(timezone.utc)
    rejected, total = len(RECEIPT_STATUSES), MAX_ERROR_SUMMARY_LENGTH
    session = CountSession(row={"rejected": rejected, "total": total})

    assert fetch_receipt_counts(session, tenant, since) == (rejected, total)
    assert session.params == {"tid": tenant, "since": since}


def test_unreadable_receipts_table_returns_none():
    session = CountSession(error=RuntimeError(str(uuid.uuid4())))
    assert fetch_receipt_counts(session, str(uuid.uuid4()), datetime.now(timezone.utc)) is None
