"""
E2E Integration Test: Identity Ambiguity Blocks Package Submission.

Proves that unresolved identity ambiguity prevents FDA package submission
and that resolving the ambiguity (via merge) clears the blocker.

Scenario:
    1. Ingest 2 events from slightly different facility names:
       "Salinas Valley Farms" vs "Salinas Valley Farm" (typo — missing 's')
    2. Register both as canonical entities via IdentityResolutionService
    3. Run fuzzy matching — detect >=85% similarity
    4. Queue an identity review item for the ambiguous match
    5. Create a request case scoping both events
    6. check_blocking_defects() returns identity_ambiguity as a blocker
    7. Resolve the identity review (merge the entities)
    8. check_blocking_defects() no longer includes identity_ambiguity

Usage:
    pytest tests/test_e2e_identity_ambiguity.py -v --tb=short

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


@pytest.fixture(scope="module")
def identity_service(db_session):
    """Create an IdentityResolutionService instance."""
    from shared.identity_resolution import IdentityResolutionService
    return IdentityResolutionService(db_session)


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
# Test Data: Two events with slightly different facility names
# ---------------------------------------------------------------------------

FACILITY_A = "Salinas Valley Farms"
FACILITY_B = "Salinas Valley Farm"   # typo — missing trailing 's'
PRODUCT = "Organic Romaine Hearts"


def _make_events(tenant_id: str) -> List[Dict]:
    """Generate two events from near-duplicate facility names."""
    base_time = datetime.now(timezone.utc) - timedelta(days=10)

    return [
        # Event 1: Harvesting from "Salinas Valley Farms"
        {
            "event_id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "event_type": "harvesting",
            "event_timestamp": (base_time + timedelta(days=0)).isoformat(),
            "product_reference": PRODUCT,
            "traceability_lot_code": "LOT-AMB-2026-001A",
            "quantity": 3000.0,
            "unit_of_measure": "lbs",
            "from_facility_reference": FACILITY_A,
            "from_entity_reference": FACILITY_A,
            "kdes": {
                "harvest_date": (base_time + timedelta(days=0)).strftime("%Y-%m-%d"),
                "field_coordinates": "36.6744,-121.6550",
                "growing_area_code": "CA-SVF-BLOCK-3",
            },
            "confidence_score": 0.95,
            "status": "active",
        },
        # Event 2: Shipping from "Salinas Valley Farm" (typo variant)
        {
            "event_id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "event_type": "shipping",
            "event_timestamp": (base_time + timedelta(days=1)).isoformat(),
            "product_reference": PRODUCT,
            "traceability_lot_code": "LOT-AMB-2026-001B",
            "quantity": 2800.0,
            "unit_of_measure": "lbs",
            "from_facility_reference": FACILITY_B,
            "from_entity_reference": FACILITY_B,
            "to_facility_reference": "MegaMart Distribution Center",
            "to_entity_reference": "MegaMart Inc",
            "kdes": {
                "ship_date": (base_time + timedelta(days=1)).strftime("%Y-%m-%d"),
                "carrier": "FedEx Freight",
                "bill_of_lading": "BOL-2026-AMB-001",
            },
            "confidence_score": 0.93,
            "status": "active",
        },
    ]


# ---------------------------------------------------------------------------
# The Test: Identity Ambiguity Blocks Submission
# ---------------------------------------------------------------------------

class TestIdentityAmbiguityBlocksSubmission:
    """Prove that unresolved identity ambiguity blocks FDA package submission."""

    @pytest.fixture(autouse=True)
    def _ensure_clean_session(self, db_session):
        """Ensure DB session is clean before each test."""
        try:
            from sqlalchemy import text
            db_session.execute(text("SELECT 1"))
        except Exception:
            db_session.rollback()

    # ------------------------------------------------------------------
    # Step 1: Ingest two events with near-duplicate facility names
    # ------------------------------------------------------------------

    def test_01_ingest_events(self, db_session, tenant_id, canonical_store):
        """Ingest 2 events from slightly different facility names."""
        from shared.canonical_event import IngestionSource, TraceabilityEvent

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

        # Stash event IDs for later steps
        self.__class__._event_ids = [e["event_id"] for e in events]

    # ------------------------------------------------------------------
    # Step 2: Register both facility names as canonical entities
    # ------------------------------------------------------------------

    def test_02_register_entities(self, tenant_id, identity_service):
        """Register both facility name variants as separate canonical entities."""
        entity_a = identity_service.register_entity(
            tenant_id,
            "facility",
            FACILITY_A,
            created_by="test@example.com",
        )
        entity_b = identity_service.register_entity(
            tenant_id,
            "facility",
            FACILITY_B,
            created_by="test@example.com",
        )

        assert entity_a["entity_id"] != entity_b["entity_id"]
        assert entity_a["canonical_name"] == FACILITY_A
        assert entity_b["canonical_name"] == FACILITY_B

        self.__class__._entity_a_id = entity_a["entity_id"]
        self.__class__._entity_b_id = entity_b["entity_id"]

    # ------------------------------------------------------------------
    # Step 3: Fuzzy matching detects high similarity
    # ------------------------------------------------------------------

    def test_03_fuzzy_match_detects_similarity(self, tenant_id, identity_service):
        """find_potential_matches should detect >=85% similarity."""
        matches = identity_service.find_potential_matches(
            tenant_id,
            FACILITY_B,
            entity_type="facility",
            threshold=0.60,
        )

        # We expect at least one match with the other entity
        other_entity_id = self.__class__._entity_a_id
        high_matches = [
            m for m in matches
            if m["entity_id"] == other_entity_id and m["confidence"] >= 0.85
        ]

        assert len(high_matches) >= 1, (
            f"Expected fuzzy match between '{FACILITY_A}' and '{FACILITY_B}' "
            f"at >=85% but got: {matches}"
        )

        self.__class__._match_confidence = high_matches[0]["confidence"]

    # ------------------------------------------------------------------
    # Step 4: Queue the ambiguous match for human review
    # ------------------------------------------------------------------

    def test_04_queue_identity_review(self, db_session, tenant_id, identity_service):
        """Create an identity review queue item for the ambiguous match."""
        review = identity_service.queue_for_review(
            tenant_id=tenant_id,
            entity_a_id=self.__class__._entity_a_id,
            entity_b_id=self.__class__._entity_b_id,
            match_type="ambiguous",
            match_confidence=self.__class__._match_confidence,
            matching_fields={"name_similarity": self.__class__._match_confidence},
        )

        assert review["status"] == "pending"
        assert review["match_confidence"] >= 0.85

        self.__class__._review_id = review["review_id"]

        # Flush to DB so check_blocking_defects can see it
        db_session.flush()

    # ------------------------------------------------------------------
    # Step 5: Create a request case scoping both events
    # ------------------------------------------------------------------

    def test_05_create_request_case(self, tenant_id, workflow):
        """Create an FDA request case that scopes both events."""
        case = workflow.create_request_case(
            tenant_id=tenant_id,
            requesting_party="FDA",
            request_channel="email",
            scope_type="product_recall",
            scope_description="Identity ambiguity test — romaine hearts",
            response_hours=24,
            affected_products=[PRODUCT],
            affected_lots=["LOT-AMB-2026-001A", "LOT-AMB-2026-001B"],
            affected_facilities=[FACILITY_A, FACILITY_B],
        )

        assert case["package_status"] == "intake"
        self.__class__._case_id = case["request_case_id"]

    # ------------------------------------------------------------------
    # Step 6: check_blocking_defects returns identity_ambiguity blocker
    # ------------------------------------------------------------------

    def test_06_identity_ambiguity_blocks_submission(
        self, db_session, tenant_id, workflow
    ):
        """check_blocking_defects() must include identity_ambiguity blocker."""
        case_id = self.__class__._case_id

        # Advance the case far enough that collect/gap analysis can run
        workflow.update_scope(
            tenant_id,
            case_id,
            scope_description="All romaine lots from Salinas Valley facilities",
        )
        workflow.collect_records(tenant_id, case_id)
        workflow.run_gap_analysis(tenant_id, case_id)

        # Now check for blocking defects
        check = workflow.check_blocking_defects(tenant_id, case_id)

        # Submission must be blocked
        assert not check["can_submit"], (
            f"Expected submission to be BLOCKED but can_submit=True. "
            f"Blockers: {check['blockers']}"
        )

        # Specifically verify identity_ambiguity is among the blockers
        identity_blockers = [
            b for b in check["blockers"]
            if b["type"] == "identity_ambiguity"
        ]
        assert len(identity_blockers) >= 1, (
            f"Expected at least 1 identity_ambiguity blocker but found none. "
            f"All blockers: {[b['type'] for b in check['blockers']]}"
        )

        # Verify the blocker references our entities
        ib = identity_blockers[0]
        assert FACILITY_A in ib["message"] or FACILITY_B in ib["message"], (
            f"Blocker message should reference one of the facility names: {ib['message']}"
        )
        assert ib["similarity"] >= 0.85

    # ------------------------------------------------------------------
    # Step 7: Resolve the identity review (merge entities)
    # ------------------------------------------------------------------

    def test_07_resolve_identity_review(
        self, db_session, tenant_id, identity_service
    ):
        """Resolve the review as confirmed_match — triggers auto-merge."""
        result = identity_service.resolve_review(
            tenant_id=tenant_id,
            review_id=self.__class__._review_id,
            resolution="confirmed_match",
            resolved_by="qa_lead@company.com",
            resolution_notes="Confirmed typo — same facility.",
            auto_merge=True,
        )

        assert result["resolution"] == "confirmed_match"
        assert "merge" in result, "Expected auto-merge to fire"
        assert result["merge"]["merge_id"], "Merge must produce a merge_id"

        # Flush so the next check sees the resolved status
        db_session.flush()

    # ------------------------------------------------------------------
    # Step 8: check_blocking_defects no longer includes identity_ambiguity
    # ------------------------------------------------------------------

    def test_08_identity_ambiguity_cleared(self, tenant_id, workflow):
        """After merge, identity_ambiguity should no longer block."""
        case_id = self.__class__._case_id

        check = workflow.check_blocking_defects(tenant_id, case_id)

        identity_blockers = [
            b for b in check["blockers"]
            if b["type"] == "identity_ambiguity"
        ]
        assert len(identity_blockers) == 0, (
            f"Expected 0 identity_ambiguity blockers after merge, "
            f"but found {len(identity_blockers)}: {identity_blockers}"
        )

        # There may still be other blockers (missing signoffs, etc.)
        # but identity_ambiguity specifically must be gone
        remaining_types = [b["type"] for b in check["blockers"]]
        assert "identity_ambiguity" not in remaining_types, (
            f"identity_ambiguity still present in blockers: {remaining_types}"
        )
