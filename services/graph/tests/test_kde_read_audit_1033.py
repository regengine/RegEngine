"""
Tests for #1033: FSMA audit trail logs read access to KDE records.

FSMA 204 / NIST AU-2 require that read operations on compliance-relevant
records are logged to the audit trail.

Verifies:
  1. FSMAAuditAction.KDE_READ enum value exists and is distinct from TRACED.
  2. Traceability endpoints call get_audit_log().log() with action=KDE_READ.
  3. The audit entry captures target_type="KDE" and the correct tenant_id.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "shared"))


class TestKDEReadActionEnum:
    """FSMAAuditAction.KDE_READ must exist and have the correct value."""

    def test_kde_read_action_exists(self):
        from services.graph.app.fsma_audit import FSMAAuditAction

        assert hasattr(FSMAAuditAction, "KDE_READ"), (
            "FSMAAuditAction.KDE_READ is missing — #1033 not patched"
        )

    def test_kde_read_value(self):
        from services.graph.app.fsma_audit import FSMAAuditAction

        assert FSMAAuditAction.KDE_READ == "KDE_READ"

    def test_kde_read_distinct_from_traced(self):
        """KDE_READ must be a separate action so it can be filtered independently."""
        from services.graph.app.fsma_audit import FSMAAuditAction

        assert FSMAAuditAction.KDE_READ != FSMAAuditAction.TRACED

    def test_kde_read_in_action_values(self):
        from services.graph.app.fsma_audit import FSMAAuditAction

        values = [a.value for a in FSMAAuditAction]
        assert "KDE_READ" in values


class TestKDEReadAuditLog:
    """Audit log records a KDE_READ entry when an FSMAAuditLog.log() call is made."""

    def test_log_kde_read_entry(self):
        """FSMAAuditLog.log() accepts KDE_READ and persists the entry."""
        from services.graph.app.fsma_audit import (
            FSMAAuditAction,
            FSMAAuditActorType,
            FSMAAuditLog,
        )

        audit = FSMAAuditLog()
        audit.log(
            action=FSMAAuditAction.KDE_READ,
            target_type="KDE",
            target_id="LOT-2024-001",
            actor="test-key",
            actor_type=FSMAAuditActorType.API,
            tenant_id="tenant-abc",
        )

        entries = audit.get_by_target("LOT-2024-001")
        assert len(entries) == 1
        entry = entries[0]
        assert entry.action == FSMAAuditAction.KDE_READ
        assert entry.target_type == "KDE"
        assert entry.tenant_id == "tenant-abc"

    def test_log_kde_read_filterable_by_action(self):
        """KDE_READ entries can be retrieved by action and are not confused with TRACED."""
        from services.graph.app.fsma_audit import (
            FSMAAuditAction,
            FSMAAuditActorType,
            FSMAAuditLog,
        )

        audit = FSMAAuditLog()
        audit.log(
            action=FSMAAuditAction.KDE_READ,
            target_type="KDE",
            target_id="LOT-A",
            actor="key-1",
            actor_type=FSMAAuditActorType.API,
            tenant_id="t1",
        )
        audit.log(
            action=FSMAAuditAction.TRACED,
            target_type="KDE",
            target_id="LOT-B",
            actor="key-1",
            actor_type=FSMAAuditActorType.API,
            tenant_id="t1",
        )

        kde_reads = audit.get_by_action(FSMAAuditAction.KDE_READ)
        traced = audit.get_by_action(FSMAAuditAction.TRACED)

        assert len(kde_reads) == 1
        assert kde_reads[0].target_id == "LOT-A"
        assert len(traced) == 1
        assert traced[0].target_id == "LOT-B"


class TestTraceabilityEndpointAuditActionIsKDERead:
    """Traceability router must call audit log with KDE_READ, not TRACED."""

    def _make_traceability_module(self):
        """Import the traceability module directly to inspect its constants."""
        import importlib
        import services.graph.app.routers.fsma.traceability as mod
        return mod

    def test_traceability_module_uses_kde_read_action(self):
        """The traceability router must reference KDE_READ for read audits."""
        import ast
        router_path = (
            Path(__file__).parent.parent
            / "app" / "routers" / "fsma" / "traceability.py"
        )
        source = router_path.read_text()

        # Confirm KDE_READ is referenced in audit log calls
        assert "KDE_READ" in source, (
            "traceability.py does not reference FSMAAuditAction.KDE_READ — "
            "read-access auditing for #1033 is missing"
        )

        # Confirm the target_type is set to KDE
        assert 'target_type="KDE"' in source, (
            "traceability.py audit calls must set target_type='KDE'"
        )

        # Confirm the audit pattern appears multiple times (forward, backward, timeline, search)
        kde_read_count = source.count("FSMAAuditAction.KDE_READ")
        assert kde_read_count >= 3, (
            f"Expected at least 3 KDE_READ audit calls, found {kde_read_count}"
        )
