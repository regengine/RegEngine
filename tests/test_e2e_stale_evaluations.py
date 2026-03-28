"""
E2E Integration Test: Stale Evaluation Detection.

Proves that the request workflow correctly blocks submission when
evaluations become stale due to:
1. Event data being amended after evaluation
2. Rule definition versions changing after evaluation

Scenario:
    1. Ingest events, evaluate rules - everything clean
    2. Create request case, verify no stale_evaluations blocker
    3. Simulate event amendment (UPDATE amended_at to after evaluation time)
    4. check_blocking_defects() -> should include stale_evaluations blocker
    5. Re-evaluate the amended event
    6. check_blocking_defects() -> stale_evaluations blocker gone
    7. Simulate rule version change (UPDATE rule_definition rule_version)
    8. check_blocking_defects() -> should include stale_evaluations again

Usage:
    pytest tests/test_e2e_stale_evaluations.py -v --tb=short

Requires:
    - PostgreSQL with fsma schema and all migrations applied
    - Set DATABASE_URL environment variable
"""

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List

import pytest

# Skip if no database configured
DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("ADMIN_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="DATABASE_URL not set - skipping E2E integration test",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def db_session():
    """Create a DB session for the entire test module."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        session.execute(text("SELECT 1"))
    except Exception:
        session.rollback()

    yield session
    session.rollback()
    session.close()


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
    """Create a RulesEngine instance."""
    from shared.rules_engine import RulesEngine
    return RulesEngine(db_session)


@pytest.fixture(scope="module")
def canonical_store(db_session):
    """Create a CanonicalEventStore instance."""
    from shared.canonical_persistence import CanonicalEventStore
    return CanonicalEventStore(db_session)


# ---------------------------------------------------------------------------
# Test Data
# ---------------------------------------------------------------------------

PRODUCT = "Stale Eval Test Lettuce"
SUPPLIER = "Stale Eval Test Farm"
LOT_CODE = "LOT-STALE-TEST-001"


def _make_events(tenant_id: str) -> List[Dict]:
    """Generate clean test events that will pass rules."""
    base_time = datetime.now(timezone.utc) - timedelta(days=10)

    return [
        {
            "event_id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "event_type": "shipping",
            "event_timestamp": (base_time + timedelta(days=0)).isoformat(),
            "product_reference": PRODUCT,
            "traceability_lot_code": LOT_CODE,
            "quantity": 2000.0,
            "unit_of_measure": "lbs",
            "from_facility_reference": SUPPLIER,
            "to_facility_reference": "Test Distribution Center",
            "from_entity_reference": SUPPLIER,
            "to_entity_reference": "Test Retailer Inc",
            "kdes": {
                "ship_date": (base_time + timedelta(days=0)).strftime("%Y-%m-%d"),
                "carrier": "Test Carrier",
                "bill_of_lading": "BOL-STALE-TEST-001",
            },
            "confidence_score": 0.97,
            "status": "active",
        },
        {
            "event_id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "event_type": "receiving",
            "event_timestamp": (base_time + timedelta(days=1)).isoformat(),
            "product_reference": PRODUCT,
            "traceability_lot_code": LOT_CODE,
            "quantity": 1950.0,
            "unit_of_measure": "lbs",
            "from_facility_reference": SUPPLIER,
            "to_facility_reference": "Test Distribution Center",
            "to_entity_reference": "Test Retailer Inc",
            "kdes": {
                "receive_date": (base_time + timedelta(days=1)).strftime("%Y-%m-%d"),
                "tlc_source_reference": SUPPLIER,
                "tlc_source_gln": "0061414100099",
                "receiving_location": "Dock 1",
                "temperature": "35F",
            },
            "confidence_score": 0.98,
            "status": "active",
        },
    ]


# ---------------------------------------------------------------------------
# The Test: Stale Evaluation Detection
# ---------------------------------------------------------------------------

class TestStaleEvaluationDetection:
    """Prove stale evaluation detection blocks submission correctly."""

    @pytest.fixture(autouse=True)
    def _ensure_clean_session(self, db_session):
        """Ensure DB session is clean before each test."""
        try:
            from sqlalchemy import text
            db_session.execute(text("SELECT 1"))
        except Exception:
            db_session.rollback()

    def test_01_ingest_events(self, db_session, tenant_id, canonical_store):
        """Step 1: Ingest events into canonical store."""
        from shared.canonical_event import TraceabilityEvent, IngestionSource

        events = _make_events(tenant_id)
        persisted = []

        for event_data in events:
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
                source_system=IngestionSource(
                    event_data.get("source_system", "csv_upload")
                ),
                status="active",
            )
            result = canonical_store.persist_event(te)
            persisted.append(result)

        assert len(persisted) == 2, f"Expected 2 persisted events, got {len(persisted)}"

    def test_02_evaluate_rules(self, db_session, tenant_id, rules_engine):
        """Step 2: Evaluate all events against rules."""
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
        assert len(events) >= 2, f"Expected >=2 events, got {len(events)}"

        for event in events:
            full = db_session.execute(
                text(
                    "SELECT * FROM fsma.traceability_events "
                    "WHERE event_id = :eid AND tenant_id = :tid"
                ),
                {"eid": str(event["event_id"]), "tid": tenant_id},
            ).mappings().fetchone()
            if full:
                event_dict = dict(full)
                if event_dict.get("kdes") and isinstance(event_dict["kdes"], str):
                    event_dict["kdes"] = json.loads(event_dict["kdes"])
                rules_engine.evaluate_event(
                    event_dict, persist=True, tenant_id=tenant_id,
                )

        # Verify evaluations were persisted
        eval_count = db_session.execute(
            text("""
                SELECT COUNT(*)
                FROM fsma.rule_evaluations
                WHERE tenant_id = :tid
            """),
            {"tid": tenant_id},
        ).scalar()
        assert eval_count > 0, "Expected at least 1 rule evaluation"

    def test_03_create_request_case(self, tenant_id, workflow):
        """Step 3: Create request case."""
        case = workflow.create_request_case(
            tenant_id=tenant_id,
            requesting_party="FDA",
            request_channel="email",
            scope_type="product_recall",
            scope_description="Stale evaluation test case",
            response_hours=24,
            affected_products=[PRODUCT],
            affected_lots=[LOT_CODE],
            affected_facilities=[SUPPLIER],
        )

        assert case["package_status"] == "intake"
        self.__class__._case_id = case["request_case_id"]

    def test_04_advance_to_collecting(self, tenant_id, workflow):
        """Step 4: Advance case to collecting stage so blocking defects work."""
        case_id = self.__class__._case_id

        workflow.update_scope(
            tenant_id, case_id,
            scope_description="All stale eval test lots",
        )

        result = workflow.collect_records(tenant_id, case_id)
        assert result["total_records"] >= 1, (
            f"Expected >=1 records in scope, got {result['total_records']}"
        )

    def test_05_no_stale_evaluations_initially(self, db_session, tenant_id, workflow):
        """Step 5: Verify no stale_evaluations blocker when everything is fresh."""
        case_id = self.__class__._case_id
        check = workflow.check_blocking_defects(tenant_id, case_id)

        stale_blockers = [
            b for b in check["blockers"]
            if b.get("category") == "stale_evaluations"
            or b.get("type") == "stale_evaluations"
        ]
        assert len(stale_blockers) == 0, (
            f"Expected no stale evaluation blockers initially, "
            f"got {stale_blockers}"
        )

    def test_06_simulate_event_amendment(self, db_session, tenant_id):
        """Step 6: Simulate event amendment by setting amended_at in the future."""
        from sqlalchemy import text

        # Get one event ID
        event_row = db_session.execute(
            text("""
                SELECT event_id FROM fsma.traceability_events
                WHERE tenant_id = :tid AND status = 'active'
                LIMIT 1
            """),
            {"tid": tenant_id},
        ).fetchone()
        assert event_row, "Expected at least one event"

        amended_event_id = str(event_row[0])
        self.__class__._amended_event_id = amended_event_id

        # Set amended_at to now (after evaluation time)
        future_time = datetime.now(timezone.utc) + timedelta(minutes=5)
        db_session.execute(
            text("""
                UPDATE fsma.traceability_events
                SET amended_at = :amended_at
                WHERE event_id = :eid AND tenant_id = :tid
            """),
            {
                "amended_at": future_time.isoformat(),
                "eid": amended_event_id,
                "tid": tenant_id,
            },
        )
        db_session.flush()

    def test_07_stale_evaluation_blocks_submission(self, db_session, tenant_id, workflow):
        """Step 7: After event amendment, stale_evaluations blocker should appear."""
        case_id = self.__class__._case_id
        check = workflow.check_blocking_defects(tenant_id, case_id)

        stale_blockers = [
            b for b in check["blockers"]
            if b.get("category") == "stale_evaluations"
            or b.get("type") == "stale_evaluations"
        ]
        assert len(stale_blockers) > 0, (
            "Expected stale_evaluations blocker after event amendment, "
            f"but got none. All blockers: {check['blockers']}"
        )

        blocker = stale_blockers[0]
        assert blocker["count"] >= 1
        assert any(
            d["reason"] == "event_modified" for d in blocker["details"]
        ), f"Expected 'event_modified' reason in details: {blocker['details']}"

        # Verify overall can_submit is False
        assert not check["can_submit"], (
            "Expected can_submit=False with stale evaluations"
        )

    def test_08_re_evaluate_clears_stale_event(
        self, db_session, tenant_id, rules_engine
    ):
        """Step 8: Re-evaluate the amended event to clear the stale blocker."""
        from sqlalchemy import text

        amended_event_id = self.__class__._amended_event_id

        # Delete old evaluations for this event so re-evaluation is fresh
        db_session.execute(
            text("""
                DELETE FROM fsma.rule_evaluations
                WHERE event_id = :eid AND tenant_id = :tid
            """),
            {"eid": amended_event_id, "tid": tenant_id},
        )
        db_session.flush()

        # Re-evaluate
        full = db_session.execute(
            text(
                "SELECT * FROM fsma.traceability_events "
                "WHERE event_id = :eid AND tenant_id = :tid"
            ),
            {"eid": amended_event_id, "tid": tenant_id},
        ).mappings().fetchone()

        assert full, f"Event {amended_event_id} not found"
        event_dict = dict(full)
        if event_dict.get("kdes") and isinstance(event_dict["kdes"], str):
            event_dict["kdes"] = json.loads(event_dict["kdes"])

        rules_engine.evaluate_event(event_dict, persist=True, tenant_id=tenant_id)

    def test_09_stale_blocker_cleared_after_re_evaluation(
        self, db_session, tenant_id, workflow
    ):
        """Step 9: After re-evaluation, stale_evaluations blocker should be gone."""
        case_id = self.__class__._case_id
        check = workflow.check_blocking_defects(tenant_id, case_id)

        stale_blockers = [
            b for b in check["blockers"]
            if b.get("category") == "stale_evaluations"
            or b.get("type") == "stale_evaluations"
        ]
        assert len(stale_blockers) == 0, (
            f"Expected no stale evaluation blockers after re-evaluation, "
            f"got {stale_blockers}"
        )

    def test_10_simulate_rule_version_change(self, db_session, tenant_id):
        """Step 10: Simulate rule version change by bumping rule_version."""
        from sqlalchemy import text

        # Find a rule_id that has evaluations for this tenant
        rule_row = db_session.execute(
            text("""
                SELECT DISTINCT re.rule_id, rd.rule_version
                FROM fsma.rule_evaluations re
                JOIN fsma.rule_definitions rd ON rd.rule_id = re.rule_id
                WHERE re.tenant_id = :tid
                LIMIT 1
            """),
            {"tid": tenant_id},
        ).fetchone()
        assert rule_row, "Expected at least one evaluated rule"

        rule_id = str(rule_row[0])
        current_version = rule_row[1]
        self.__class__._bumped_rule_id = rule_id
        self.__class__._original_rule_version = current_version

        # Bump the rule version to simulate a rule change
        db_session.execute(
            text("""
                UPDATE fsma.rule_definitions
                SET rule_version = :new_version
                WHERE rule_id = :rid
            """),
            {"new_version": current_version + 1, "rid": rule_id},
        )
        db_session.flush()

    def test_11_stale_evaluation_from_rule_version_change(
        self, db_session, tenant_id, workflow
    ):
        """Step 11: After rule version bump, stale_evaluations blocker should appear."""
        case_id = self.__class__._case_id
        check = workflow.check_blocking_defects(tenant_id, case_id)

        stale_blockers = [
            b for b in check["blockers"]
            if b.get("category") == "stale_evaluations"
            or b.get("type") == "stale_evaluations"
        ]
        assert len(stale_blockers) > 0, (
            "Expected stale_evaluations blocker after rule version change, "
            f"but got none. All blockers: {check['blockers']}"
        )

        blocker = stale_blockers[0]
        assert any(
            d["reason"] == "rule_version_changed" for d in blocker["details"]
        ), f"Expected 'rule_version_changed' reason in details: {blocker['details']}"

        # Verify can_submit is False
        assert not check["can_submit"], (
            "Expected can_submit=False with stale evaluations from rule change"
        )

    def test_12_cleanup_rule_version(self, db_session, tenant_id):
        """Step 12: Restore rule version to avoid polluting other tests."""
        from sqlalchemy import text

        rule_id = self.__class__._bumped_rule_id
        original_version = self.__class__._original_rule_version

        db_session.execute(
            text("""
                UPDATE fsma.rule_definitions
                SET rule_version = :version
                WHERE rule_id = :rid
            """),
            {"version": original_version, "rid": rule_id},
        )
        db_session.flush()
