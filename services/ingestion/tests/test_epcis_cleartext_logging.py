"""CodeQL py/clear-text-logging-sensitive-data regression tests.

The EPCIS persistence and validation warning logs must not carry the tenant
id, traceability lot code, event time, raw validation status or exception
text. Only non-sensitive context (indexes, counts, error types) may appear.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

from app.epcis import (
    persistence as pmod,  # noqa: E402
    validation as vmod,  # noqa: E402
)
from fastapi import HTTPException  # noqa: E402

TENANT = "tenant-private-7f3a"
PRIVATE_TEXT = "lot TLC-PRIVATE-991 for tenant-private-7f3a"


def _log_text(caplog) -> str:
    return "\n".join(r.getMessage() for r in caplog.records)


def _assert_clean(caplog) -> None:
    text = _log_text(caplog)
    assert TENANT not in text
    assert "TLC-PRIVATE-991" not in text


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
        lambda t, e: {"kde_map": {"fsma_validation_status": "TLC-PRIVATE-991"}},
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
        result = vmod._validate_as_fsma_event({"event_type": "not-a-cte", "tlc": "TLC-PRIVATE-991"}, tenant_id=TENANT)
    assert result is None
    assert "fsma_event_validation_failed" in _log_text(caplog)
    # The audit trail still records the failure and its tenant.
    assert audited and audited[0][1] == TENANT
    _assert_clean(caplog)
