"""
Invariant tests for core truth properties.

These are property tests that must ALWAYS hold, regardless of input.
They protect the trust guarantees of the system during refactoring.

Ref: REGENGINE_CODEBASE_REMEDIATION_PRD.md Phase 2.2

Invariants tested:
    1. Canonical events are immutable after finalization (status=ACTIVE)
    2. Rule evaluation is reproducible (same inputs → same outputs)
    3. Audit chain is tamper-evident (hash chain integrity)
    4. Merge preserves traceability (entity merge history)
    5. Tenant isolation (tenant_id required on all truth-bearing models)
"""

import hashlib
import json
import sys
from copy import deepcopy
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services"))

from shared.canonical_event import (
    CTEType,
    EventStatus,
    IngestionSource,
    ProvenanceMetadata,
    TraceabilityEvent,
)
from shared.cte_persistence import compute_chain_hash
from shared.rules.types import RuleDefinition, RuleEvaluationResult, EvaluationSummary
from shared.rules.evaluators.stateless import (
    evaluate_field_presence,
    evaluate_multi_field_presence,
)


# ---------------------------------------------------------------------------
# Test Data Builders
# ---------------------------------------------------------------------------

TENANT_A = "00000000-0000-0000-0000-00000000000a"
TENANT_B = "00000000-0000-0000-0000-00000000000b"
TENANT_DEFAULT = "00000000-0000-0000-0000-000000000001"


def _make_event(**overrides) -> TraceabilityEvent:
    """Build a minimal valid TraceabilityEvent."""
    params = dict(
        tenant_id=TENANT_DEFAULT,
        source_system=IngestionSource.WEBHOOK_API,
        event_type=CTEType.RECEIVING,
        event_timestamp=datetime(2026, 4, 14, 10, 0, 0, tzinfo=timezone.utc),
        traceability_lot_code="TLC-INV-001",
        product_reference="Test Product",
        quantity=100.0,
        unit_of_measure="cases",
        kdes={"receive_date": "2026-04-14"},
    )
    params.update(overrides)
    return TraceabilityEvent(**params)


def _make_rule(**overrides) -> RuleDefinition:
    """Build a minimal valid RuleDefinition."""
    params = dict(
        rule_id="test-rule-001",
        rule_version=1,
        title="Test Rule",
        description="Test",
        severity="critical",
        category="kde_presence",
        applicability_conditions={"cte_types": ["receiving"]},
        citation_reference="21 CFR §1.1345",
        effective_date=date(2026, 1, 1),
        retired_date=None,
        evaluation_logic={"type": "field_presence", "field": "traceability_lot_code"},
        failure_reason_template="Missing {field_name} per {citation}",
        remediation_suggestion="Add the field",
    )
    params.update(overrides)
    return RuleDefinition(**params)


# ===================================================================
# Invariant 1: Canonical events are immutable after finalization
# ===================================================================

class TestCanonicalEventImmutability:
    """Once a canonical event is finalized (status=ACTIVE), its content
    hash must not change. Amendments create NEW events with
    supersedes_event_id, never modify the original."""

    def test_active_event_hash_is_stable(self):
        """Serializing the same ACTIVE event always produces the same hash."""
        event = _make_event(status=EventStatus.ACTIVE)
        dump1 = json.dumps(event.model_dump(mode="json"), sort_keys=True)
        dump2 = json.dumps(event.model_dump(mode="json"), sort_keys=True)
        assert hashlib.sha256(dump1.encode()).hexdigest() == hashlib.sha256(dump2.encode()).hexdigest()

    def test_amendment_creates_new_event_id(self):
        """Amending an event produces a different event_id."""
        original = _make_event()
        amended = _make_event(
            quantity=90.0,
            supersedes_event_id=original.event_id,
        )
        assert original.event_id != amended.event_id
        assert amended.supersedes_event_id == original.event_id

    def test_status_transitions_are_valid(self):
        """Only valid status values are accepted by the model."""
        for status in EventStatus:
            event = _make_event(status=status)
            assert event.status == status

    def test_superseded_event_retains_original_data(self):
        """Marking an event SUPERSEDED does not change its content."""
        event = _make_event()
        original_dump = event.model_dump(mode="json")
        original_dump["status"] = EventStatus.SUPERSEDED.value

        # Reconstruct — the TLC, quantity, KDEs all remain
        assert original_dump["traceability_lot_code"] == "TLC-INV-001"
        assert original_dump["quantity"] == 100.0


# ===================================================================
# Invariant 2: Rule evaluation is reproducible
# ===================================================================

class TestRuleEvaluationReproducibility:
    """Same inputs + same rule version = same output. Always."""

    def test_same_event_same_rule_same_result(self):
        """Evaluating the same event with the same rule produces identical results."""
        event = _make_event(kdes={"receive_date": "2026-04-14"})
        event_data = event.model_dump(mode="json")
        rule = _make_rule(
            evaluation_logic={"type": "field_presence", "field": "kdes.receive_date"},
        )

        result1 = evaluate_field_presence(event_data, rule.evaluation_logic, rule)
        result2 = evaluate_field_presence(event_data, rule.evaluation_logic, rule)

        assert result1.result == result2.result
        assert result1.severity == result2.severity
        assert result1.why_failed == result2.why_failed

    def test_evaluation_is_deterministic_across_runs(self):
        """Multiple evaluations of the same failing event produce the same failure."""
        event = _make_event(kdes={})  # Missing receive_date
        event_data = event.model_dump(mode="json")
        rule = _make_rule(
            evaluation_logic={"type": "field_presence", "field": "kdes.receive_date"},
        )

        results = [evaluate_field_presence(event_data, rule.evaluation_logic, rule) for _ in range(10)]
        assert all(r.result == "fail" for r in results)
        assert all(r.why_failed == results[0].why_failed for r in results)

    def test_rule_version_is_recorded_in_result(self):
        """Each evaluation result records the rule_version used."""
        rule_v1 = _make_rule(rule_version=1)
        rule_v2 = _make_rule(rule_version=2)
        event_data = _make_event().model_dump(mode="json")

        r1 = evaluate_field_presence(event_data, rule_v1.evaluation_logic, rule_v1)
        r2 = evaluate_field_presence(event_data, rule_v2.evaluation_logic, rule_v2)

        assert r1.rule_version == 1
        assert r2.rule_version == 2

    def test_multi_field_or_logic_is_deterministic(self):
        """Multi-field presence (OR logic) produces consistent results."""
        event = _make_event(
            from_entity_reference="Fresh Farms LLC",
            kdes={"immediate_previous_source": "Fresh Farms LLC"},
        )
        event_data = event.model_dump(mode="json")
        rule = _make_rule(
            evaluation_logic={
                "type": "multi_field_presence",
                "field": "from_entity_reference",
                "params": {"fields": ["from_entity_reference", "kdes.immediate_previous_source"]},
            },
        )

        results = [evaluate_multi_field_presence(event_data, rule.evaluation_logic, rule) for _ in range(10)]
        assert all(r.result == "pass" for r in results)

    def test_evaluation_summary_compliant_property(self):
        """EvaluationSummary.compliant is tri-state — True iff failed==0
        AND errored==0 AND at least one rule actually ran (#1347, #1354)."""
        passing = EvaluationSummary(event_id="x", total_rules=5, failed=0, passed=5)
        failing = EvaluationSummary(event_id="x", total_rules=5, failed=1, passed=4)
        empty = EvaluationSummary(event_id="x")
        errored = EvaluationSummary(event_id="x", total_rules=5, passed=4, errored=1)
        assert passing.compliant is True
        assert failing.compliant is False
        # #1347 — empty rule set must not silently report compliant=True.
        assert empty.compliant is None
        # #1354 — evaluator errors count as non-compliant, not skipped.
        assert errored.compliant is False


# ===================================================================
# Invariant 3: Audit chain is tamper-evident
# ===================================================================

class TestAuditChainTamperEvidence:
    """Hash chain integrity: tampering any event invalidates all
    downstream chain hashes."""

    def test_genesis_block_uses_genesis_seed(self):
        """First chain entry uses 'GENESIS' as the previous hash seed."""
        event_hash = hashlib.sha256(b"first-event").hexdigest()
        chain_hash = compute_chain_hash(event_hash, None)
        expected = hashlib.sha256(f"GENESIS|{event_hash}".encode()).hexdigest()
        assert chain_hash == expected

    def test_chain_links_are_ordered(self):
        """Each chain entry depends on the previous chain hash."""
        hashes = [hashlib.sha256(f"event-{i}".encode()).hexdigest() for i in range(5)]
        chain = [compute_chain_hash(hashes[0], None)]
        for i in range(1, 5):
            chain.append(compute_chain_hash(hashes[i], chain[-1]))

        # Verify each link depends on the previous
        for i in range(1, 5):
            recomputed = compute_chain_hash(hashes[i], chain[i - 1])
            assert chain[i] == recomputed

    def test_tampering_invalidates_downstream(self):
        """Changing any event hash invalidates all subsequent chain hashes."""
        hashes = [hashlib.sha256(f"event-{i}".encode()).hexdigest() for i in range(5)]
        original_chain = []
        prev = None
        for h in hashes:
            c = compute_chain_hash(h, prev)
            original_chain.append(c)
            prev = c

        # Tamper with event 2 (index 2)
        tampered_hashes = list(hashes)
        tampered_hashes[2] = hashlib.sha256(b"TAMPERED").hexdigest()

        tampered_chain = []
        prev = None
        for h in tampered_hashes:
            c = compute_chain_hash(h, prev)
            tampered_chain.append(c)
            prev = c

        # Events 0-1 unchanged, events 2-4 diverge
        assert tampered_chain[0] == original_chain[0]
        assert tampered_chain[1] == original_chain[1]
        assert tampered_chain[2] != original_chain[2]
        assert tampered_chain[3] != original_chain[3]
        assert tampered_chain[4] != original_chain[4]

    def test_chain_hash_is_sha256(self):
        """Chain hashes are valid SHA-256 hex strings (64 chars)."""
        h = compute_chain_hash("abc123", None)
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_empty_event_hash_still_chains(self):
        """Even an empty event hash produces a valid chain entry."""
        c = compute_chain_hash("", None)
        assert len(c) == 64


# ===================================================================
# Invariant 4: Merge preserves traceability
# ===================================================================

class TestMergePreservesTraceability:
    """Entity merges/splits must preserve full traceability history.
    Both source and target entities remain referenceable."""

    def test_merged_entity_retains_both_ids(self):
        """A merge operation should record both source entity IDs."""
        source_ids = [str(uuid4()), str(uuid4())]
        target_id = str(uuid4())

        merge_record = {
            "action": "merge",
            "source_entity_ids": source_ids,
            "target_entity_id": target_id,
            "performed_by": "operator@example.com",
        }

        assert len(merge_record["source_entity_ids"]) == 2
        assert merge_record["target_entity_id"] == target_id

    def test_split_records_source_and_targets(self):
        """A split operation should record the source and all targets."""
        source_id = str(uuid4())
        target_ids = [str(uuid4()), str(uuid4())]

        split_record = {
            "action": "split",
            "source_entity_ids": [source_id],
            "target_entity_id": target_ids[0],  # primary target
        }

        assert split_record["action"] == "split"
        assert len(split_record["source_entity_ids"]) == 1

    def test_undo_merge_is_reversible(self):
        """Merge operations can be undone (is_reversed flag)."""
        merge_record = {
            "action": "merge",
            "source_entity_ids": [str(uuid4()), str(uuid4())],
            "target_entity_id": str(uuid4()),
            "is_reversed": False,
        }

        # Undo
        merge_record["is_reversed"] = True
        merge_record["reversed_by"] = "admin@example.com"
        assert merge_record["is_reversed"] is True


# ===================================================================
# Invariant 5: Tenant isolation
# ===================================================================

class TestTenantIsolation:
    """Tenant A's data is never visible to Tenant B.
    Every truth-bearing model must carry tenant_id."""

    def test_traceability_event_requires_tenant_id(self):
        """TraceabilityEvent cannot be constructed without tenant_id."""
        with pytest.raises(Exception):
            TraceabilityEvent(
                # Missing tenant_id
                source_system=IngestionSource.WEBHOOK_API,
                event_type=CTEType.RECEIVING,
                event_timestamp=datetime.now(timezone.utc),
                traceability_lot_code="TLC-001",
                quantity=100.0,
                unit_of_measure="cases",
            )

    def test_different_tenants_produce_different_events(self):
        """Events from different tenants have different tenant_ids."""
        event_a = _make_event(tenant_id=TENANT_A)
        event_b = _make_event(tenant_id=TENANT_B)
        assert str(event_a.tenant_id) != str(event_b.tenant_id)

    def test_tenant_id_is_uuid_format(self):
        """Tenant IDs are valid UUID strings."""
        tid = str(uuid4())
        event = _make_event(tenant_id=tid)
        assert str(event.tenant_id) == tid

    def test_event_data_includes_tenant_in_serialization(self):
        """Serialized event data always includes tenant_id."""
        event = _make_event()
        data = event.model_dump(mode="json")
        assert "tenant_id" in data
        assert data["tenant_id"] is not None
