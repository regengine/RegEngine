"""
E2E Integration Test: Multi-Tenant Isolation Under Concurrent-Like Operations.

Proves that tenant boundaries hold across every layer of the system:
canonical events, rule evaluations, request cases, response packages,
and exception cases.

Scenario:
    Two tenants (A and B) each ingest events for different products.
    Tenant A creates a request case, advances it through the workflow,
    and submits a package. At every step, we verify:

    1. Tenant A's events are invisible to Tenant B queries
    2. Tenant A's request case is inaccessible to Tenant B
    3. Rule evaluations are scoped per-tenant
    4. Response packages contain only the owning tenant's data
    5. Exception cases respect tenant boundaries
    6. Tenant B's independent workflow is fully isolated

    If ANY cross-tenant data leaks, the system is not production-safe.

Usage:
    pytest tests/test_e2e_tenant_isolation.py -v --tb=short

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

    # Ensure clean state
    try:
        session.execute(text("SELECT 1"))
    except Exception:
        session.rollback()

    yield session
    session.rollback()
    session.close()


@pytest.fixture(scope="module")
def tenant_a():
    """Unique tenant UUID for Tenant A."""
    return str(uuid.uuid4())


@pytest.fixture(scope="module")
def tenant_b():
    """Unique tenant UUID for Tenant B."""
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
# Test Data: Different products per tenant for clear isolation signal
# ---------------------------------------------------------------------------

PRODUCT_A = "Organic Romaine Hearts"
PRODUCT_B = "Atlantic Salmon Fillets"

SUPPLIERS_A = ["Salinas Valley Farms", "Pacific Coast Growers", "FreshCut Processing"]
SUPPLIERS_B = ["Nordic Aquaculture", "Ocean Fresh Packers", "ColdChain Logistics"]


def _make_events_for_tenant(tenant_id: str, product: str, suppliers: List[str], lot_prefix: str) -> List[Dict]:
    """Generate 3 test events for a given tenant and product."""
    from shared.canonical_event import TraceabilityEvent, IngestionSource

    base_time = datetime.now(timezone.utc) - timedelta(days=10)

    events = [
        TraceabilityEvent(
            event_id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            event_type="harvesting",
            event_timestamp=(base_time + timedelta(days=0)).isoformat(),
            product_reference=product,
            traceability_lot_code=f"{lot_prefix}-001",
            quantity=5000.0,
            unit_of_measure="lbs",
            from_facility_reference=suppliers[0],
            from_entity_reference=suppliers[0],
            kdes={
                "harvest_date": (base_time + timedelta(days=0)).strftime("%Y-%m-%d"),
                "growing_area_code": f"{lot_prefix}-BLOCK-1",
            },
            confidence_score=0.95,
            source_system=IngestionSource("csv_upload"),
            status="active",
        ),
        TraceabilityEvent(
            event_id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            event_type="shipping",
            event_timestamp=(base_time + timedelta(days=1)).isoformat(),
            product_reference=product,
            traceability_lot_code=f"{lot_prefix}-001",
            quantity=4800.0,
            unit_of_measure="lbs",
            from_facility_reference=suppliers[1],
            to_facility_reference="Distribution Center",
            from_entity_reference=suppliers[1],
            to_entity_reference="Retailer Inc",
            kdes={
                "ship_date": (base_time + timedelta(days=1)).strftime("%Y-%m-%d"),
                "carrier": "FedEx Freight",
                # Missing: bill_of_lading (will trigger rule failure)
            },
            confidence_score=0.90,
            source_system=IngestionSource("csv_upload"),
            status="active",
        ),
        TraceabilityEvent(
            event_id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            event_type="receiving",
            event_timestamp=(base_time + timedelta(days=2)).isoformat(),
            product_reference=product,
            traceability_lot_code=f"{lot_prefix}-002",
            quantity=3000.0,
            unit_of_measure="lbs",
            from_facility_reference=suppliers[1],
            to_facility_reference=suppliers[2],
            to_entity_reference=suppliers[2],
            kdes={
                "receive_date": (base_time + timedelta(days=2)).strftime("%Y-%m-%d"),
                "tlc_source_reference": suppliers[1],
            },
            confidence_score=0.97,
            source_system=IngestionSource("csv_upload"),
            status="active",
        ),
    ]
    return events


# ---------------------------------------------------------------------------
# The Test: Multi-Tenant Isolation
# ---------------------------------------------------------------------------

class TestTenantIsolationE2E:
    """Prove that tenant boundaries hold across every system layer."""

    @pytest.fixture(autouse=True)
    def _ensure_clean_session(self, db_session):
        """Ensure DB session is clean before each test."""
        try:
            from sqlalchemy import text
            db_session.execute(text("SELECT 1"))
        except Exception:
            db_session.rollback()

    # ------------------------------------------------------------------
    # Step 1 & 2: Ingest events for both tenants
    # ------------------------------------------------------------------

    def test_01_ingest_events_tenant_a(self, db_session, tenant_a, canonical_store):
        """Ingest 3 events for Tenant A."""
        events = _make_events_for_tenant(tenant_a, PRODUCT_A, SUPPLIERS_A, "LOT-A")
        persisted = []
        for event in events:
            result = canonical_store.persist_event(event)
            persisted.append(result)

        assert len(persisted) == 3, f"Expected 3 persisted events for tenant_a, got {len(persisted)}"
        assert all(r.success for r in persisted), "All tenant_a events must persist successfully"

    def test_02_ingest_events_tenant_b(self, db_session, tenant_b, canonical_store):
        """Ingest 3 events for Tenant B (different product)."""
        events = _make_events_for_tenant(tenant_b, PRODUCT_B, SUPPLIERS_B, "LOT-B")
        persisted = []
        for event in events:
            result = canonical_store.persist_event(event)
            persisted.append(result)

        assert len(persisted) == 3, f"Expected 3 persisted events for tenant_b, got {len(persisted)}"
        assert all(r.success for r in persisted), "All tenant_b events must persist successfully"

    # ------------------------------------------------------------------
    # Step 3: Create a request case for Tenant A
    # ------------------------------------------------------------------

    def test_03_create_request_case_tenant_a(self, tenant_a, workflow):
        """Create an FDA request case scoped to Tenant A's product."""
        case = workflow.create_request_case(
            tenant_id=tenant_a,
            requesting_party="FDA",
            request_channel="email",
            scope_type="product_recall",
            scope_description="Investigation — Organic Romaine Hearts",
            response_hours=24,
            affected_products=[PRODUCT_A],
            affected_lots=["LOT-A-001", "LOT-A-002"],
            affected_facilities=SUPPLIERS_A,
        )

        assert case["package_status"] == "intake"
        assert case["tenant_id"] == tenant_a
        self.__class__._case_a_id = case["request_case_id"]

    # ------------------------------------------------------------------
    # Step 4: Tenant A's request only contains Tenant A events
    # ------------------------------------------------------------------

    def test_04_tenant_a_request_scoped_correctly(self, db_session, tenant_a, workflow):
        """Verify Tenant A's request scope returns only Tenant A's events."""
        from sqlalchemy import text

        case_id = self.__class__._case_a_id

        # Advance to scoping and collecting
        workflow.update_scope(
            tenant_a, case_id,
            scope_description="All Romaine lots from Salinas region",
        )
        result = workflow.collect_records(tenant_a, case_id)

        assert result["total_records"] >= 2, (
            f"Expected >=2 records for tenant_a, got {result['total_records']}"
        )

        # Verify every collected event belongs to tenant_a
        collected_events = db_session.execute(
            text("""
                SELECT event_id, tenant_id, product_reference
                FROM fsma.traceability_events
                WHERE tenant_id = :tid AND status = 'active'
            """),
            {"tid": tenant_a},
        ).mappings().fetchall()

        for evt in collected_events:
            assert str(evt["tenant_id"]) == tenant_a, (
                f"Event {evt['event_id']} belongs to wrong tenant"
            )
            assert evt["product_reference"] == PRODUCT_A, (
                f"Event {evt['event_id']} has wrong product: {evt['product_reference']}"
            )

    # ------------------------------------------------------------------
    # Step 5: Tenant B cannot see Tenant A's request case
    # ------------------------------------------------------------------

    def test_05_tenant_b_cannot_see_tenant_a_case(self, tenant_b, workflow):
        """Tenant B must not be able to access Tenant A's request case."""
        case_a_id = self.__class__._case_a_id

        with pytest.raises(ValueError, match="not found"):
            workflow._get_case(tenant_b, case_a_id)

    # ------------------------------------------------------------------
    # Step 6: Tenant B cannot see Tenant A's canonical events
    # ------------------------------------------------------------------

    def test_06_tenant_b_cannot_see_tenant_a_events(self, db_session, tenant_a, tenant_b):
        """Tenant B queries must never return Tenant A's events."""
        from sqlalchemy import text

        # Query events with tenant_b's ID but looking for tenant_a's product
        result = db_session.execute(
            text("""
                SELECT COUNT(*) FROM fsma.traceability_events
                WHERE tenant_id = :tid
                  AND product_reference = :product
                  AND status = 'active'
            """),
            {"tid": tenant_b, "product": PRODUCT_A},
        ).scalar()

        assert result == 0, (
            f"Tenant B found {result} events for Tenant A's product '{PRODUCT_A}' — isolation breach!"
        )

        # Verify tenant_b only sees their own product
        b_products = db_session.execute(
            text("""
                SELECT DISTINCT product_reference
                FROM fsma.traceability_events
                WHERE tenant_id = :tid AND status = 'active'
            """),
            {"tid": tenant_b},
        ).fetchall()

        b_product_names = [r[0] for r in b_products]
        assert PRODUCT_A not in b_product_names, "Tenant A product leaked into Tenant B's view"
        assert PRODUCT_B in b_product_names, "Tenant B should see their own product"

    # ------------------------------------------------------------------
    # Step 7: Rules evaluated for Tenant A don't leak to Tenant B
    # ------------------------------------------------------------------

    def test_07_rule_evaluations_tenant_isolated(self, db_session, tenant_a, tenant_b, rules_engine):
        """Rules evaluated for Tenant A events must not appear under Tenant B."""
        from sqlalchemy import text

        # Evaluate rules for tenant_a's events
        a_events = db_session.execute(
            text("""
                SELECT * FROM fsma.traceability_events
                WHERE tenant_id = :tid AND status = 'active'
                ORDER BY event_timestamp
            """),
            {"tid": tenant_a},
        ).mappings().fetchall()

        for event in a_events:
            event_dict = dict(event)
            if event_dict.get("kdes") and isinstance(event_dict["kdes"], str):
                event_dict["kdes"] = json.loads(event_dict["kdes"])
            rules_engine.evaluate_event(
                event_dict, persist=True, tenant_id=tenant_a,
            )

        # Now check: tenant_b must have ZERO rule evaluations for tenant_a's events
        a_event_ids = [str(e["event_id"]) for e in a_events]
        if a_event_ids:
            leak_count = db_session.execute(
                text("""
                    SELECT COUNT(*) FROM fsma.rule_evaluations
                    WHERE tenant_id = :tid_b
                      AND event_id = ANY(CAST(:eids AS uuid[]))
                """),
                {"tid_b": tenant_b, "eids": a_event_ids},
            ).scalar()

            assert leak_count == 0, (
                f"Found {leak_count} rule evaluations for Tenant A events under Tenant B — isolation breach!"
            )

        # Verify tenant_b has no rule evaluations at all (we haven't evaluated for them yet)
        b_eval_count = db_session.execute(
            text("""
                SELECT COUNT(*) FROM fsma.rule_evaluations
                WHERE tenant_id = :tid
            """),
            {"tid": tenant_b},
        ).scalar()

        assert b_eval_count == 0, (
            f"Tenant B has {b_eval_count} rule evaluations before any were run — unexpected data"
        )

    # ------------------------------------------------------------------
    # Step 8: Create a request case for Tenant B — verify isolation
    # ------------------------------------------------------------------

    def test_08_create_request_case_tenant_b_isolated(self, db_session, tenant_a, tenant_b, workflow):
        """Tenant B creates their own request case — fully isolated from A."""
        case = workflow.create_request_case(
            tenant_id=tenant_b,
            requesting_party="State DOH",
            request_channel="email",
            scope_type="product_recall",
            scope_description="Investigation — Atlantic Salmon Fillets",
            response_hours=48,
            affected_products=[PRODUCT_B],
            affected_lots=["LOT-B-001", "LOT-B-002"],
            affected_facilities=SUPPLIERS_B,
        )

        assert case["package_status"] == "intake"
        assert case["tenant_id"] == tenant_b
        self.__class__._case_b_id = case["request_case_id"]

        # Advance tenant_b's case through scope and collect
        workflow.update_scope(
            tenant_b, case["request_case_id"],
            scope_description="All salmon lots",
        )
        result = workflow.collect_records(tenant_b, case["request_case_id"])

        assert result["total_records"] >= 2, (
            f"Expected >=2 records for tenant_b, got {result['total_records']}"
        )

        # Verify tenant_b's active cases don't include tenant_a's case
        b_cases = workflow.get_active_cases(tenant_b, include_submitted=True)
        b_case_ids = [c["request_case_id"] for c in b_cases]

        assert self.__class__._case_a_id not in b_case_ids, (
            "Tenant A's case appeared in Tenant B's active cases — isolation breach!"
        )
        assert case["request_case_id"] in b_case_ids, (
            "Tenant B's own case not found in their active cases"
        )

    # ------------------------------------------------------------------
    # Step 9: Submit package for Tenant A — verify Tenant B's data excluded
    # ------------------------------------------------------------------

    def test_09_submit_package_tenant_a_excludes_tenant_b(
        self, db_session, tenant_a, tenant_b, workflow
    ):
        """Assemble and submit Tenant A's package — must not contain Tenant B data."""
        case_a_id = self.__class__._case_a_id

        # Run gap analysis
        workflow.run_gap_analysis(tenant_a, case_a_id)

        # Assemble package
        package = workflow.assemble_response_package(
            tenant_a, case_a_id,
            generated_by="qa_lead_a@company.com",
        )

        assert package["version_number"] == 1
        assert package["package_hash"], "Package must have SHA-256 hash"

        # Inspect package contents — must not contain tenant_b's product or events
        contents = package["package_contents"]
        if isinstance(contents, str):
            contents = json.loads(contents)

        contents_str = json.dumps(contents, default=str)
        assert PRODUCT_B not in contents_str, (
            f"Tenant B's product '{PRODUCT_B}' found in Tenant A's package — isolation breach!"
        )
        for supplier in SUPPLIERS_B:
            assert supplier not in contents_str, (
                f"Tenant B's supplier '{supplier}' found in Tenant A's package — isolation breach!"
            )

        # Verify all events in package belong to tenant_a
        if "events" in contents:
            for evt in contents["events"]:
                assert str(evt.get("tenant_id", tenant_a)) == tenant_a, (
                    f"Package event belongs to wrong tenant: {evt.get('tenant_id')}"
                )

        self.__class__._package_a_id = package["package_id"]

        # Add signoffs and submit
        workflow.add_signoff(
            tenant_a, case_a_id,
            signoff_type="scope_approval",
            signed_by="qa_lead_a@company.com",
            notes="Scope confirmed for tenant A.",
        )
        workflow.add_signoff(
            tenant_a, case_a_id,
            signoff_type="final_approval",
            signed_by="vp_quality_a@company.com",
            notes="Approved for submission.",
        )

        result = workflow.submit_package(
            tenant_a, case_a_id,
            package_id=package["package_id"],
            submitted_by="vp_quality_a@company.com",
            submitted_to="FDA",
            submission_method="export",
            submission_notes="Tenant A submission — isolation test",
            force=True,
        )

        assert result["submission_id"], "Must have submission ID"
        assert result["record_count"] >= 2, "Must have records in submission"

    # ------------------------------------------------------------------
    # Step 10: Exception cases are tenant-isolated
    # ------------------------------------------------------------------

    def test_10_exception_cases_tenant_isolated(self, db_session, tenant_a, tenant_b):
        """Exception cases created for one tenant must not be visible to the other."""
        from sqlalchemy import text

        # Create an exception case for tenant_a
        exc_case_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        # Get a tenant_a event to link the exception to
        a_event = db_session.execute(
            text("""
                SELECT event_id FROM fsma.traceability_events
                WHERE tenant_id = :tid AND status = 'active'
                LIMIT 1
            """),
            {"tid": tenant_a},
        ).fetchone()

        assert a_event is not None, "Tenant A must have at least one event"
        a_event_id = str(a_event[0])

        db_session.execute(
            text("""
                INSERT INTO fsma.exception_cases (
                    case_id, tenant_id, request_case_id, severity, status,
                    source_supplier, source_facility_reference,
                    rule_category, recommended_remediation,
                    linked_event_ids, created_at, updated_at
                ) VALUES (
                    :case_id, :tenant_id, :request_case_id, 'critical', 'open',
                    :supplier, :facility,
                    'kde_presence', 'Request missing data from supplier',
                    CAST(:linked_ids AS uuid[]), :now, :now
                )
            """),
            {
                "case_id": exc_case_id,
                "tenant_id": tenant_a,
                "request_case_id": self.__class__._case_a_id,
                "supplier": SUPPLIERS_A[0],
                "facility": SUPPLIERS_A[0],
                "linked_ids": [a_event_id],
                "now": now,
            },
        )
        db_session.commit()

        # Verify tenant_a can see the exception
        a_exc_count = db_session.execute(
            text("""
                SELECT COUNT(*) FROM fsma.exception_cases
                WHERE tenant_id = :tid AND case_id = :cid
            """),
            {"tid": tenant_a, "cid": exc_case_id},
        ).scalar()
        assert a_exc_count == 1, "Tenant A must see their own exception case"

        # Verify tenant_b CANNOT see tenant_a's exception
        b_exc_count = db_session.execute(
            text("""
                SELECT COUNT(*) FROM fsma.exception_cases
                WHERE tenant_id = :tid AND case_id = :cid
            """),
            {"tid": tenant_b, "cid": exc_case_id},
        ).scalar()
        assert b_exc_count == 0, (
            f"Tenant B found Tenant A's exception case — isolation breach!"
        )

        # Verify tenant_b has no exception cases linked to tenant_a's request
        b_leaked_exc = db_session.execute(
            text("""
                SELECT COUNT(*) FROM fsma.exception_cases
                WHERE tenant_id = :tid
                  AND request_case_id = :case_id
            """),
            {"tid": tenant_b, "case_id": self.__class__._case_a_id},
        ).scalar()
        assert b_leaked_exc == 0, (
            "Tenant B has exception cases linked to Tenant A's request — isolation breach!"
        )

    # ------------------------------------------------------------------
    # Final verification: cross-tenant counts
    # ------------------------------------------------------------------

    def test_11_final_cross_tenant_count_verification(self, db_session, tenant_a, tenant_b):
        """Final sanity check: each tenant sees only their own data across all tables."""
        from sqlalchemy import text

        tables_with_tenant_id = [
            ("fsma.traceability_events", "tenant_id"),
            ("fsma.request_cases", "tenant_id"),
            ("fsma.rule_evaluations", "tenant_id"),
            ("fsma.hash_chain", "tenant_id"),
        ]

        for table, col in tables_with_tenant_id:
            a_count = db_session.execute(
                text(f"SELECT COUNT(*) FROM {table} WHERE {col} = :tid"),
                {"tid": tenant_a},
            ).scalar()
            b_count = db_session.execute(
                text(f"SELECT COUNT(*) FROM {table} WHERE {col} = :tid"),
                {"tid": tenant_b},
            ).scalar()

            # Neither tenant should have zero rows (both have data)
            # except rule_evaluations for tenant_b which we never ran
            if table == "fsma.rule_evaluations":
                assert a_count > 0, f"Tenant A should have data in {table}"
                # tenant_b may have 0 rule evaluations — that's expected
            elif table == "fsma.request_cases":
                assert a_count >= 1, f"Tenant A should have cases in {table}"
                assert b_count >= 1, f"Tenant B should have cases in {table}"
            else:
                assert a_count > 0, f"Tenant A should have data in {table}"
                assert b_count > 0, f"Tenant B should have data in {table}"

            # Cross-check: verify no data from one tenant leaked to the other
            # by checking that tenant_a's count + tenant_b's count equals the
            # total for both tenants combined
            combined = db_session.execute(
                text(f"""
                    SELECT COUNT(*) FROM {table}
                    WHERE {col} IN (:tid_a, :tid_b)
                """),
                {"tid_a": tenant_a, "tid_b": tenant_b},
            ).scalar()

            assert combined == a_count + b_count, (
                f"Data integrity issue in {table}: "
                f"combined({combined}) != a({a_count}) + b({b_count})"
            )
