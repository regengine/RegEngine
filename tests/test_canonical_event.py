"""
Tests for the Canonical TraceabilityEvent Model.

Validates:
1. Webhook event normalization
2. EPCIS event normalization
3. CSV row normalization
4. Hash computation and idempotency
5. Provenance metadata
6. Amendment chain semantics
"""

import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from shared.canonical_event import (
    CTEType,
    EventStatus,
    IngestionSource,
    ProvenanceMetadata,
    TraceabilityEvent,
    normalize_webhook_event,
    normalize_epcis_event,
    normalize_csv_row,
    SCHEMA_VERSION,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

class MockWebhookEvent:
    """Simulates an IngestEvent from webhook_models.py."""
    def __init__(self, **kwargs):
        self.cte_type = kwargs.get("cte_type", "receiving")
        self.traceability_lot_code = kwargs.get("traceability_lot_code", "00614141000001ABC123")
        self.product_description = kwargs.get("product_description", "Romaine Lettuce, Whole Head")
        self.quantity = kwargs.get("quantity", 500.0)
        self.unit_of_measure = kwargs.get("unit_of_measure", "cases")
        self.location_gln = kwargs.get("location_gln", "0061414100001")
        self.location_name = kwargs.get("location_name", "Acme Distribution Center")
        self.timestamp = kwargs.get("timestamp", "2026-03-25T14:30:00Z")
        self.kdes = kwargs.get("kdes", {
            "receive_date": "2026-03-25",
            "reference_document": "BOL-2026-0325-001",
            "immediate_previous_source": "Fresh Farms LLC",
            "tlc_source_reference": "0061414100002",
        })
        self.input_traceability_lot_codes = kwargs.get("input_traceability_lot_codes", None)


TENANT_ID = str(uuid4())


# ---------------------------------------------------------------------------
# TraceabilityEvent Construction
# ---------------------------------------------------------------------------

class TestTraceabilityEventModel:
    def test_basic_construction(self):
        event = TraceabilityEvent(
            tenant_id=UUID(TENANT_ID),
            source_system=IngestionSource.WEBHOOK_API,
            event_type=CTEType.RECEIVING,
            event_timestamp="2026-03-25T14:30:00Z",
            traceability_lot_code="00614141000001ABC123",
            quantity=500.0,
            unit_of_measure="cases",
        )
        assert event.event_type == CTEType.RECEIVING
        assert event.quantity == 500.0
        assert event.status == EventStatus.ACTIVE
        assert event.schema_version == SCHEMA_VERSION

    def test_timestamp_parsing_iso(self):
        event = TraceabilityEvent(
            tenant_id=UUID(TENANT_ID),
            source_system=IngestionSource.WEBHOOK_API,
            event_type=CTEType.SHIPPING,
            event_timestamp="2026-03-25T14:30:00+05:00",
            traceability_lot_code="TLC001",
            quantity=100.0,
            unit_of_measure="cases",
        )
        assert event.event_timestamp.tzinfo is not None

    def test_timestamp_parsing_z_suffix(self):
        event = TraceabilityEvent(
            tenant_id=UUID(TENANT_ID),
            source_system=IngestionSource.WEBHOOK_API,
            event_type=CTEType.SHIPPING,
            event_timestamp="2026-03-25T14:30:00Z",
            traceability_lot_code="TLC001",
            quantity=100.0,
            unit_of_measure="cases",
        )
        assert event.event_timestamp.tzinfo is not None

    def test_hash_computation(self):
        event = TraceabilityEvent(
            tenant_id=UUID(TENANT_ID),
            source_system=IngestionSource.WEBHOOK_API,
            event_type=CTEType.RECEIVING,
            event_timestamp="2026-03-25T14:30:00Z",
            traceability_lot_code="TLC001",
            quantity=100.0,
            unit_of_measure="cases",
        )
        sha = event.compute_sha256_hash()
        assert len(sha) == 64  # SHA-256 hex digest
        assert sha == event.compute_sha256_hash()  # deterministic

    def test_idempotency_key_deterministic(self):
        event = TraceabilityEvent(
            tenant_id=UUID(TENANT_ID),
            source_system=IngestionSource.WEBHOOK_API,
            event_type=CTEType.RECEIVING,
            event_timestamp="2026-03-25T14:30:00Z",
            traceability_lot_code="TLC001",
            quantity=100.0,
            unit_of_measure="cases",
            kdes={"receive_date": "2026-03-25"},
        )
        key1 = event.compute_idempotency_key()
        key2 = event.compute_idempotency_key()
        assert key1 == key2
        assert len(key1) == 64

    def test_idempotency_key_different_events(self):
        event_a = TraceabilityEvent(
            tenant_id=UUID(TENANT_ID),
            source_system=IngestionSource.WEBHOOK_API,
            event_type=CTEType.RECEIVING,
            event_timestamp="2026-03-25T14:30:00Z",
            traceability_lot_code="TLC001",
            quantity=100.0,
            unit_of_measure="cases",
        )
        event_b = TraceabilityEvent(
            tenant_id=UUID(TENANT_ID),
            source_system=IngestionSource.WEBHOOK_API,
            event_type=CTEType.SHIPPING,  # different type
            event_timestamp="2026-03-25T14:30:00Z",
            traceability_lot_code="TLC001",
            quantity=100.0,
            unit_of_measure="cases",
        )
        assert event_a.compute_idempotency_key() != event_b.compute_idempotency_key()

    def test_prepare_for_persistence(self):
        event = TraceabilityEvent(
            tenant_id=UUID(TENANT_ID),
            source_system=IngestionSource.WEBHOOK_API,
            event_type=CTEType.RECEIVING,
            event_timestamp="2026-03-25T14:30:00Z",
            traceability_lot_code="TLC001",
            quantity=100.0,
            unit_of_measure="cases",
            product_reference="Romaine Lettuce",
        )
        result = event.prepare_for_persistence()
        assert result.sha256_hash is not None
        assert result.idempotency_key is not None
        assert result.normalized_payload["event_type"] == "receiving"
        assert result.normalized_payload["traceability_lot_code"] == "TLC001"

    def test_amendment_chain(self):
        original = TraceabilityEvent(
            tenant_id=UUID(TENANT_ID),
            source_system=IngestionSource.WEBHOOK_API,
            event_type=CTEType.RECEIVING,
            event_timestamp="2026-03-25T14:30:00Z",
            traceability_lot_code="TLC001",
            quantity=100.0,
            unit_of_measure="cases",
        )

        amended = TraceabilityEvent(
            tenant_id=UUID(TENANT_ID),
            source_system=IngestionSource.WEBHOOK_API,
            event_type=CTEType.RECEIVING,
            event_timestamp="2026-03-25T14:30:00Z",
            traceability_lot_code="TLC001",
            quantity=120.0,  # corrected quantity
            unit_of_measure="cases",
            supersedes_event_id=original.event_id,
        )

        assert amended.supersedes_event_id == original.event_id
        assert amended.event_id != original.event_id


# ---------------------------------------------------------------------------
# Webhook Normalization
# ---------------------------------------------------------------------------

class TestWebhookNormalization:
    def test_basic_normalization(self):
        webhook_event = MockWebhookEvent()
        canonical = normalize_webhook_event(webhook_event, TENANT_ID)

        assert canonical.event_type == CTEType.RECEIVING
        assert canonical.traceability_lot_code == "00614141000001ABC123"
        assert canonical.product_reference == "Romaine Lettuce, Whole Head"
        assert canonical.quantity == 500.0
        assert canonical.source_system == IngestionSource.WEBHOOK_API
        assert canonical.sha256_hash is not None
        assert canonical.idempotency_key is not None

    def test_raw_payload_preserved(self):
        webhook_event = MockWebhookEvent()
        canonical = normalize_webhook_event(webhook_event, TENANT_ID)

        assert canonical.raw_payload["cte_type"] == "receiving"
        assert canonical.raw_payload["traceability_lot_code"] == "00614141000001ABC123"
        assert canonical.raw_payload["kdes"]["reference_document"] == "BOL-2026-0325-001"

    def test_provenance_metadata(self):
        webhook_event = MockWebhookEvent()
        canonical = normalize_webhook_event(webhook_event, TENANT_ID)

        assert canonical.provenance_metadata.mapper_name == "webhook_v2_normalizer"
        assert canonical.provenance_metadata.original_format == "json"
        assert "webhook_kde_extraction" in canonical.provenance_metadata.normalization_rules_applied

    def test_facility_reference_extraction(self):
        webhook_event = MockWebhookEvent(
            kdes={
                "ship_from_gln": "0061414100002",
                "ship_to_location": "Walmart Store #1234",
            }
        )
        canonical = normalize_webhook_event(webhook_event, TENANT_ID)
        # from_facility should resolve from location_gln or kdes
        assert canonical.from_facility_reference is not None

    def test_shipping_event_facility_mapping(self):
        webhook_event = MockWebhookEvent(
            cte_type="shipping",
            kdes={
                "ship_from_location": "Warehouse A",
                "ship_to_location": "Distribution Center B",
            }
        )
        canonical = normalize_webhook_event(webhook_event, TENANT_ID)
        assert canonical.event_type == CTEType.SHIPPING

    def test_transformation_with_input_tlcs(self):
        webhook_event = MockWebhookEvent(
            cte_type="transformation",
            input_traceability_lot_codes=["INPUT-TLC-001", "INPUT-TLC-002"],
        )
        canonical = normalize_webhook_event(webhook_event, TENANT_ID)
        assert canonical.event_type == CTEType.TRANSFORMATION
        assert canonical.raw_payload.get("input_traceability_lot_codes") == ["INPUT-TLC-001", "INPUT-TLC-002"]

    def test_normalized_payload_structure(self):
        webhook_event = MockWebhookEvent()
        canonical = normalize_webhook_event(webhook_event, TENANT_ID)

        np = canonical.normalized_payload
        assert "event_id" in np
        assert "event_type" in np
        assert "traceability_lot_code" in np
        assert "kdes" in np
        assert "schema_version" in np
        assert np["schema_version"] == SCHEMA_VERSION


# ---------------------------------------------------------------------------
# EPCIS Normalization
# ---------------------------------------------------------------------------

class TestEPCISNormalization:
    def test_basic_epcis_normalization(self):
        epcis_data = {
            "type": "ObjectEvent",
            "eventTime": "2026-03-25T14:30:00Z",
            "bizStep": "urn:epcglobal:cbv:bizstep:receiving",
            "readPoint": {"id": "urn:epc:id:sgln:061414100000.0.0"},
            "epcList": ["urn:epc:id:sgtin:061414100001.ABC123"],
            "quantity": {"value": 500, "uom": "cases"},
        }
        canonical = normalize_epcis_event(epcis_data, TENANT_ID)

        assert canonical.event_type == CTEType.RECEIVING
        assert canonical.source_system == IngestionSource.EPCIS_API
        assert canonical.epcis_biz_step == "urn:epcglobal:cbv:bizstep:receiving"
        assert canonical.raw_payload == epcis_data

    def test_epcis_provenance(self):
        epcis_data = {
            "eventTime": "2026-03-25T14:30:00Z",
            "bizStep": "shipping",
            "epcList": [],
            "traceability_lot_code": "TLC-EPCIS-001",
            "quantity": {"value": 100, "uom": "kg"},
        }
        canonical = normalize_epcis_event(epcis_data, TENANT_ID)
        assert canonical.provenance_metadata.mapper_name == "epcis_normalizer"
        assert "epcis_bizstep_mapping" in canonical.provenance_metadata.normalization_rules_applied


# ---------------------------------------------------------------------------
# CSV Normalization
# ---------------------------------------------------------------------------

class TestCSVNormalization:
    def test_basic_csv_normalization(self):
        row = {
            "Event Type": "receiving",
            "TLC": "TLC-CSV-001",
            "Product": "Fresh Salmon Fillet",
            "Qty": "250",
            "UOM": "lbs",
            "Date": "2026-03-25",
        }
        column_mapping = {
            "Event Type": "event_type",
            "TLC": "traceability_lot_code",
            "Product": "product_description",
            "Qty": "quantity",
            "UOM": "unit_of_measure",
            "Date": "event_timestamp",
        }
        canonical = normalize_csv_row(row, TENANT_ID, column_mapping, source_file_name="import.csv")

        assert canonical.event_type == CTEType.RECEIVING
        assert canonical.traceability_lot_code == "TLC-CSV-001"
        assert canonical.source_system == IngestionSource.CSV_UPLOAD
        assert canonical.raw_payload == row

    def test_csv_unmapped_columns_become_kdes(self):
        row = {
            "Event Type": "shipping",
            "TLC": "TLC-CSV-002",
            "Qty": "100",
            "UOM": "cases",
            "Date": "2026-03-25",
            "Carrier": "FedEx Freight",
            "BOL Number": "BOL-12345",
        }
        column_mapping = {
            "Event Type": "event_type",
            "TLC": "traceability_lot_code",
            "Qty": "quantity",
            "UOM": "unit_of_measure",
            "Date": "event_timestamp",
        }
        canonical = normalize_csv_row(row, TENANT_ID, column_mapping)

        assert "Carrier" in canonical.kdes
        assert canonical.kdes["Carrier"] == "FedEx Freight"
        assert "BOL Number" in canonical.kdes

    def test_csv_event_type_inference(self):
        row = {
            "Type": "recv",  # non-standard, will be inferred
            "TLC": "TLC-CSV-003",
            "Qty": "50",
            "UOM": "kg",
            "Date": "2026-03-25",
        }
        column_mapping = {"Type": "event_type", "TLC": "traceability_lot_code", "Qty": "quantity", "UOM": "unit_of_measure", "Date": "event_timestamp"}
        canonical = normalize_csv_row(row, TENANT_ID, column_mapping)

        # Unknown type defaults to "receiving" with lower confidence
        assert canonical.event_type == CTEType.RECEIVING
        assert canonical.confidence_score < 1.0

    def test_csv_provenance_tracks_source_file(self):
        row = {"TLC": "TLC-004", "Qty": "10", "UOM": "cases", "Date": "2026-03-25"}
        column_mapping = {"TLC": "traceability_lot_code", "Qty": "quantity", "UOM": "unit_of_measure", "Date": "event_timestamp"}
        canonical = normalize_csv_row(
            row, TENANT_ID, column_mapping,
            source_file_name="supplier_data_q1.csv",
            row_number=42,
        )
        assert canonical.provenance_metadata.source_file_name == "supplier_data_q1.csv"
        assert canonical.source_record_id == "42"


# ---------------------------------------------------------------------------
# ProvenanceMetadata
# ---------------------------------------------------------------------------

class TestProvenanceMetadata:
    def test_default_provenance(self):
        p = ProvenanceMetadata()
        assert p.mapper_name == "unknown"
        assert p.mapper_version == "1.0.0"
        assert p.extraction_confidence == 1.0

    def test_provenance_to_dict(self):
        p = ProvenanceMetadata(
            mapper_name="test_mapper",
            original_format="csv",
            normalization_rules_applied=["rule_a", "rule_b"],
        )
        d = p.to_dict()
        assert d["mapper_name"] == "test_mapper"
        assert d["original_format"] == "csv"
        assert "rule_a" in d["normalization_rules_applied"]
