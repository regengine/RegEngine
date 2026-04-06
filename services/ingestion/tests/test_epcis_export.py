"""Unit tests for EPCIS export module (app/epcis_export.py)."""

import sys
from pathlib import Path

_ingestion_dir = Path(__file__).resolve().parent.parent
if str(_ingestion_dir) not in sys.path:
    sys.path.insert(0, str(_ingestion_dir))

_services_dir = _ingestion_dir.parent
if str(_services_dir) not in sys.path:
    sys.path.insert(0, str(_services_dir))

import pytest

from app.epcis_export import _CTE_TO_BIZSTEP, _validate_epcis_document


EXPECTED_CTE_TYPES = {
    "receiving", "shipping", "transformation",
    "initial_packing", "harvesting", "cooling",
    "first_land_based_receiving",
}


class TestCTEToBizStep:
    """Tests for the _CTE_TO_BIZSTEP mapping."""

    def test_has_all_cte_types(self):
        """EPCIS bizstep mapping covers all 7 canonical FSMA 204 CTEs."""
        assert set(_CTE_TO_BIZSTEP.keys()) == EXPECTED_CTE_TYPES

    def test_all_uris_start_with_bizstep_prefix(self):
        prefix = "urn:epcglobal:cbv:bizstep:"
        for cte_type, uri in _CTE_TO_BIZSTEP.items():
            assert uri.startswith(prefix), f"{cte_type} URI does not start with {prefix}: {uri}"


def _valid_epcis_doc(**overrides):
    """Return a minimal valid EPCIS 2.0 JSON-LD document."""
    doc = {
        "@context": ["https://ref.gs1.org/standards/epcis/2.0.0/epcis-context.jsonld"],
        "type": "EPCISDocument",
        "schemaVersion": "2.0",
        "creationDate": "2026-03-01T00:00:00Z",
        "epcisBody": {
            "eventList": [
                {
                    "type": "ObjectEvent",
                    "eventTime": "2026-03-01T12:00:00Z",
                    "action": "OBSERVE",
                    "bizStep": "urn:epcglobal:cbv:bizstep:shipping",
                }
            ]
        },
    }
    doc.update(overrides)
    return doc


class TestValidateEpcisDocument:
    """Tests for _validate_epcis_document."""

    def test_catches_missing_context(self):
        doc = _valid_epcis_doc()
        del doc["@context"]
        errors = _validate_epcis_document(doc)
        assert any("@context" in e for e in errors)

    def test_catches_wrong_type(self):
        doc = _valid_epcis_doc(type="NotAnEPCISDocument")
        errors = _validate_epcis_document(doc)
        assert any("EPCISDocument" in e for e in errors)

    def test_passes_valid_document(self):
        doc = _valid_epcis_doc()
        errors = _validate_epcis_document(doc)
        assert errors == []

    def test_catches_missing_schema_version(self):
        doc = _valid_epcis_doc()
        del doc["schemaVersion"]
        errors = _validate_epcis_document(doc)
        assert any("schemaVersion" in e for e in errors)

    def test_catches_empty_event_list(self):
        doc = _valid_epcis_doc()
        doc["epcisBody"]["eventList"] = []
        errors = _validate_epcis_document(doc)
        assert any("eventList" in e for e in errors)

    def test_catches_invalid_event_type(self):
        doc = _valid_epcis_doc()
        doc["epcisBody"]["eventList"][0]["type"] = "BadEventType"
        errors = _validate_epcis_document(doc)
        assert any("BadEventType" in e for e in errors)
