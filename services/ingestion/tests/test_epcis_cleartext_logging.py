"""CodeQL py/clear-text-logging-sensitive-data regression tests.

The EPCIS persistence and validation warning logs must not carry the tenant
id, traceability lot code, event time, raw validation status or exception
text. Only non-sensitive context (indexes, counts, error types) may appear.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

from app.epcis import (
    persistence as pmod,  # noqa: E402
    validation as vmod,  # noqa: E402
)
from fastapi import HTTPException  # noqa: E402

TENANT = str(uuid4())
TLC = str(uuid4())
PRIVATE_TEXT = f"private-exception-{uuid4()}"


def _log_text(caplog) -> str:
    return "\n".join(r.getMessage() for r in caplog.records)


def _assert_clean(caplog) -> None:
    text = _log_text(caplog)
    assert TENANT not in text
    assert TLC not in text
    assert PRIVATE_TEXT not in text


def test_single_event_refused_on_prepare_422_does_not_log_tenant(monkeypatch, caplog):
    def _raise(tenant_id, event):
        raise HTTPException(status_code=422, detail={"error": "fsma_validation_failed"})

    monkeypatch.setattr(pmod, "_prepare_event_for_persistence", _raise)
    monkeypatch.setattr(pmod, "_fsma_strict_mode", lambda: True)
    with caplog.at_level(logging.WARNING), pytest.raises(ValueError, match="E_EPCIS_UNVALIDATED"):
        pmod._ingest_single_event_db(TENANT, {})
    assert "epcis_single_event_refused_unvalidated" in _log_text(caplog)
    _assert_clean(caplog)


def test_single_event_refused_on_status_does_not_log_tenant_or_status(monkeypatch, caplog):
    monkeypatch.setattr(
        pmod,
        "_prepare_event_for_persistence",
        lambda t, e: {"kde_map": {"fsma_validation_status": TLC}},
    )
    monkeypatch.setattr(pmod, "_fsma_strict_mode", lambda: True)
    with caplog.at_level(logging.WARNING), pytest.raises(ValueError, match="E_EPCIS_UNVALIDATED"):
        pmod._ingest_single_event_db(TENANT, {})
    assert "status_present=True" in _log_text(caplog)
    _assert_clean(caplog)


def test_ingest_refused_unvalidated_does_not_log_tenant(monkeypatch, caplog):
    def _raise(tenant_id, event):
        raise ValueError("E_EPCIS_UNVALIDATED")

    monkeypatch.setattr(pmod, "_ingest_single_event_db", _raise)
    with caplog.at_level(logging.WARNING), pytest.raises(HTTPException) as exc_info:
        pmod._ingest_single_event(TENANT, {})
    assert exc_info.value.status_code == 422
    assert "epcis_ingest_refused_unvalidated" in _log_text(caplog)
    _assert_clean(caplog)


def test_unsupported_cte_logs_error_type_not_message(monkeypatch, caplog):
    def _raise(tenant_id, event):
        raise ValueError(f"{PRIVATE_TEXT} is not a recognized FSMA 204 CTE type")

    monkeypatch.setattr(pmod, "_ingest_single_event_db", _raise)
    with caplog.at_level(logging.WARNING), pytest.raises(HTTPException) as exc_info:
        pmod._ingest_single_event(TENANT, {})
    assert exc_info.value.status_code == 422
    assert "error_type=ValueError" in _log_text(caplog)
    _assert_clean(caplog)


def test_validation_failure_log_omits_tenant(monkeypatch, caplog):
    audited = []
    monkeypatch.setattr(vmod, "_audit_log_validation_failure", lambda e, t, n: audited.append((e, t)))
    with caplog.at_level(logging.WARNING):
        result = vmod._validate_as_fsma_event({"event_type": "not-a-cte", "tlc": TLC}, tenant_id=TENANT)
    assert result is None
    assert "fsma_event_validation_failed" in _log_text(caplog)
    # The audit trail still records the failure and its tenant.
    assert audited and audited[0][1] == TENANT
    _assert_clean(caplog)


@pytest.mark.parametrize(
    ("ingest", "warning"),
    [
        (pmod._ingest_single_event_fallback, "epcis_fsma_validation_rejected"),
        (pmod._prepare_event_for_persistence, "epcis_fsma_validation_rejected_db"),
    ],
)
def test_fsma_rejection_logs_omit_private_values(ingest, warning, monkeypatch, caplog):
    audited = []
    monkeypatch.setattr(vmod, "_audit_log_validation_failure", lambda e, t, n: audited.append((e, t, n)))
    monkeypatch.setattr(pmod, "_fsma_strict_mode", lambda: True)
    monkeypatch.setattr(pmod, "_epcis_store", {})
    monkeypatch.setattr(pmod, "_epcis_idempotency_index", {})
    event = {
        "type": "ObjectEvent",
        "eventTime": datetime.now(timezone.utc).isoformat(),
        "action": "OBSERVE",
        "bizStep": "receiving",
        "ilmd": {"fsma:traceabilityLotCode": TLC},
    }

    with caplog.at_level(logging.WARNING), pytest.raises(HTTPException) as exc_info:
        ingest(TENANT, event)

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["error"] == "fsma_validation_failed"
    assert warning in [record.getMessage() for record in caplog.records]
    assert audited[0][1] == TENANT
    assert audited[0][2]["tlc"] == TLC
    assert any(error["loc"] == ("tlc",) for error in audited[0][0])
    _assert_clean(caplog)


def test_batch_rollback_logs_error_type_not_private_exception(monkeypatch, caplog):
    session = Mock()

    def _raise(db_session, tenant_id, prepared):
        raise ValueError(PRIVATE_TEXT)

    monkeypatch.setattr(pmod, "_prepare_event_for_persistence", lambda t, e: e)
    monkeypatch.setattr(pmod, "get_db_safe", lambda: session)
    monkeypatch.setattr(pmod, "_persist_prepared_event_in_session", _raise)
    with caplog.at_level(logging.WARNING), pytest.raises(HTTPException) as exc_info:
        pmod._ingest_batch_events_db_atomic(TENANT, [{"tlc": TLC}])

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["failed_index"] == 0
    session.rollback.assert_called_once_with()
    session.commit.assert_not_called()
    session.close.assert_called_once_with()
    assert "epcis_batch_rollback failed_index=0 batch_size=1 error_type=ValueError" in _log_text(caplog)
    _assert_clean(caplog)


def test_pydantic_validation_failure_log_omits_private_values(monkeypatch, caplog):
    audited = []
    monkeypatch.setattr(vmod, "_audit_log_validation_failure", lambda e, t, n: audited.append((e, t, n)))
    normalized = {
        "event_type": "receiving",
        "tlc": TLC,
        "event_time": datetime.now(timezone.utc).isoformat(),
    }
    with caplog.at_level(logging.WARNING):
        result = vmod._validate_as_fsma_event(normalized, tenant_id=TENANT)

    assert result is None
    assert "fsma_event_validation_failed" in _log_text(caplog)
    assert audited[0][1:] == (TENANT, normalized)
    assert any(error["loc"] == ("tlc",) and error["type"] == "value_error" for error in audited[0][0])
    _assert_clean(caplog)
