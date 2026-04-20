"""Unit tests for the EDI rejection log (#1174).

Covers the mechanism that keeps FSMA-invalid EDI documents out of the
canonical ingestion stream. The route-level assertion that
``ingest_events`` is not invoked lives in
``test_edi_ingestion_api.py::test_document_ingest_strict_false_query_advisory``;
this file focuses on the storage API so route regressions can be
diagnosed against a known-good primitive.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

from app.edi_ingestion.rejection_log import (
    list_edi_rejections,
    record_edi_rejection,
    reset_edi_rejections,
)


TENANT = "00000000-0000-0000-0000-0000000000aa"
OTHER_TENANT = "00000000-0000-0000-0000-0000000000bb"


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
    assert any(
        "edi_fsma_rejection_recorded" in rec.message for rec in caplog.records
    ), "rejection must always emit a structured warning for ops"
