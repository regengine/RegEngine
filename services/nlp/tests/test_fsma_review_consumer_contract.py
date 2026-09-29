"""The signed FSMA review message must survive the admin consumer projection."""

import json
import sys
from copy import deepcopy
from dataclasses import fields
from datetime import datetime, timezone

import pytest

from services.nlp.app.extractors.fsma_extractor import FSMAExtractor
from services.nlp.app.extractors.fsma_types import (
    CTE,
    KDE,
    CTEType,
    DocumentType,
    ExtractionConfidence,
    FSMAExtractionResult,
)

TENANT_ID = "11111111-1111-1111-1111-111111111111"
DOC_ID = "fsma-review-contract"
DOC_HASH = "fsma-review-document-hash"
ENVELOPE_KEYS = {
    "event_type",
    "document_id",
    "tenant_id",
    "document_type",
    "timestamp",
    "ctes",
    "warnings",
    "risk_assessment",
}
BOL_NO_DATE = """
BILL OF LADING
Shipper: Fresh Farms Inc.
GLN: 1234567890123
Ship To: Metro Distribution Center
ITEM DETAILS:
Product: Romaine Lettuce Hearts 12ct
Lot: L-2025-1105-A
Quantity: 50 cases
GTIN: 00012345678901
"""


class RecordingProducer:
    def __init__(self):
        self.messages = []

    def send(self, topic, *, key, value, headers):
        self.messages.append((topic, key, json.loads(json.dumps(value)), list(headers)))

    def flush(self, timeout):
        pass


class RecordingTracker:
    def __init__(self):
        self.records = []

    def record_hallucination(self, **kwargs):
        self.records.append(deepcopy(kwargs))
        return kwargs


@pytest.fixture
def components(monkeypatch):
    import services

    prior_modules = {
        name: module
        for name, module in sys.modules.items()
        if name == "services.admin" or name.startswith("services.admin.")
    }
    prior_packages = {
        name: (module, dict(vars(module)))
        for name, module in {"services": services, **prior_modules}.items()
        if hasattr(module, "__path__")
    }
    try:
        with monkeypatch.context() as scoped:
            # Admin imports construct an engine; no external DB is needed.
            scoped.setenv("ADMIN_DATABASE_URL", "sqlite:///:memory:")
            scoped.setenv("DATABASE_URL", "sqlite:///:memory:")
            from services.admin.app import review_consumer
            from services.nlp.app import consumer

            # Real strict signing/verification with synthetic scoped keys.
            scoped.setenv("ENVIRONMENT", "production")
            scoped.setenv("KAFKA_SIGNING_KEY_NLP", "offline-fsma-contract-nlp-key")
            scoped.setenv("KAFKA_SIGNING_KEY_SCHEDULER", "offline-fsma-contract-scheduler-key")
            scoped.setenv("KAFKA_ALLOWED_PRODUCERS_NLP_NEEDS_REVIEW", "nlp-service")
            scoped.setenv("KAFKA_MAX_SIGNATURE_AGE_SECONDS", "900")
            yield consumer, review_consumer
    finally:
        # Remove only admin imports this fixture introduced, including bindings
        # on pre-existing parent packages. Never replace a prior engine/session.
        admin_names = {name for name in sys.modules if name == "services.admin" or name.startswith("services.admin.")}
        database = sys.modules.get("services.admin.app.database")
        if "services.admin.app.database" not in prior_modules and database is not None:
            database._engine.dispose()
        for name in admin_names - prior_modules.keys():
            sys.modules.pop(name)
        sys.modules.update(prior_modules)
        for name in admin_names | prior_modules.keys():
            parent_name, _, child = name.rpartition(".")
            if parent_name in prior_packages:
                parent, attributes = prior_packages[parent_name]
                if child in attributes:
                    setattr(parent, child, attributes[child])
                else:
                    vars(parent).pop(child, None)


def _publish(consumer, monkeypatch, extractor):
    monkeypatch.setattr(consumer, "_get_fsma_extractor", lambda: extractor)
    producer = RecordingProducer()
    summary = consumer._run_fsma_extractor(
        text=BOL_NO_DATE,
        doc_id=DOC_ID,
        doc_hash=DOC_HASH,
        producer=producer,
        tenant_id=TENANT_ID,
        kafka_headers=[("X-Request-ID", b"fsma-contract")],
    )
    assert len(producer.messages) == 1
    return summary, producer.messages[0]


def _record(review_consumer, message):
    topic, key, body, headers = message
    original = deepcopy(body)
    tracker = RecordingTracker()
    review_consumer._extract_and_record(body, tracker, headers=headers, topic=topic)
    assert len(tracker.records) == 1
    assert body == original
    return tracker.records[0]


def test_real_fsma_review_reaches_tracker_with_full_envelope(components, monkeypatch):
    consumer, review_consumer = components
    summary, message = _publish(consumer, monkeypatch, FSMAExtractor())
    topic, key, body, headers = message
    assert summary == {
        "status": "ok",
        "cte_count": 1,
        "review_required": True,
        "routed": "nlp.needs_review",
        "high_confidence": False,
    }
    assert topic == "nlp.needs_review"
    assert key == f"{TENANT_ID}:{DOC_ID}"
    assert ("X-Request-ID", b"fsma-contract") in headers
    assert body["ctes"][0]["kdes"]["traceability_lot_code"] == "L-2025-1105-A"
    assert body["ctes"][0]["missing_kdes"] == ["event_date"]

    recorded = _record(review_consumer, message)

    envelope = {name: body[name] for name in ENVELOPE_KEYS}
    assert recorded["extraction"] == {"attributes": {"extractor": "fsma_extractor", "fsma_envelope": envelope}}
    assert set(body) == ENVELOPE_KEYS | {
        "doc_hash",
        "extraction",
        "_producer_service",
        "_signed_at",
    }
    assert recorded["tenant_id"] == TENANT_ID
    assert recorded["document_id"] == DOC_ID
    assert recorded["doc_hash"] == DOC_HASH
    assert recorded["extractor"] == "fsma_extractor"
    # Preserve the current summary defaults and the text-based dedup input.
    assert recorded["confidence_score"] == 0.0
    assert recorded["text_raw"] == ""


def _result_and_envelope(ftl_covered, review_required=True):
    kde_values = {
        "traceability_lot_code": "ORIGINAL-TLC",
        "product_description": "Leafy greens",
        "quantity": 0.0,
        "unit_of_measure": "cases",
        "location_identifier": "0614141123452",
        "event_date": "2026-09-28",
        "event_time": "",
        "ship_from_location": "Farm",
        "ship_to_location": "Warehouse",
        "tlc_source_gln": "0614141123452",
        "tlc_source_fda_reg": None,
        "ship_from_gln": "0614141123452",
        "ship_to_gln": "0614141987652",
        "gtin": "00012345678901",
        "harvester_identifier": "HARVESTER-17",
        "field_identifier": "FIELD-8",
        "harvest_date": "2026-09-27",
        "cooling_location": "Cooler A",
        "cooling_temperature": "0 C",
        "packing_location": "Packing line 2",
        "harvest_location_ref": "Farm north field",
        "entry_point": "Dock 3",
        "source_vessel_name": "Vessel One",
        "prior_source_tlc": None,
        "is_ftl_covered": ftl_covered,
        "ftl_category": "",
    }
    assert set(kde_values) == {field.name for field in fields(KDE)}
    ctes, expected_ctes = [], []
    for event_type, event_id, prior_tlc in [
        (CTEType.SHIPPING, "shipping-id", None),
        (CTEType.RECEIVING, "receiving-id", "ORIGINAL-TLC"),
    ]:
        values = {**kde_values, "prior_source_tlc": prior_tlc}
        ctes.append(
            CTE(
                type=event_type,
                kdes=KDE(**values),
                confidence=0.0,
                source_text="Original evidence\n0 cases",
                bounding_box={"x": 0.0},
                event_id=event_id,
            )
        )
        expected = {
            "type": event_type.value,
            "event_id": event_id,
            "kdes": values,
            "confidence": 0.0,
            "source_text": "Original evidence\n0 cases",
            "bounding_box": {"x": 0.0},
        }
        if review_required:
            expected["missing_kdes"] = []
        expected_ctes.append(expected)
    result = FSMAExtractionResult(
        document_id=DOC_ID,
        tenant_id=TENANT_ID,
        document_type=DocumentType.BILL_OF_LADING,
        ctes=ctes,
        extraction_timestamp="2026-09-28T12:00:00Z",
        raw_text="Do not promote this document text into the dedup key",
        warnings=["Original warning"],
        confidence_level=ExtractionConfidence.LOW,
        review_required=review_required,
    )
    return result, {
        "event_type": "fsma.extraction",
        "document_id": DOC_ID,
        "tenant_id": TENANT_ID,
        "document_type": "BOL",
        "timestamp": "2026-09-28T12:00:00Z",
        "ctes": expected_ctes,
        "warnings": ["Original warning"],
        "risk_assessment": {"level": "LOW", "review_required": review_required},
    }


@pytest.mark.parametrize("ftl_covered", [True, False, None])
def test_review_boundary_retains_typed_kdes_and_evidence(components, monkeypatch, ftl_covered):
    consumer, review_consumer = components
    result, expected = _result_and_envelope(ftl_covered)
    original = deepcopy(result)
    extractor = FSMAExtractor()
    # Substitute extraction input only; routing, serialization and auth stay real.
    monkeypatch.setattr(extractor, "extract", lambda *args, **kwargs: result)
    _, message = _publish(consumer, monkeypatch, extractor)

    recorded = _record(review_consumer, message)

    assert {name: message[2][name] for name in ENVELOPE_KEYS} == expected
    assert recorded["extraction"]["attributes"]["fsma_envelope"] == expected
    kdes = recorded["extraction"]["attributes"]["fsma_envelope"]["ctes"][0]["kdes"]
    assert kdes["is_ftl_covered"] is ftl_covered
    assert type(kdes["quantity"]) is float
    assert recorded["text_raw"] == ""
    assert recorded["confidence_score"] == 0.0
    assert "source_text" not in recorded["extraction"]
    assert "confidence_score" not in recorded["extraction"]
    assert result == original


def test_graph_message_keeps_existing_wire_shape(components, monkeypatch):
    from shared.kafka_auth import verify_event

    consumer, _ = components
    result, expected = _result_and_envelope(False, review_required=False)
    extractor = FSMAExtractor()
    monkeypatch.setattr(extractor, "extract", lambda *args, **kwargs: result)
    summary, message = _publish(consumer, monkeypatch, extractor)
    topic, key, body, headers = message

    verified, producer = verify_event(
        body,
        headers,
        topic=topic,
        allowed_producers={"nlp-service"},
        strict=True,
    )

    assert topic == "graph.update"
    assert key == f"{TENANT_ID}:{DOC_ID}"
    assert producer == "nlp-service"
    assert summary["high_confidence"] is True
    assert summary["review_required"] is False
    assert {k: v for k, v in verified.items() if k not in {"_producer_service", "_signed_at"}} == {
        **expected,
        "doc_hash": DOC_HASH,
    }


@pytest.mark.parametrize(
    ("fault", "reason"),
    [
        ("tenant", "signature_mismatch"),
        ("nested_evidence", "signature_mismatch"),
        ("wrong_producer", "producer_not_allowed_for_topic"),
        ("missing_auth", "missing_sig_version_header"),
        ("expired", "signed_at_stale"),
    ],
)
def test_review_boundary_rejects_invalid_auth_before_recording(components, monkeypatch, fault, reason):
    from shared.kafka_auth import KafkaAuthError, sign_event

    consumer, review_consumer = components
    _, (topic, _, body, headers) = _publish(consumer, monkeypatch, FSMAExtractor())
    if fault == "tenant":
        body["tenant_id"] = "22222222-2222-2222-2222-222222222222"
    elif fault == "nested_evidence":
        body["extraction"] = {"attributes": {"fsma_envelope": {"ctes": []}}}
    elif fault == "wrong_producer":
        body, headers = sign_event(body, producer_service="scheduler-service")
    elif fault == "missing_auth":
        headers = []
    else:
        body, headers = sign_event(
            body,
            producer_service="nlp-service",
            now_fn=lambda: datetime(2000, 1, 1, tzinfo=timezone.utc),
        )
    tracker = RecordingTracker()

    with pytest.raises(KafkaAuthError) as excinfo:
        review_consumer._extract_and_record(body, tracker, headers=headers, topic=topic)

    assert excinfo.value.reason == reason
    assert tracker.records == []


def test_generic_review_projection_and_sanitization_are_unchanged(components):
    from shared.kafka_auth import sign_event

    _, review_consumer = components
    payload = {
        "tenant_id": TENANT_ID,
        "document_id": DOC_ID,
        "doc_hash": DOC_HASH,
        "extraction": {
            "confidence_score": 0.42,
            "source_text": "<b>Cold</b> & fresh",
            "attributes": {"extractor": "GENERIC"},
        },
    }
    body, headers = sign_event(payload, producer_service="nlp-service")

    recorded = _record(review_consumer, ("nlp.needs_review", b"generic", body, headers))

    assert recorded == {
        "tenant_id": TENANT_ID,
        "document_id": DOC_ID,
        "doc_hash": DOC_HASH,
        "extractor": "GENERIC",
        "confidence_score": 0.42,
        "text_raw": "Cold &amp; fresh",
        "provenance": {"extractor": "GENERIC"},
        "extraction": {
            "confidence_score": 0.42,
            "source_text": "Cold &amp; fresh",
            "attributes": {"extractor": "GENERIC"},
        },
    }
