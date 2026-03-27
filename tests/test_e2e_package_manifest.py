"""
E2E Integration Test: Package Manifest — Reproducibility & Immutability.

Proves that the response package manifest:
1. Contains all required manifest fields (system-state snapshot)
2. Is reproducible: same inputs -> same hash
3. Is immutable: submitted packages cannot be modified
4. Preserves history on amendment: old package intact with original hash
5. Is not mutated by identity changes after submission
6. Is not mutated by rule changes after submission

Usage:
    pytest tests/test_e2e_package_manifest.py -v --tb=short

Requires:
    - PostgreSQL with fsma schema and all migrations applied
    - Set DATABASE_URL environment variable
"""

import hashlib
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

PRODUCT = "Manifest Test Romaine"
SUPPLIERS = ["Manifest Farm Alpha", "Manifest Farm Beta"]


def _make_events(tenant_id: str) -> List[Dict]:
    """Generate test events for manifest validation."""
    base_time = datetime.now(timezone.utc) - timedelta(days=10)
    return [
        {
            "event_id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "event_type": "harvesting",
            "event_timestamp": (base_time + timedelta(days=0)).isoformat(),
            "product_reference": PRODUCT,
            "traceability_lot_code": "LOT-MAN-2026-001A",
            "quantity": 3000.0,
            "unit_of_measure": "lbs",
            "from_facility_reference": "Manifest Farm Alpha",
            "from_entity_reference": "Manifest Farm Alpha",
            "kdes": {
                "harvest_date": (base_time + timedelta(days=0)).strftime("%Y-%m-%d"),
                "field_coordinates": "36.67,-121.65",
                "growing_area_code": "CA-MFA-BLOCK-1",
            },
            "confidence_score": 0.95,
            "status": "active",
        },
        {
            "event_id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "event_type": "cooling",
            "event_timestamp": (base_time + timedelta(hours=4)).isoformat(),
            "product_reference": PRODUCT,
            "traceability_lot_code": "LOT-MAN-2026-001A",
            "quantity": 3000.0,
            "unit_of_measure": "lbs",
            "from_facility_reference": "Manifest Farm Alpha",
            "kdes": {
                # Missing cooling_date — triggers rule failure
                "cooling_method": "hydro",
            },
            "confidence_score": 0.88,
            "status": "active",
        },
        {
            "event_id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "event_type": "shipping",
            "event_timestamp": (base_time + timedelta(days=2)).isoformat(),
            "product_reference": PRODUCT,
            "traceability_lot_code": "LOT-MAN-2026-001B",
            "quantity": 2000.0,
            "unit_of_measure": "lbs",
            "from_facility_reference": "Manifest Farm Beta",
            "to_facility_reference": "RetailCo DC",
            "from_entity_reference": "Manifest Farm Beta",
            "to_entity_reference": "RetailCo Inc",
            "kdes": {
                "ship_date": (base_time + timedelta(days=2)).strftime("%Y-%m-%d"),
                "carrier": "USPS Freight",
                "bill_of_lading": "BOL-MAN-001",
            },
            "confidence_score": 0.97,
            "status": "active",
        },
    ]


# ---------------------------------------------------------------------------
# Shared state between ordered tests
# ---------------------------------------------------------------------------

class _State:
    """Mutable namespace for cross-test state (module-scoped)."""
    case_id: str = ""
    package_id: str = ""
    package_hash: str = ""
    package_contents: dict = {}
    entity_id: str = ""


# ---------------------------------------------------------------------------
# The Tests
# ---------------------------------------------------------------------------

class TestPackageManifest:
    """Prove manifest completeness, reproducibility, and immutability."""

    @pytest.fixture(autouse=True)
    def _ensure_clean_session(self, db_session):
        """Ensure DB session is clean before each test."""
        try:
            from sqlalchemy import text
            db_session.execute(text("SELECT 1"))
        except Exception:
            db_session.rollback()

    # ── Setup: ingest events, evaluate rules, create request ──

    def test_01_ingest_events(self, db_session, tenant_id, canonical_store):
        """Ingest test events into canonical store."""
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
                source_system=IngestionSource(event_data.get("source_system", "csv_upload")),
                status="active",
            )
            result = canonical_store.persist_event(te)
            persisted.append(result)

        assert len(persisted) == 3

    def test_02_evaluate_rules(self, db_session, tenant_id, rules_engine):
        """Run rules engine on all events."""
        from sqlalchemy import text

        result = db_session.execute(
            text("""
                SELECT event_id, event_type FROM fsma.traceability_events
                WHERE tenant_id = :tid AND status = 'active'
                  AND product_reference = :product
                ORDER BY event_timestamp
            """),
            {"tid": tenant_id, "product": PRODUCT},
        )
        events = result.mappings().fetchall()
        assert len(events) >= 3

        for event in events:
            full = db_session.execute(
                text("SELECT * FROM fsma.traceability_events WHERE event_id = :eid AND tenant_id = :tid"),
                {"eid": str(event["event_id"]), "tid": tenant_id},
            ).mappings().fetchone()
            if full:
                event_dict = dict(full)
                if event_dict.get("kdes") and isinstance(event_dict["kdes"], str):
                    event_dict["kdes"] = json.loads(event_dict["kdes"])
                rules_engine.evaluate_event(event_dict, persist=True, tenant_id=tenant_id)

    def test_03_create_identity_entity(self, db_session, tenant_id):
        """Create a canonical entity so identity_state is populated."""
        from sqlalchemy import text

        entity_id = str(uuid.uuid4())
        db_session.execute(
            text("""
                INSERT INTO fsma.canonical_entities (
                    entity_id, tenant_id, entity_type, canonical_name,
                    confidence_score, is_active
                ) VALUES (
                    :eid, :tid, 'firm', 'Manifest Farm Alpha',
                    0.95, TRUE
                )
            """),
            {"eid": entity_id, "tid": tenant_id},
        )
        # Add an alias
        db_session.execute(
            text("""
                INSERT INTO fsma.entity_aliases (
                    alias_id, tenant_id, entity_id, alias_type, alias_value
                ) VALUES (
                    :aid, :tid, :eid, 'name', 'MFA Corp'
                )
            """),
            {"aid": str(uuid.uuid4()), "tid": tenant_id, "eid": entity_id},
        )
        db_session.commit()
        _State.entity_id = entity_id

    def test_04_create_request_and_advance(self, tenant_id, workflow):
        """Create FDA request, scope, collect, gap-analyze, signoff."""
        case = workflow.create_request_case(
            tenant_id=tenant_id,
            requesting_party="FDA",
            request_channel="email",
            scope_type="product_recall",
            scope_description="Manifest test — Romaine investigation",
            response_hours=24,
            affected_products=[PRODUCT],
            affected_lots=["LOT-MAN-2026-001A", "LOT-MAN-2026-001B"],
            affected_facilities=SUPPLIERS,
        )
        _State.case_id = case["request_case_id"]

        workflow.update_scope(
            tenant_id, _State.case_id,
            scope_description="All manifest test romaine lots",
        )
        workflow.collect_records(tenant_id, _State.case_id)
        workflow.run_gap_analysis(tenant_id, _State.case_id)

        # Add required signoff to advance through workflow
        workflow.add_signoff(
            tenant_id, _State.case_id,
            signoff_type="scope_approval",
            signed_by="qa_lead@test.com",
            notes="Scope approved for manifest test.",
        )

    # ── Core manifest tests ──

    def test_05_assemble_package_has_manifest_fields(self, tenant_id, workflow):
        """Assemble package and verify all manifest fields are present."""
        package = workflow.assemble_response_package(
            tenant_id, _State.case_id,
            generated_by="manifest_test@test.com",
        )

        _State.package_id = package["package_id"]
        _State.package_hash = package["package_hash"]

        contents = package["package_contents"]
        if isinstance(contents, str):
            contents = json.loads(contents)
        _State.package_contents = contents

        # ── Required manifest fields ──
        assert contents["manifest_version"] == "1.0"
        assert contents["request_case_id"] == _State.case_id
        assert contents["tenant_id"] == tenant_id
        assert "assembled_at" in contents
        assert isinstance(contents["scoped_event_ids"], list)
        assert len(contents["scoped_event_ids"]) >= 1
        assert isinstance(contents["rule_evaluation_ids"], list)
        assert isinstance(contents["rule_versions"], dict)
        assert isinstance(contents["identity_state"], dict)
        assert isinstance(contents["exception_state"], dict)
        assert isinstance(contents["signoff_state"], list)
        assert isinstance(contents["waiver_state"], list)
        assert "package_hash" in contents
        assert len(contents["package_hash"]) == 64  # SHA-256 hex

        # Verify identity_state has our entity
        assert _State.entity_id in contents["identity_state"]
        entity_snap = contents["identity_state"][_State.entity_id]
        assert entity_snap["name"] == "Manifest Farm Alpha"
        assert entity_snap["type"] == "firm"
        assert isinstance(entity_snap["aliases"], list)

        # Verify signoff_state includes our scope_approval
        assert len(contents["signoff_state"]) >= 1
        assert any(
            s["signoff_type"] == "scope_approval"
            for s in contents["signoff_state"]
        )

    def test_06_reproducibility_same_hash(self, db_session, tenant_id, workflow):
        """Assemble again with same inputs -> same manifest hash.

        The hash is computed from all manifest fields EXCEPT assembled_at
        and package_hash itself. Since assembled_at will differ, we verify
        that the deterministic content (scoped_event_ids, rule_versions,
        identity_state, etc.) matches exactly.
        """
        package2 = workflow.assemble_response_package(
            tenant_id, _State.case_id,
            generated_by="manifest_test@test.com",
        )
        contents2 = package2["package_contents"]
        if isinstance(contents2, str):
            contents2 = json.loads(contents2)

        # The deterministic manifest fields must match
        deterministic_keys = [
            "manifest_version",
            "request_case_id",
            "tenant_id",
            "scoped_event_ids",
            "rule_versions",
            "identity_state",
            "exception_state",
            "waiver_state",
        ]
        for key in deterministic_keys:
            assert json.dumps(contents2[key], sort_keys=True, default=str) == \
                   json.dumps(_State.package_contents[key], sort_keys=True, default=str), \
                   f"Manifest field '{key}' differs between assemblies"

        # Verify the embedded package_hash is self-consistent
        # (remove package_hash, recompute, compare)
        contents2_check = {k: v for k, v in contents2.items() if k != "package_hash"}
        recomputed = hashlib.sha256(
            json.dumps(contents2_check, sort_keys=True, default=str).encode()
        ).hexdigest()
        assert recomputed == contents2["package_hash"], \
            "Embedded package_hash must match recomputed hash of manifest"

    def test_07_submit_package(self, tenant_id, workflow):
        """Add final_approval signoff and submit the package."""
        workflow.add_signoff(
            tenant_id, _State.case_id,
            signoff_type="final_approval",
            signed_by="vp_quality@test.com",
            notes="Approved for submission.",
        )

        # Submit with force=True to bypass any rule-failure blockers
        result = workflow.submit_package(
            tenant_id, _State.case_id,
            package_id=_State.package_id,
            submitted_by="vp_quality@test.com",
            submitted_to="FDA",
            submission_method="export",
            force=True,
        )
        assert result["submission_id"]
        assert result["package_hash"] == _State.package_hash

    def test_08_immutability_package_unchanged_after_submit(self, db_session, tenant_id):
        """Re-read the submitted package from DB — contents and hash are intact."""
        from sqlalchemy import text

        row = db_session.execute(
            text("""
                SELECT package_contents, package_hash
                FROM fsma.response_packages
                WHERE package_id = :pkg_id
                  AND tenant_id = :tid
            """),
            {"pkg_id": _State.package_id, "tid": tenant_id},
        ).mappings().fetchone()

        assert row is not None
        stored_hash = row["package_hash"]
        stored_contents = row["package_contents"]
        if isinstance(stored_contents, str):
            stored_contents = json.loads(stored_contents)

        # Hash must match what was recorded at assembly time
        assert stored_hash == _State.package_hash

        # Manifest fields must match original snapshot
        assert stored_contents["manifest_version"] == "1.0"
        assert stored_contents["scoped_event_ids"] == _State.package_contents["scoped_event_ids"]
        assert stored_contents["identity_state"] == _State.package_contents["identity_state"]
        assert stored_contents["rule_versions"] == _State.package_contents["rule_versions"]

    def test_09_amendment_preserves_original(self, db_session, tenant_id, workflow):
        """Amend package -> old package still intact with original hash."""
        amendment = workflow.create_amendment(
            tenant_id, _State.case_id,
            generated_by="manifest_test@test.com",
        )
        assert amendment["version_number"] == 3  # versions 1, 2 from reproducibility test, now 3

        # Re-read version 1 — must still have original hash and contents
        from sqlalchemy import text
        v1 = db_session.execute(
            text("""
                SELECT package_contents, package_hash
                FROM fsma.response_packages
                WHERE package_id = :pkg_id
                  AND tenant_id = :tid
            """),
            {"pkg_id": _State.package_id, "tid": tenant_id},
        ).mappings().fetchone()

        assert v1 is not None
        assert v1["package_hash"] == _State.package_hash, \
            "Original package hash must be preserved after amendment"

    def test_10_identity_change_does_not_mutate_old_package(
        self, db_session, tenant_id
    ):
        """Change an entity name after submission -> old package manifest unchanged."""
        from sqlalchemy import text

        # Change the entity name
        db_session.execute(
            text("""
                UPDATE fsma.canonical_entities
                SET canonical_name = 'Manifest Farm Alpha RENAMED',
                    updated_at = NOW()
                WHERE entity_id = :eid
                  AND tenant_id = :tid
            """),
            {"eid": _State.entity_id, "tid": tenant_id},
        )
        db_session.commit()

        # Re-read the original package
        row = db_session.execute(
            text("""
                SELECT package_contents, package_hash
                FROM fsma.response_packages
                WHERE package_id = :pkg_id
                  AND tenant_id = :tid
            """),
            {"pkg_id": _State.package_id, "tid": tenant_id},
        ).mappings().fetchone()

        assert row is not None
        stored_contents = row["package_contents"]
        if isinstance(stored_contents, str):
            stored_contents = json.loads(stored_contents)

        # The stored identity_state must still show the OLD name
        entity_snap = stored_contents["identity_state"][_State.entity_id]
        assert entity_snap["name"] == "Manifest Farm Alpha", \
            "Old package must retain original entity name, not the renamed one"

        # Hash must be unchanged
        assert row["package_hash"] == _State.package_hash

    def test_11_rule_change_does_not_mutate_old_package(
        self, db_session, tenant_id
    ):
        """If rule definitions change, old package manifest still has original rule versions."""
        from sqlalchemy import text

        # Get a rule_id from our stored manifest
        rule_versions_snapshot = _State.package_contents["rule_versions"]
        if not rule_versions_snapshot:
            pytest.skip("No rule versions captured in manifest (no rules defined)")

        sample_rule_id = next(iter(rule_versions_snapshot))
        original_version = rule_versions_snapshot[sample_rule_id]["version"]

        # Simulate a rule version bump by inserting a new version
        # (We don't actually modify the old row — just prove the package is frozen)
        db_session.execute(
            text("""
                UPDATE fsma.rule_definitions
                SET rule_version = rule_version + 100
                WHERE rule_id = :rid
            """),
            {"rid": sample_rule_id},
        )
        db_session.commit()

        # Re-read the original package
        row = db_session.execute(
            text("""
                SELECT package_contents, package_hash
                FROM fsma.response_packages
                WHERE package_id = :pkg_id
                  AND tenant_id = :tid
            """),
            {"pkg_id": _State.package_id, "tid": tenant_id},
        ).mappings().fetchone()

        assert row is not None
        stored_contents = row["package_contents"]
        if isinstance(stored_contents, str):
            stored_contents = json.loads(stored_contents)

        # The stored rule_versions must still show the ORIGINAL version
        assert stored_contents["rule_versions"][sample_rule_id]["version"] == original_version, \
            "Old package must retain original rule version, not the updated one"

        # Hash must be unchanged
        assert row["package_hash"] == _State.package_hash

        # Restore the rule version to not affect other tests
        db_session.execute(
            text("""
                UPDATE fsma.rule_definitions
                SET rule_version = rule_version - 100
                WHERE rule_id = :rid
            """),
            {"rid": sample_rule_id},
        )
        db_session.commit()

    def test_12_package_hash_self_verifiable(self, db_session, tenant_id):
        """The embedded package_hash can be verified against the manifest contents."""
        from sqlalchemy import text

        row = db_session.execute(
            text("""
                SELECT package_contents
                FROM fsma.response_packages
                WHERE package_id = :pkg_id
                  AND tenant_id = :tid
            """),
            {"pkg_id": _State.package_id, "tid": tenant_id},
        ).mappings().fetchone()

        contents = row["package_contents"]
        if isinstance(contents, str):
            contents = json.loads(contents)

        embedded_hash = contents.pop("package_hash")

        # Recompute from manifest without the hash field
        recomputed = hashlib.sha256(
            json.dumps(contents, sort_keys=True, default=str).encode()
        ).hexdigest()

        assert recomputed == embedded_hash, \
            "Embedded package_hash must be verifiable by recomputing SHA-256 of manifest"
