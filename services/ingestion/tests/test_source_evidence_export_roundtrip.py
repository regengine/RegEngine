"""Real PostgreSQL source/canonical/provenance/CSV boundary tests.

Evidence here means the persisted raw supplier record and normalization
provenance. There is no attachment-ingestion writer in this repository; this
does not claim S3 upload, HTTP auth, rule evaluation, billing, Redis, or Neo4j
coverage. The shared fixture is a targeted Alembic subset, not upgrade-head.
"""

from __future__ import annotations

import csv
import io
import json
from uuid import uuid4

import pytest
from sqlalchemy import text

from services.ingestion.tests.test_cte_persistence_e2e import db_session, postgres_engine  # noqa: F401

pytestmark = pytest.mark.integration


@pytest.fixture
def source_record():
    return {
        "cte_type": "shipping",
        "traceability_lot_code": "ROUNDTRIP-LOT-001",
        "product_description": "Fresh basil, premium",
        "quantity": 12.5,
        "unit_of_measure": "cases",
        "location_gln": "0614141000005",
        "location_name": "Source Farm",
        "timestamp": "2026-03-01T00:00:00Z",
        "kdes": {
            "ship_date": "2026-03-01",
            "ship_from_gln": "0614141000005",
            "ship_from_location": "Source Farm",
            "ship_to_gln": "0614141000012",
            "ship_to_location": "Destination DC",
            "reference_document_number": "BOL-0007",
            "temperature": 0,
            "sealed": False,
            "sample_sizes": [0, 2, 5],
            "inspection": {"passed": True, "note": 'cold, "sealed"'},
        },
    }


@pytest.fixture
def persisted_source(db_session, source_record, monkeypatch):
    from app.webhook_models import IngestEvent
    from shared.canonical_event import normalize_webhook_event
    from shared.canonical_persistence import CanonicalEventStore

    # Disable external graph transport explicitly; all persistence/query code
    # below is real. The supported metering opt-out avoids billing dependencies.
    monkeypatch.setenv("ENABLE_NEO4J_SYNC", "false")
    tenant_id = str(uuid4())
    event = normalize_webhook_event(
        IngestEvent.model_validate(source_record),
        tenant_id,
        source="supplier-webhook",
        raw_payload=source_record,
    )
    store = CanonicalEventStore(db_session, dual_write=True, meter_usage=False)
    result = store.persist_event(event)
    db_session.commit()
    assert result.success and not result.idempotent
    assert result.legacy_event_id == result.event_id
    return tenant_id, event, result, store


def test_source_canonical_and_provenance_survive_real_persistence(db_session, source_record, persisted_source):
    tenant_id, event, result, store = persisted_source
    saved = store.get_event(tenant_id, result.event_id, include_raw_payload=True)

    assert saved["raw_payload"] == source_record
    assert saved["normalized_payload"] == {
        "event_id": result.event_id,
        "event_type": "shipping",
        "traceability_lot_code": "ROUNDTRIP-LOT-001",
        "product_reference": "Fresh basil, premium",
        "lot_reference": "ROUNDTRIP-LOT-001",
        "quantity": 12.5,
        "unit_of_measure": "cases",
        "event_timestamp": "2026-03-01T00:00:00+00:00",
        "event_timezone": "UTC",
        "from_entity_reference": None,
        "to_entity_reference": None,
        "from_facility_reference": "0614141000005",
        "to_facility_reference": "0614141000012",
        "transport_reference": None,
        "kdes": {
            **source_record["kdes"],
            "ingest_source": "supplier-webhook",
            "ftl_covered": True,
            "ftl_category": "Herbs",
        },
        "schema_version": 1,
    }
    provenance = saved["provenance_metadata"]
    assert provenance["mapper_name"] == "webhook_v2_normalizer"
    assert provenance["mapper_version"] == "1.0.0"
    assert provenance["original_format"] == "json"
    assert provenance["normalization_rules_applied"] == [
        "webhook_kde_extraction",
        "facility_reference_mapping",
    ]
    assert saved["sha256_hash"] == result.sha256_hash
    assert saved["chain_hash"] == result.chain_hash
    assert store.verify_chain_canonical(tenant_id).valid

    # Raw supplier evidence is opt-in, and an explicit foreign-tenant lookup
    # returns nothing. This checks query predicates, not runtime-role RLS.
    assert "raw_payload" not in store.get_event(tenant_id, result.event_id)
    assert store.get_event(str(uuid4()), result.event_id, include_raw_payload=True) is None
    replay = store.persist_event(event)
    db_session.commit()
    assert replay.idempotent and replay.event_id == result.event_id
    assert store.verify_chain_canonical(tenant_id).chain_length == 1


def test_source_fields_and_json_types_survive_fda_csv(db_session, persisted_source):
    from app.fda_export_service import _generate_csv
    from shared.cte_persistence import CTEPersistence

    tenant_id, _, result, _ = persisted_source
    events = CTEPersistence(db_session).query_events_by_tlc(tenant_id, "ROUNDTRIP-LOT-001")
    assert len(events) == 1
    assert events[0]["id"] == result.event_id
    row = next(csv.DictReader(io.StringIO(_generate_csv(events, include_pii=True))))

    expected = {
        "Traceability Lot Code (TLC)": "ROUNDTRIP-LOT-001",
        "Product Description": "Fresh basil, premium",
        "Quantity": "12.5",
        "Unit of Measure": "cases",
        "Event Type (CTE)": "shipping",
        "Event Date": "2026-03-01",
        "Event Time": "00:00:00 UTC",
        "Location GLN": "0614141000005",
        "Location Name": "Source Farm",
        "Ship From GLN": "0614141000005",
        "Ship From Name": "Source Farm",
        "Ship To GLN": "0614141000012",
        "Ship To Name": "Destination DC",
        "Ship Date": "2026-03-01",
        "Reference Document Number": "BOL-0007",
        "Temperature (°F)": "0",
        "Record Hash (SHA-256)": result.sha256_hash,
        "Chain Hash": result.chain_hash,
    }
    assert {key: row[key] for key in expected} == expected
    assert json.loads(row["Additional KDEs (JSON)"]) == {
        "sealed": False,
        "sample_sizes": [0, 2, 5],
        "inspection": {"passed": True, "note": 'cold, "sealed"'},
        "ingest_source": "supplier-webhook",
        "ftl_covered": True,
        "ftl_category": "Herbs",
    }


@pytest.mark.parametrize("session_timezone", ["America/Los_Angeles", "Asia/Tokyo"])
def test_fda_csv_uses_utc_event_date_across_database_timezones(db_session, persisted_source, session_timezone):
    from app.fda_export_service import _generate_csv
    from shared.cte_persistence import CTEPersistence

    tenant_id, _, _, _ = persisted_source
    db_session.execute(text("SELECT set_config('TimeZone', :zone, true)"), {"zone": session_timezone})
    events = CTEPersistence(db_session).query_events_by_tlc(tenant_id, "ROUNDTRIP-LOT-001")
    row = next(csv.DictReader(io.StringIO(_generate_csv(events, include_pii=True))))

    # The source was exactly midnight UTC. A database/session timezone must
    # not silently change the FDA event date or time to a different contract.
    assert row["Event Date"] == "2026-03-01"
    assert row["Event Time"] == "00:00:00 UTC"


def test_export_verification_rejects_drift_in_exported_legacy_facts(db_session, persisted_source):
    from app.fda_export.queries import _verify_chain_for_export
    from app.fda_export_service import _generate_csv
    from shared.cte_persistence import CTEPersistence

    tenant_id, _, result, store = persisted_source
    db_session.execute(text("SET LOCAL fsma.allow_mutation = 'true'"))
    db_session.execute(
        text("UPDATE fsma.cte_events SET product_description = 'ALTERED EXPORT' WHERE id = :id"),
        {"id": result.event_id},
    )
    db_session.commit()

    persistence = CTEPersistence(db_session)
    exported = persistence.query_events_by_tlc(tenant_id, "ROUNDTRIP-LOT-001")
    row = next(csv.DictReader(io.StringIO(_generate_csv(exported, include_pii=True))))
    assert row["Product Description"] == "ALTERED EXPORT"
    assert store.get_event(tenant_id, result.event_id)["product_reference"] == "Fresh basil, premium"
    assert store.verify_chain_canonical(tenant_id).valid
    # The export reads legacy rows. Verification must cover those same facts,
    # not a separate unchanged canonical copy with an identical stored hash.
    assert not _verify_chain_for_export(persistence, db_session, tenant_id, source="legacy").valid


@pytest.mark.parametrize("canonical_verifier", ["1", "0"])
def test_canonical_export_verification_requires_content_verifier(
    db_session, persisted_source, monkeypatch, canonical_verifier
):
    from app.fda_export.queries import _verify_chain_for_export
    from shared.cte_persistence import CTEPersistence

    tenant_id, _, _, _ = persisted_source
    monkeypatch.setenv("CHAIN_VERIFY_READ_CANONICAL", canonical_verifier)
    verification = _verify_chain_for_export(CTEPersistence(db_session), db_session, tenant_id, source="canonical")
    assert verification.valid is (canonical_verifier == "1")


def test_epcis_date_filter_keeps_first_utc_instant_under_non_utc_session(db_session, persisted_source, monkeypatch):
    from app import epcis_export

    tenant_id, _, _, _ = persisted_source
    db_session.execute(text("SET LOCAL TIME ZONE 'America/Los_Angeles'"))
    monkeypatch.setattr(epcis_export, "get_db_safe", lambda: db_session)
    events = epcis_export._query_tenant_events(tenant_id, "ROUNDTRIP-LOT-001", "2026-03-01", "2026-03-01")

    assert len(events) == 1
    assert events[0]["product_description"] == "Fresh basil, premium"
    assert events[0]["quantity"] == 12.5


def _read_fda_events(db_session, tenant_id, reader, *, start_date=None, end_date=None, location=None):
    from app.fda_export import queries

    if reader == "v2":
        where, params = queries.build_v2_where_clause(tenant_id, "ROUNDTRIP-LOT-001", None, start_date, end_date)
        return queries.v2_rows_to_event_dicts(queries.fetch_v2_events(db_session, where, params))
    builder, fetcher = (
        (queries.build_recall_where_clause, queries.fetch_recall_events)
        if reader == "legacy"
        else (queries.build_recall_where_clause_canonical, queries.fetch_recall_events_canonical)
    )
    where, params = builder(tenant_id, None, location, "ROUNDTRIP-LOT-001", None, start_date, end_date)
    return queries.rows_to_event_dicts(fetcher(db_session, where, params))


@pytest.mark.parametrize("reader", ["legacy", "canonical", "v2"])
def test_fda_query_date_filter_keeps_midnight_utc_under_non_utc_session(db_session, persisted_source, reader):
    tenant_id, _, _, _ = persisted_source
    db_session.execute(text("SET LOCAL TIME ZONE 'America/Los_Angeles'"))
    events = _read_fda_events(db_session, tenant_id, reader, start_date="2026-03-01", end_date="2026-03-01")

    assert len(events) == 1
    assert events[0]["product_description"] == "Fresh basil, premium"


@pytest.mark.parametrize("reader", ["legacy", "canonical", "v2"])
def test_fda_readers_preserve_distinct_source_location_name_and_gln(db_session, persisted_source, reader):
    tenant_id, _, _, _ = persisted_source
    events = _read_fda_events(db_session, tenant_id, reader)

    assert len(events) == 1
    assert events[0]["location_gln"] == "0614141000005"
    assert events[0]["location_name"] == "Source Farm"


@pytest.mark.parametrize("reader", ["legacy", "canonical"])
def test_fda_recall_filters_use_preserved_source_name(db_session, persisted_source, reader):
    tenant_id, _, _, _ = persisted_source
    events = _read_fda_events(db_session, tenant_id, reader, location="Source Farm")

    assert len(events) == 1
    assert events[0]["location_name"] == "Source Farm"


@pytest.mark.parametrize("reader", ["tlc", "tlcs", "all"])
def test_cte_query_date_filter_keeps_midnight_utc_under_non_utc_session(db_session, persisted_source, reader):
    from shared.cte_persistence import CTEPersistence

    tenant_id, _, _, _ = persisted_source
    db_session.execute(text("SET LOCAL TIME ZONE 'America/Los_Angeles'"))
    persistence = CTEPersistence(db_session)
    bounds = {"start_date": "2026-03-01", "end_date": "2026-03-01"}
    if reader == "tlc":
        events = persistence.query_events_by_tlc(tenant_id, "ROUNDTRIP-LOT-001", **bounds)
    elif reader == "tlcs":
        events = persistence.query_events_by_tlcs(tenant_id, ["ROUNDTRIP-LOT-001"], **bounds)
    else:
        events, total = persistence.query_all_events(tenant_id, **bounds)
        assert total == 1

    assert len(events) == 1
    assert events[0]["product_description"] == "Fresh basil, premium"


@pytest.mark.parametrize(
    ("reference", "raw_location", "expected_gln", "expected_name"),
    [
        ("Source Farm", {}, None, "Source Farm"),
        ("0614141000005.0", {}, "0614141000005.0", "0614141000005.0"),
        (
            "urn:epc:id:sgln:0614141.00001.0",
            {},
            "urn:epc:id:sgln:0614141.00001.0",
            "urn:epc:id:sgln:0614141.00001.0",
        ),
        (
            "https://id.gs1.org/414/0614141000005",
            {},
            "https://id.gs1.org/414/0614141000005",
            "https://id.gs1.org/414/0614141000005",
        ),
        (
            "0614141000005",
            {"location_name": "  Source Farm  ", "location_gln": "0614141000098"},
            "0614141000098",
            "  Source Farm  ",
        ),
    ],
)
def test_real_sql_location_projection_matches_persisted_source_facts(
    db_session, monkeypatch, reference, raw_location, expected_gln, expected_name
):
    from shared.canonical_event import TraceabilityEvent
    from shared.canonical_persistence import CanonicalEventStore

    monkeypatch.setenv("ENABLE_NEO4J_SYNC", "false")
    tenant_id = str(uuid4())
    canonical = TraceabilityEvent(
        tenant_id=tenant_id,
        source_system="epcis_api",
        event_type="shipping",
        event_timestamp="2026-03-01T00:00:00Z",
        traceability_lot_code="ROUNDTRIP-LOT-001",
        product_reference="Fresh basil",
        quantity=1,
        unit_of_measure="cases",
        to_facility_reference=reference,
        raw_payload=raw_location,
    )
    CanonicalEventStore(db_session, dual_write=True, meter_usage=False).persist_event(canonical)
    db_session.commit()

    for reader in ("legacy", "canonical", "v2"):
        events = _read_fda_events(db_session, tenant_id, reader)
        assert len(events) == 1
        assert events[0]["location_gln"] == expected_gln
        assert events[0]["location_name"] == expected_name
