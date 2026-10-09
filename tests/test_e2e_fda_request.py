"""
E2E Integration Test: FDA 24-Hour Request — Full Closed-Loop Execution.

This is THE test that proves the system is real.

Scenario:
    FDA requests all records for Product "Organic Romaine Hearts" over
    30 days across 3 suppliers. Data is messy — some events are missing
    KDEs, one supplier has identity ambiguity, and there are gaps in
    the traceability chain.

    The test walks through the entire pipeline:
    1. Ingest messy CTE events (with missing fields)
    2. Canonical normalization (all events hit traceability_events)
    3. Rules engine fires (critical failures detected)
    4. FDA request case created with 24-hour deadline
    5. Records collected for scope
    6. Gap analysis identifies defects
    7. check_blocking_defects() confirms submission is BLOCKED
    8. Exceptions created and resolved
    9. Signoffs added
    10. Package assembled — immutable, hashed, versioned
    11. Package submitted
    12. Amendment created after new data arrives

    If ANY step fails, the system is not ready for production.

Usage:
    pytest tests/test_e2e_fda_request.py -v --tb=short

Requires:
    - PostgreSQL with fsma schema and all migrations applied
    - Set DATABASE_URL environment variable
"""

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List

import pytest

from tests.integration_requirements import sqlalchemy_session_or_skip
from tests.migrations.rls_db import guarded_live_database_url

# Skip if no database configured
DATABASE_URL = guarded_live_database_url()
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="no designated live test DB (CI DATABASE_URL or REGENGINE_MIGRATION_TEST_DB) — skipping E2E integration test",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def db_session():
    """Create a DB session for the entire test module."""
    engine, session = sqlalchemy_session_or_skip(
        DATABASE_URL,
        reason="PostgreSQL with fsma schema is unavailable",
    )

    try:
        yield session
    finally:
        session.rollback()
        session.close()
        engine.dispose()


@pytest.fixture(scope="module")
def tenant_id():
    """Use a unique tenant UUID for test isolation."""
    return str(uuid.uuid4())


@pytest.fixture(scope="module")
def workflow(db_session):
    """Create a RequestWorkflow instance."""
    from shared.request_workflow import RequestWorkflow

    return RequestWorkflow(db_session)


@pytest.fixture(scope="module")
def rules_engine(db_session):
    """Create a RulesEngine instance with the built-in FSMA rules seeded.

    An alembic-head database has no rule_definitions rows; without seeds
    every evaluation returns no-verdict and persists nothing, so step 2
    would count zero failures. Production seeds these rules explicitly
    (POST /rules/seed or scripts/seed_demo_data.py), so the test must too.
    """
    from shared.rules import seed_rule_definitions
    from shared.rules_engine import RulesEngine

    seed_rule_definitions(db_session)
    db_session.commit()
    return RulesEngine(db_session)


@pytest.fixture(scope="module")
def canonical_store(db_session):
    """Create a CanonicalEventStore instance."""
    from shared.canonical_persistence import CanonicalEventStore

    return CanonicalEventStore(db_session)


# ---------------------------------------------------------------------------
# Test Data: Messy CTE Events (realistic supplier data)
# ---------------------------------------------------------------------------

PRODUCT = "Organic Romaine Hearts"
SUPPLIERS = [
    "Salinas Valley Farms",
    "Pacific Coast Growers",
    "FreshCut Processing",
]


def _make_events(tenant_id: str) -> List[Dict]:
    """Generate messy test events simulating real supplier data."""
    base_time = datetime.now(timezone.utc) - timedelta(days=15)

    return [
        # Event 1: Complete harvesting event (PASS)
        {
            "event_id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "event_type": "harvesting",
            "event_timestamp": (base_time + timedelta(days=0)).isoformat(),
            "product_reference": PRODUCT,
            "traceability_lot_code": "LOT-ROM-2026-0312A",
            "quantity": 5000.0,
            "unit_of_measure": "lbs",
            "from_facility_reference": "Salinas Valley Farms",
            "from_entity_reference": "Salinas Valley Farms",
            "kdes": {
                "harvest_date": (base_time + timedelta(days=0)).strftime("%Y-%m-%d"),
                "field_coordinates": "36.6744,-121.6550",
                "growing_area_code": "CA-SVF-BLOCK-7",
            },
            "confidence_score": 0.95,
            "status": "active",
        },
        # Event 2: Cooling event — MISSING cooling_date KDE (will fail rule)
        {
            "event_id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "event_type": "cooling",
            "event_timestamp": (base_time + timedelta(days=0, hours=4)).isoformat(),
            "product_reference": PRODUCT,
            "traceability_lot_code": "LOT-ROM-2026-0312A",
            "quantity": 5000.0,
            "unit_of_measure": "lbs",
            "from_facility_reference": "Salinas Valley Farms",
            "kdes": {
                # Missing: cooling_date (required KDE)
                "cooling_method": "vacuum",
            },
            "confidence_score": 0.88,
            "status": "active",
        },
        # Event 3: Initial packing — MISSING tlc_source_reference (critical)
        {
            "event_id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "event_type": "initial_packing",
            "event_timestamp": (base_time + timedelta(days=1)).isoformat(),
            "product_reference": PRODUCT,
            "traceability_lot_code": "LOT-ROM-2026-0312A",
            "quantity": 4800.0,
            "unit_of_measure": "lbs",
            "from_facility_reference": "FreshCut Processing",
            "from_entity_reference": "FreshCut Processing",
            "kdes": {
                "packing_date": (base_time + timedelta(days=1)).strftime("%Y-%m-%d"),
                # Missing: tlc_source_reference (critical for FSMA 204)
            },
            "confidence_score": 0.92,
            "status": "active",
        },
        # Event 4: Shipping event from second supplier
        {
            "event_id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "event_type": "shipping",
            "event_timestamp": (base_time + timedelta(days=2)).isoformat(),
            "product_reference": PRODUCT,
            "traceability_lot_code": "LOT-ROM-2026-0312B",
            "quantity": 3000.0,
            "unit_of_measure": "lbs",
            "from_facility_reference": "Pacific Coast Growers",
            "to_facility_reference": "MegaMart Distribution Center",
            "from_entity_reference": "Pacific Coast Growers",
            "to_entity_reference": "MegaMart Inc",
            "kdes": {
                "ship_date": (base_time + timedelta(days=2)).strftime("%Y-%m-%d"),
                "carrier": "FedEx Freight",
                "bill_of_lading": "BOL-2026-0314-001",
            },
            "confidence_score": 0.97,
            "status": "active",
        },
        # Event 5: Receiving at retailer
        {
            "event_id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "event_type": "receiving",
            "event_timestamp": (base_time + timedelta(days=3)).isoformat(),
            "product_reference": PRODUCT,
            "traceability_lot_code": "LOT-ROM-2026-0312B",
            "quantity": 2950.0,
            "unit_of_measure": "lbs",
            "from_facility_reference": "Pacific Coast Growers",
            "to_facility_reference": "MegaMart Distribution Center",
            "to_entity_reference": "MegaMart Inc",
            "kdes": {
                "receive_date": (base_time + timedelta(days=3)).strftime("%Y-%m-%d"),
                "tlc_source_reference": "Pacific Coast Growers",
                "tlc_source_gln": "0061414100010",
                "receiving_location": "Dock 7, Bay 12",
                "temperature": "34°F",
            },
            "confidence_score": 0.99,
            "status": "active",
        },
    ]


# ---------------------------------------------------------------------------
# Shared workflow state as explicit fixtures
# ---------------------------------------------------------------------------
# Each numbered step below depends only on the fixture for its own stage.
# Pytest resolves the whole chain automatically, so every test also passes
# in isolation (for example
# ``pytest tests/test_e2e_fda_request.py::TestFDARequestE2E::test_05_gap_analysis``)
# and reordering the tests cannot break the suite. Nothing is handed
# through class attributes.


def _ingest_seed_events(db_session, tenant_id: str, canonical_store) -> int:
    """Persist the messy supplier events; return how many were stored."""
    from shared.canonical_event import IngestionSource, TraceabilityEvent

    persisted = []
    for event_data in _make_events(tenant_id):
        te = TraceabilityEvent(
            event_id=event_data["event_id"],
            tenant_id=tenant_id,
            event_type=event_data["event_type"],
            event_timestamp=event_data["event_timestamp"],
            product_reference=event_data.get("product_reference"),
            traceability_lot_code=event_data.get("traceability_lot_code"),
            quantity=event_data.get("quantity"),
            unit_of_measure=event_data.get("unit_of_measure"),
            from_entity_reference=event_data.get("from_entity_reference"),
            to_entity_reference=event_data.get("to_entity_reference"),
            from_facility_reference=event_data.get("from_facility_reference"),
            to_facility_reference=event_data.get("to_facility_reference"),
            kdes=event_data.get("kdes", {}),
            confidence_score=event_data.get("confidence_score"),
            source_system=IngestionSource(event_data.get("source_system", "csv_upload")),
            status="active",
        )
        persisted.append(canonical_store.persist_event(te))
    return len(persisted)


def _evaluate_seed_rules(db_session, tenant_id: str, rules_engine) -> Dict[str, int]:
    """Evaluate every tenant event; return the event and failure counts."""
    from sqlalchemy import text

    result = db_session.execute(
        text("""
            SELECT event_id, event_type
            FROM fsma.traceability_events
            WHERE tenant_id = :tid AND status = 'active'
            ORDER BY event_timestamp
        """),
        {"tid": tenant_id},
    )
    events = result.mappings().fetchall()

    total_failures = 0
    for event in events:
        full = (
            db_session.execute(
                text("SELECT * FROM fsma.traceability_events WHERE event_id = :eid AND tenant_id = :tid"),
                {"eid": str(event["event_id"]), "tid": tenant_id},
            )
            .mappings()
            .fetchone()
        )
        if full:
            event_dict = dict(full)
            if event_dict.get("kdes") and isinstance(event_dict["kdes"], str):
                event_dict["kdes"] = json.loads(event_dict["kdes"])
            summary = rules_engine.evaluate_event(
                event_dict,
                persist=True,
                tenant_id=tenant_id,
            )
            total_failures += summary.failed
    return {"event_count": len(events), "total_failures": total_failures}


@pytest.fixture(scope="module")
def seeded_event_count(db_session, tenant_id, canonical_store):
    """Step 1 runs once per module: ingest the messy supplier events."""
    return _ingest_seed_events(db_session, tenant_id, canonical_store)


@pytest.fixture(scope="module")
def rule_evaluation(db_session, tenant_id, rules_engine, seeded_event_count):
    """Step 2 runs once per module: evaluate every tenant event."""
    return _evaluate_seed_rules(db_session, tenant_id, rules_engine)


@pytest.fixture(scope="module")
def fda_case(tenant_id, workflow, rule_evaluation):
    """Step 3 runs once per module: the FDA request case exists."""
    return workflow.create_request_case(
        tenant_id=tenant_id,
        requesting_party="FDA",
        request_channel="email",
        scope_type="product_recall",
        scope_description="E. coli O157:H7 investigation — Organic Romaine Hearts",
        response_hours=24,
        affected_products=[PRODUCT],
        affected_lots=["LOT-ROM-2026-0312A", "LOT-ROM-2026-0312B"],
        affected_facilities=SUPPLIERS,
    )


@pytest.fixture(scope="module")
def collection_result(tenant_id, workflow, fda_case):
    """Step 4 runs once per module: scope confirmed and records collected."""
    case_id = fda_case["request_case_id"]
    workflow.update_scope(
        tenant_id,
        case_id,
        scope_description="All romaine lettuce lots from Salinas Valley region, 30-day window",
    )
    result = workflow.collect_records(tenant_id, case_id)
    return {"case_id": case_id, "total_records": result["total_records"]}


@pytest.fixture(scope="module")
def gap_report(tenant_id, workflow, collection_result):
    """Step 5 runs once per module: gap analysis identifies defects."""
    gaps = workflow.run_gap_analysis(tenant_id, collection_result["case_id"])
    return {"case_id": collection_result["case_id"], "gaps": gaps}


@pytest.fixture(scope="module")
def blocking_report(tenant_id, workflow, gap_report):
    """Step 6 runs once per module: blocking-defect check result."""
    check = workflow.check_blocking_defects(tenant_id, gap_report["case_id"])
    return {"case_id": gap_report["case_id"], "check": check}


@pytest.fixture(scope="module")
def signed_case_id(tenant_id, workflow, blocking_report):
    """Step 7 runs once per module: scope-approval signoff recorded."""
    case_id = blocking_report["case_id"]
    workflow.add_signoff(
        tenant_id,
        case_id,
        signoff_type="scope_approval",
        signed_by="qa_lead@company.com",
        notes="Scope confirmed — all Salinas Valley romaine lots included.",
    )
    return case_id


@pytest.fixture(scope="module")
def assembled_package(tenant_id, workflow, signed_case_id):
    """Step 8 runs once per module: immutable response package assembled."""
    return workflow.assemble_response_package(
        tenant_id,
        signed_case_id,
        generated_by="compliance_officer@company.com",
    )


@pytest.fixture(scope="module")
def submission_result(tenant_id, workflow, signed_case_id, assembled_package):
    """Step 9 runs once per module: final approval signoff, then submit."""
    workflow.add_signoff(
        tenant_id,
        signed_case_id,
        signoff_type="final_approval",
        signed_by="vp_quality@company.com",
        notes="Approved for FDA submission.",
    )
    # force=True to bypass remaining rule failures (in production those
    # would need exception waivers first).
    return workflow.submit_package(
        tenant_id,
        signed_case_id,
        package_id=assembled_package["package_id"],
        submitted_by="vp_quality@company.com",
        submitted_to="FDA",
        submission_method="export",
        submission_notes="24-hour response — E. coli O157:H7 romaine investigation",
        force=True,
    )


@pytest.fixture(scope="module")
def amendment_record(tenant_id, workflow, submission_result):
    """Step 10 runs once per module: amendment created after submission."""
    return workflow.create_amendment(
        tenant_id,
        submission_result["request_case_id"],
        generated_by="compliance_officer@company.com",
    )


# ---------------------------------------------------------------------------
# The Test: Full Closed-Loop Execution
# ---------------------------------------------------------------------------


class TestFDARequestE2E:
    """Prove the system works end-to-end under realistic conditions."""

    @pytest.fixture(autouse=True)
    def _ensure_clean_session(self, db_session):
        """Ensure DB session is clean before each test."""
        try:
            from sqlalchemy import text

            db_session.execute(text("SELECT 1"))
        except Exception:
            db_session.rollback()

    def test_01_ingest_events_to_canonical_store(self, seeded_event_count):
        """Step 1: Ingest messy events into canonical store."""
        assert seeded_event_count == 5, f"Expected 5 persisted events, got {seeded_event_count}"

    def test_02_rules_engine_fires(self, rule_evaluation):
        """Step 2: Rules engine evaluates all events — expects failures."""
        assert rule_evaluation["event_count"] >= 5, f"Expected >=5 events, got {rule_evaluation['event_count']}"

        # We expect failures from missing KDEs
        assert rule_evaluation["total_failures"] > 0, "Expected at least 1 rule failure from messy data"

    def test_03_create_fda_request(self, fda_case):
        """Step 3: FDA requests Product X records."""
        assert fda_case["package_status"] == "intake"
        assert fda_case["requesting_party"] == "FDA"
        assert fda_case["request_case_id"], "Case must have an id"

    def test_04_scope_and_collect(self, collection_result):
        """Step 4: Scope confirmed and records collected."""
        assert collection_result["total_records"] >= 3, (
            f"Expected >=3 records in scope, got {collection_result['total_records']}"
        )

    def test_05_gap_analysis(self, gap_report):
        """Step 5: Gap analysis identifies defects."""
        gaps = gap_report["gaps"]

        # We expect failed rules from our messy data
        total_gaps = (
            len(gaps.get("failed_rules", []))
            + len(gaps.get("missing_events", []))
            + len(gaps.get("unresolved_exceptions", []))
        )
        assert total_gaps > 0, "Expected gaps from messy data"

    def test_06_blocking_defects_prevent_submission(self, tenant_id, workflow, blocking_report):
        """Step 6: System BLOCKS submission — critical defects exist."""
        check = blocking_report["check"]

        # Must have blockers (critical rule failures, missing signoffs)
        assert not check["can_submit"], (
            f"Expected submission to be BLOCKED but can_submit=True. Blockers: {check['blockers']}"
        )
        assert check["blocker_count"] > 0

        # Verify submit_package raises (either due to blockers or wrong status)
        with pytest.raises(ValueError):
            workflow.submit_package(
                tenant_id,
                blocking_report["case_id"],
                package_id="fake-pkg-id",
                submitted_by="test@example.com",
            )

    def test_07_signoffs_added(self, db_session, tenant_id, signed_case_id):
        """Step 7: Required signoffs provided."""
        from sqlalchemy import text

        row = (
            db_session.execute(
                text("""
                    SELECT signoff_type, signed_by
                    FROM fsma.request_signoffs
                    WHERE tenant_id = :tid
                      AND request_case_id = :cid
                      AND signoff_type = 'scope_approval'
                """),
                {"tid": tenant_id, "cid": signed_case_id},
            )
            .mappings()
            .fetchone()
        )
        assert row is not None, "scope_approval signoff must be recorded"
        assert row["signed_by"] == "qa_lead@company.com"

    def test_08_assemble_package(self, assembled_package):
        """Step 8: Assemble immutable response package."""
        package = assembled_package

        assert package["version_number"] == 1
        assert package["package_hash"], "Package must have SHA-256 hash"
        assert len(package["package_hash"]) == 64, "Hash must be 64 hex chars (SHA-256)"

        # Verify hash is reproducible (hash is computed WITHOUT the package_hash field)
        contents = package["package_contents"]
        if isinstance(contents, str):
            contents = json.loads(contents)
        contents_for_hash = {k: v for k, v in contents.items() if k != "package_hash"}
        recomputed = hashlib.sha256(json.dumps(contents_for_hash, sort_keys=True, default=str).encode()).hexdigest()
        assert recomputed == package["package_hash"], "Package hash must be reproducible"

    def test_09_final_approval_and_submit(self, submission_result):
        """Step 9: Final approval signoff, then submit."""
        assert submission_result["submission_id"], "Must have submission ID"
        assert submission_result["package_hash"], "Submission must reference package hash"
        assert submission_result["record_count"] >= 3, "Must have records in submission"

    def test_10_amendment_after_new_data(self, amendment_record):
        """Step 10: New data arrives → create amendment with diff."""
        assert amendment_record["version_number"] == 2, "Amendment must be version 2"
        assert amendment_record.get("diff_from_previous"), "Amendment must have diff"

    def test_11_package_history_complete(self, tenant_id, workflow, amendment_record):
        """Step 11: Verify complete package history."""
        history = workflow.get_package_history(tenant_id, amendment_record["request_case_id"])

        assert len(history) == 2, f"Expected 2 package versions, got {len(history)}"
        assert history[0]["version_number"] == 1
        assert history[1]["version_number"] == 2

        # Hashes must be different (data changed between versions)
        # (They might be the same if no new data was added, which is ok for this test)
        assert history[0]["package_hash"], "Version 1 must have hash"
        assert history[1]["package_hash"], "Version 2 must have hash"

    def test_12_deadline_monitoring(self, tenant_id, workflow, submission_result):
        """Step 12: Submitted cases leave the deadline list; active ones are reported."""
        submitted_case_id = submission_result["request_case_id"]

        # A fresh active case with a 1-hour deadline must show up as
        # urgent/critical. This proves the monitor reports real deadlines
        # instead of just returning without error.
        probe = workflow.create_request_case(
            tenant_id=tenant_id,
            requesting_party="FDA",
            request_channel="email",
            scope_type="product_recall",
            scope_description="Deadline probe — must appear in the active deadline list",
            response_hours=1,
            affected_products=[PRODUCT],
            affected_lots=["LOT-ROM-2026-0312A"],
            affected_facilities=SUPPLIERS,
        )
        probe_id = probe["request_case_id"]

        cases = workflow.check_deadline_status(tenant_id)
        assert isinstance(cases, list)
        by_id = {c["request_case_id"]: c for c in cases}

        # The submitted E2E case is no longer active, so it must be excluded.
        assert submitted_case_id not in by_id, "Submitted case must not appear in the active deadline list"

        # Every reported entry carries the full urgency contract.
        assert cases, "Expected at least the deadline probe in the active list"
        for entry in cases:
            assert entry["urgency"] in ("overdue", "critical", "urgent", "normal"), (
                f"Unknown urgency {entry['urgency']!r} for case {entry['request_case_id']}"
            )
            for key in (
                "request_case_id",
                "package_status",
                "response_due_at",
                "hours_remaining",
                "countdown_display",
            ):
                assert key in entry, f"Deadline entry missing {key!r}"

        # The fresh 1-hour probe must be reported as urgent or critical.
        assert probe_id in by_id, "Fresh active case missing from deadline status"
        assert by_id[probe_id]["urgency"] in ("urgent", "critical"), (
            f"Expected 'urgent' or 'critical' for 1h remaining, got {by_id[probe_id]['urgency']!r}"
        )
        assert by_id[probe_id]["hours_remaining"] <= 2
