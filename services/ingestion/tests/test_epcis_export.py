"""Data-free structural and error-path tests for EPCIS export validation."""

import sys
from pathlib import Path

_ingestion_dir = Path(__file__).resolve().parent.parent
if str(_ingestion_dir) not in sys.path:
    sys.path.insert(0, str(_ingestion_dir))

_services_dir = _ingestion_dir.parent
if str(_services_dir) not in sys.path:
    sys.path.insert(0, str(_services_dir))

from app.epcis_export import _validate_epcis_document


def test_reports_missing_required_document_fields():
    errors = _validate_epcis_document({})

    for field in ("@context", "EPCISDocument", "schemaVersion", "creationDate", "eventList"):
        assert any(field in error for error in errors)


def test_reports_empty_event_list():
    errors = _validate_epcis_document({"epcisBody": {"eventList": []}})

    assert any("eventList" in error for error in errors)


def test_reports_bad_schema_version():
    errors = _validate_epcis_document({"schemaVersion": ""})

    assert any("schemaVersion" in error for error in errors)


def test_reports_missing_event_fields():
    errors = _validate_epcis_document({"epcisBody": {"eventList": [{}]}})

    assert any("type" in error for error in errors)
    assert any("eventTime" in error for error in errors)
