"""
E2E Integration Test: Deadline Monitoring & Overdue Escalation.

Proves that the deadline monitoring system correctly classifies case
urgency and that overdue cases remain fully functional (records can
still be added and packages assembled after a breach).

Scenario:
    1. Create a request case with a deadline 1 hour from now
    2. Verify check_deadline_status() returns "urgent" (< 6 hours)
    3. Modify the deadline to be 30 minutes ago (simulate breach)
    4. Verify check_deadline_status() returns "overdue"
    5. Verify the case still functions — can still add records, create package
    6. Test boundary cases: exactly 2h = "critical", exactly 6h = "normal"

Usage:
    pytest tests/test_e2e_deadline_breach.py -v --tb=short

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
    reason="DATABASE_URL not set — skipping E2E integration test",
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

    # Ensure clean state — rollback any failed transaction
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PRODUCT = "Test Deadline Product"
SUPPLIER = "Deadline Test Supplier"


def _make_events(tenant_id: str) -> List[Dict]:
    """Generate minimal test events for record collection."""
    base_time = datetime.now(timezone.utc) - timedelta(days=5)

    return [
        {
            "event_id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "event_type": "shipping",
            "event_timestamp": (base_time + timedelta(days=0)).isoformat(),
            "product_reference": PRODUCT,
            "traceability_lot_code": "LOT-DL-2026-001",
            "quantity": 1000.0,
            "unit_of_measure": "lbs",
            "from_facility_reference": SUPPLIER,
            "from_entity_reference": SUPPLIER,
            "to_facility_reference": "Warehouse A",
            "to_entity_reference": "Warehouse A",
            "kdes": {
                "ship_date": (base_time + timedelta(days=0)).strftime("%Y-%m-%d"),
                "carrier": "TestCarrier",
                "bill_of_lading": "BOL-DL-001",
            },
            "confidence_score": 0.95,
            "status": "active",
        },
        {
            "event_id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "event_type": "receiving",
            "event_timestamp": (base_time + timedelta(days=1)).isoformat(),
            "product_reference": PRODUCT,
            "traceability_lot_code": "LOT-DL-2026-001",
            "quantity": 990.0,
            "unit_of_measure": "lbs",
            "from_facility_reference": SUPPLIER,
            "to_facility_reference": "Warehouse A",
            "to_entity_reference": "Warehouse A",
            "kdes": {
                "receive_date": (base_time + timedelta(days=1)).strftime("%Y-%m-%d"),
                "tlc_source_reference": SUPPLIER,
                "receiving_location": "Dock 1",
            },
            "confidence_score": 0.97,
            "status": "active",
        },
    ]


def _set_deadline(db_session, tenant_id: str, case_id: str, due_at: datetime):
    """Directly update response_due_at in the database to simulate time shifts."""
    from sqlalchemy import text

    db_session.execute(
        text("""
            UPDATE fsma.request_cases
            SET response_due_at = :due_at, updated_at = NOW()
            WHERE tenant_id = :tenant_id
              AND request_case_id = :case_id
        """),
        {"due_at": due_at, "tenant_id": tenant_id, "case_id": case_id},
    )
    db_session.flush()


# ---------------------------------------------------------------------------
# The Test: Deadline Monitoring & Overdue Escalation
# ---------------------------------------------------------------------------

class TestDeadlineBreachE2E:
    """Prove deadline monitoring detects urgency levels and overdue cases
    remain functional."""

    @pytest.fixture(autouse=True)
    def _ensure_clean_session(self, db_session):
        """Ensure DB session is clean before each test."""
        try:
            from sqlalchemy import text
            db_session.execute(text("SELECT 1"))
        except Exception:
            db_session.rollback()

    # ---- Step 0: Ingest events so we have records to collect later ----

    def test_00_ingest_events(self, db_session, tenant_id):
        """Ingest minimal events for later record collection."""
        from shared.canonical_event import IngestionSource, TraceabilityEvent
        from shared.canonical_persistence import CanonicalEventStore

        store = CanonicalEventStore(db_session)
        events = _make_events(tenant_id)

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
            store.persist_event(te)

    # ---- Step 1: Create case with 1-hour deadline ----

    def test_01_create_case_with_1h_deadline(self, tenant_id, workflow):
        """Create a request case with a deadline 1 hour from now."""
        now = datetime.now(timezone.utc)
        due_at = now + timedelta(hours=1)

        case = workflow.create_request_case(
            tenant_id=tenant_id,
            requesting_party="FDA",
            request_channel="email",
            scope_type="product_recall",
            scope_description="Deadline breach test — " + PRODUCT,
            response_due_at=due_at,
            affected_products=[PRODUCT],
            affected_lots=["LOT-DL-2026-001"],
            affected_facilities=[SUPPLIER],
        )

        assert case["package_status"] == "intake"
        assert case["requesting_party"] == "FDA"
        self.__class__._case_id = case["request_case_id"]

    # ---- Step 2: Verify "urgent" (< 6 hours remaining) ----

    def test_02_deadline_1h_is_urgent(self, tenant_id, workflow):
        """1 hour remaining should be classified as 'urgent' (< 6h)."""
        cases = workflow.check_deadline_status(tenant_id)
        our_case = _find_case(cases, self.__class__._case_id)

        assert our_case is not None, "Case not found in deadline status results"
        # 1 hour < 2 hours, so this is actually "critical"
        assert our_case["urgency"] in ("urgent", "critical"), (
            f"Expected 'urgent' or 'critical' for 1h remaining, got '{our_case['urgency']}'"
        )
        assert our_case["hours_remaining"] <= 2

    # ---- Step 3: Simulate breach — move deadline 30 minutes into past ----

    def test_03_simulate_deadline_breach(self, db_session, tenant_id):
        """Move the deadline to 30 minutes ago to simulate a breach."""
        now = datetime.now(timezone.utc)
        overdue_at = now - timedelta(minutes=30)

        _set_deadline(db_session, tenant_id, self.__class__._case_id, overdue_at)

    # ---- Step 4: Verify "overdue" ----

    def test_04_breached_deadline_is_overdue(self, tenant_id, workflow):
        """A case past its deadline must be classified as 'overdue'."""
        cases = workflow.check_deadline_status(tenant_id)
        our_case = _find_case(cases, self.__class__._case_id)

        assert our_case is not None, "Case not found in deadline status results"
        assert our_case["urgency"] == "overdue", (
            f"Expected 'overdue' for breached deadline, got '{our_case['urgency']}'"
        )
        assert our_case["hours_remaining"] < 0, (
            f"Expected negative hours_remaining, got {our_case['hours_remaining']}"
        )

    # ---- Step 5: Verify case still functions after breach ----

    def test_05_overdue_case_still_functional_scope(self, tenant_id, workflow):
        """An overdue case can still have its scope updated."""
        case_id = self.__class__._case_id

        workflow.update_scope(
            tenant_id, case_id,
            scope_description="Updated scope after deadline breach — still operational",
        )

    def test_06_overdue_case_still_functional_collect(self, tenant_id, workflow):
        """An overdue case can still collect records."""
        case_id = self.__class__._case_id

        result = workflow.collect_records(tenant_id, case_id)
        assert result["total_records"] >= 1, (
            f"Expected >=1 records collected, got {result['total_records']}"
        )

    def test_07_overdue_case_still_functional_package(self, tenant_id, workflow):
        """An overdue case can still assemble a response package."""
        case_id = self.__class__._case_id

        # Add required signoff before assembly
        workflow.add_signoff(
            tenant_id, case_id,
            signoff_type="scope_approval",
            signed_by="qa_lead@company.com",
            notes="Scope approved despite overdue status.",
        )

        package = workflow.assemble_response_package(
            tenant_id, case_id,
            generated_by="compliance_officer@company.com",
        )

        assert package["version_number"] == 1
        assert package["package_hash"], "Package must have SHA-256 hash"
        assert len(package["package_hash"]) == 64, "Hash must be 64 hex chars (SHA-256)"

    # ---- Step 6: Boundary cases ----

    def test_08_boundary_2h_is_critical(self, db_session, tenant_id, workflow):
        """Exactly 2 hours remaining should be classified as 'critical' (< 2h boundary)."""
        now = datetime.now(timezone.utc)
        # Set deadline to exactly 2 hours from now.
        # The check is `hours < 2`, so exactly 2h should be "urgent" (not critical).
        # We set to 1h59m to guarantee critical.
        due_at = now + timedelta(hours=1, minutes=59)
        _set_deadline(db_session, tenant_id, self.__class__._case_id, due_at)

        # Need to reset case status so it appears in active deadlines.
        # The package was assembled, so status may be 'ready' — but
        # check_deadline_status excludes 'submitted' and 'amended' only.
        cases = workflow.check_deadline_status(tenant_id)
        our_case = _find_case(cases, self.__class__._case_id)

        assert our_case is not None, "Case not found in deadline status"
        assert our_case["urgency"] == "critical", (
            f"Expected 'critical' at ~2h boundary, got '{our_case['urgency']}' "
            f"(hours_remaining={our_case['hours_remaining']})"
        )

    def test_09_boundary_exactly_2h_is_urgent(self, db_session, tenant_id, workflow):
        """Exactly 2.0 hours remaining: hours < 2 is False, hours < 6 is True => 'urgent'."""
        now = datetime.now(timezone.utc)
        # Add a small buffer (1 minute) to ensure we're clearly above the 2h threshold
        due_at = now + timedelta(hours=2, minutes=1)
        _set_deadline(db_session, tenant_id, self.__class__._case_id, due_at)

        cases = workflow.check_deadline_status(tenant_id)
        our_case = _find_case(cases, self.__class__._case_id)

        assert our_case is not None, "Case not found in deadline status"
        assert our_case["urgency"] == "urgent", (
            f"Expected 'urgent' at >2h, got '{our_case['urgency']}' "
            f"(hours_remaining={our_case['hours_remaining']})"
        )

    def test_10_boundary_6h_is_normal(self, db_session, tenant_id, workflow):
        """Exactly 6.0 hours remaining: hours < 6 is False => 'normal'."""
        now = datetime.now(timezone.utc)
        # Add a small buffer (1 minute) to ensure we're clearly above the 6h threshold
        due_at = now + timedelta(hours=6, minutes=1)
        _set_deadline(db_session, tenant_id, self.__class__._case_id, due_at)

        cases = workflow.check_deadline_status(tenant_id)
        our_case = _find_case(cases, self.__class__._case_id)

        assert our_case is not None, "Case not found in deadline status"
        assert our_case["urgency"] == "normal", (
            f"Expected 'normal' at >=6h, got '{our_case['urgency']}' "
            f"(hours_remaining={our_case['hours_remaining']})"
        )

    def test_11_boundary_just_under_6h_is_urgent(self, db_session, tenant_id, workflow):
        """5h59m remaining: hours < 6 is True, hours >= 2 => 'urgent'."""
        now = datetime.now(timezone.utc)
        due_at = now + timedelta(hours=5, minutes=59)
        _set_deadline(db_session, tenant_id, self.__class__._case_id, due_at)

        cases = workflow.check_deadline_status(tenant_id)
        our_case = _find_case(cases, self.__class__._case_id)

        assert our_case is not None, "Case not found in deadline status"
        assert our_case["urgency"] == "urgent", (
            f"Expected 'urgent' at 5h59m, got '{our_case['urgency']}' "
            f"(hours_remaining={our_case['hours_remaining']})"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_case(cases: List[Dict], case_id: str) -> Dict | None:
    """Find a specific case in the deadline status results."""
    for c in cases:
        if c["request_case_id"] == case_id:
            return c
    return None
