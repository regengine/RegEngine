"""
Tests for FSMA 204 Audit Trail / Evidence Ledger.

Sprint 6: Audit Trail for FDA Compliance
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# Add service path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.fsma_audit import (  # Enums; Data classes; Manager class; Global functions; Convenience functions; Decorator
    FSMAAuditAction,
    FSMAAuditActorType,
    FSMAAuditDiff,
    FSMAAuditEntry,
    FSMAAuditLog,
    audit_graph_write,
    get_audit_log,
    log_approval,
    log_export,
    log_extraction,
    log_modification,
    log_recall,
    log_trace_query,
    reset_audit_log,
)

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture(autouse=True)
def reset_log():
    """Reset the global audit log before each test."""
    reset_audit_log()
    yield
    reset_audit_log()


# ============================================================================
# AUDIT ENTRY TESTS
# ============================================================================


class TestFSMAAuditEntry:
    """Tests for FSMAAuditEntry data class."""

    def test_entry_creation(self):
        """Test basic audit entry creation."""
        entry = FSMAAuditEntry(
            actor="System/AI",
            action=FSMAAuditAction.EXTRACTED,
            target_type="Lot",
            target_id="LOT-2024-001",
            evidence_link="s3://documents/doc-001.pdf",
        )

        assert entry.event_id is not None
        assert entry.actor == "System/AI"
        assert entry.action == FSMAAuditAction.EXTRACTED
        assert entry.target_type == "Lot"
        assert entry.target_id == "LOT-2024-001"
        assert entry.evidence_link == "s3://documents/doc-001.pdf"

    def test_entry_has_timestamp(self):
        """Test that entries have ISO format timestamps."""
        entry = FSMAAuditEntry()

        assert entry.timestamp is not None
        # Should be valid ISO format
        datetime.fromisoformat(entry.timestamp.replace("Z", "+00:00"))

    def test_entry_has_checksum(self):
        """Test that entries have SHA-256 checksums."""
        entry = FSMAAuditEntry(
            target_type="Lot",
            target_id="LOT-001",
        )

        assert entry.checksum is not None
        assert len(entry.checksum) == 64  # SHA-256 hex length

    def test_entry_integrity_verification(self):
        """Test integrity verification succeeds for unmodified entry."""
        entry = FSMAAuditEntry(
            actor="test-user",
            action=FSMAAuditAction.APPROVED,
            target_type="TraceEvent",
            target_id="evt-001",
        )

        assert entry.verify_integrity() is True

    def test_entry_to_dict(self):
        """Test conversion to dictionary."""
        entry = FSMAAuditEntry(
            actor="test-user",
            action=FSMAAuditAction.MODIFIED,
            target_type="Lot",
            target_id="LOT-001",
        )

        d = entry.to_dict()

        assert d["actor"] == "test-user"
        assert d["action"] == "MODIFIED"
        assert d["target_type"] == "Lot"
        assert d["target_id"] == "LOT-001"
        assert "event_id" in d
        assert "timestamp" in d
        assert "checksum" in d

    def test_diff_tracking(self):
        """Test that diffs are properly recorded."""
        diff = FSMAAuditDiff(
            field_name="quantity",
            previous_value=100,
            new_value=150,
        )

        entry = FSMAAuditEntry(
            action=FSMAAuditAction.MODIFIED,
            diff=[diff],
            target_type="Lot",
            target_id="LOT-001",
        )

        assert len(entry.diff) == 1
        assert entry.diff[0].field_name == "quantity"
        assert entry.diff[0].previous_value == 100
        assert entry.diff[0].new_value == 150


# ============================================================================
# AUDIT LOG MANAGER TESTS
# ============================================================================


class TestFSMAAuditLog:
    """Tests for FSMAAuditLog manager."""

    def test_log_creates_entry(self):
        """Test that logging creates an entry."""
        log = FSMAAuditLog()

        entry = log.log(
            action=FSMAAuditAction.CREATED,
            target_type="Document",
            target_id="doc-001",
        )

        assert entry is not None
        assert log.count() == 1

    def test_log_chains_checksums(self):
        """Test that entries are linked by checksum chain."""
        log = FSMAAuditLog()

        entry1 = log.log(
            action=FSMAAuditAction.CREATED,
            target_type="Document",
            target_id="doc-001",
        )
        entry2 = log.log(
            action=FSMAAuditAction.CREATED,
            target_type="Lot",
            target_id="lot-001",
        )

        assert entry1.previous_checksum is None
        assert entry2.previous_checksum == entry1.checksum

    def test_get_by_target(self):
        """Test filtering by target ID."""
        log = FSMAAuditLog()

        log.log(
            action=FSMAAuditAction.EXTRACTED, target_type="Lot", target_id="LOT-001"
        )
        log.log(action=FSMAAuditAction.MODIFIED, target_type="Lot", target_id="LOT-001")
        log.log(
            action=FSMAAuditAction.EXTRACTED, target_type="Lot", target_id="LOT-002"
        )

        lot1_entries = log.get_by_target("LOT-001")

        assert len(lot1_entries) == 2

    def test_get_by_tenant(self):
        """Test filtering by tenant ID."""
        log = FSMAAuditLog()

        log.log(
            action=FSMAAuditAction.EXTRACTED,
            target_type="Lot",
            target_id="LOT-001",
            tenant_id="tenant-a",
        )
        log.log(
            action=FSMAAuditAction.EXTRACTED,
            target_type="Lot",
            target_id="LOT-002",
            tenant_id="tenant-b",
        )
        log.log(
            action=FSMAAuditAction.EXTRACTED,
            target_type="Lot",
            target_id="LOT-003",
            tenant_id="tenant-a",
        )

        tenant_a_entries = log.get_by_tenant("tenant-a")

        assert len(tenant_a_entries) == 2

    def test_get_by_action(self):
        """Test filtering by action type."""
        log = FSMAAuditLog()

        log.log(
            action=FSMAAuditAction.EXTRACTED, target_type="Lot", target_id="LOT-001"
        )
        log.log(action=FSMAAuditAction.APPROVED, target_type="Lot", target_id="LOT-001")
        log.log(
            action=FSMAAuditAction.EXTRACTED, target_type="Lot", target_id="LOT-002"
        )

        extracted = log.get_by_action(FSMAAuditAction.EXTRACTED)

        assert len(extracted) == 2

    def test_chain_integrity_valid(self):
        """Test that valid chain passes integrity check."""
        log = FSMAAuditLog()

        log.log(action=FSMAAuditAction.CREATED, target_type="Doc", target_id="d1")
        log.log(action=FSMAAuditAction.EXTRACTED, target_type="Lot", target_id="l1")
        log.log(action=FSMAAuditAction.APPROVED, target_type="Lot", target_id="l1")

        integrity = log.verify_chain_integrity()

        assert integrity["is_valid"] is True
        assert integrity["total_entries"] == 3
        assert len(integrity["violations"]) == 0

    def test_export_for_fda(self):
        """Test FDA export format."""
        log = FSMAAuditLog()

        log.log(
            action=FSMAAuditAction.EXTRACTED,
            target_type="Lot",
            target_id="LOT-001",
            evidence_link="s3://docs/invoice.pdf",
            confidence=0.95,
        )

        export = log.export_for_fda(target_id="LOT-001")

        assert len(export) == 1
        assert export[0]["action"] == "EXTRACTED"
        assert export[0]["evidence_link"] == "s3://docs/invoice.pdf"


# ============================================================================
# CONVENIENCE FUNCTION TESTS
# ============================================================================


class TestConvenienceFunctions:
    """Tests for convenience logging functions."""

    def test_log_extraction(self):
        """Test log_extraction function."""
        entry = log_extraction(
            target_type="Lot",
            target_id="LOT-2024-001",
            evidence_link="s3://docs/bol.pdf",
            confidence=0.92,
            extracted_fields={
                "product_description": "Fresh Lettuce",
                "quantity": 100,
            },
        )

        assert entry.action == FSMAAuditAction.EXTRACTED
        assert entry.actor_type == FSMAAuditActorType.AI
        assert entry.confidence == 0.92
        assert len(entry.diff) == 2

    def test_log_modification(self):
        """Test log_modification function."""
        entry = log_modification(
            target_type="Lot",
            target_id="LOT-001",
            actor="user@example.com",
            changes={
                "quantity": (100, 150),
                "unit_of_measure": ("kg", "lbs"),
            },
        )

        assert entry.action == FSMAAuditAction.MODIFIED
        assert entry.actor == "user@example.com"
        assert len(entry.diff) == 2

    def test_log_approval(self):
        """Test log_approval function."""
        entry = log_approval(
            target_type="TraceEvent",
            target_id="evt-001",
            actor="reviewer@company.com",
        )

        assert entry.action == FSMAAuditAction.APPROVED
        assert entry.actor_type == FSMAAuditActorType.USER

    def test_log_trace_query(self):
        """Test log_trace_query function."""
        entry = log_trace_query(
            target_id="LOT-001",
            direction="forward",
        )

        assert entry.action == FSMAAuditAction.TRACED
        assert entry.target_type == "Lot"

    def test_log_export(self):
        """Test log_export function."""
        entry = log_export(
            target_id="LOT-001",
            export_type="csv",
        )

        assert entry.action == FSMAAuditAction.EXPORTED

    def test_log_recall(self):
        """Test log_recall function."""
        entry = log_recall(
            target_id="LOT-CONTAMINATED",
            actor="safety@company.com",
            is_initiated=True,
            affected_facilities=15,
        )

        assert entry.action == FSMAAuditAction.RECALL_INITIATED


# ============================================================================
# GLOBAL AUDIT LOG TESTS
# ============================================================================


class TestGlobalAuditLog:
    """Tests for global audit log singleton."""

    def test_get_audit_log_returns_same_instance(self):
        """Test singleton behavior."""
        log1 = get_audit_log()
        log2 = get_audit_log()

        assert log1 is log2

    def test_reset_clears_log(self):
        """Test reset clears all entries."""
        log = get_audit_log()
        log.log(action=FSMAAuditAction.CREATED, target_type="Doc", target_id="d1")

        assert log.count() > 0

        reset_audit_log()
        new_log = get_audit_log()

        assert new_log.count() == 0


# ============================================================================
# FDA COMPLIANCE TESTS
# ============================================================================


class TestFDACompliance:
    """Tests ensuring FDA audit requirements are met."""

    def test_all_required_fields_present(self):
        """Verify all FDA-required fields are in audit entries."""
        entry = log_extraction(
            target_type="Lot",
            target_id="LOT-001",
            evidence_link="s3://docs/doc.pdf",
            confidence=0.9,
            extracted_fields={"field": "value"},
        )

        d = entry.to_dict()

        # Required per FSMA 204 Section 7
        assert "event_id" in d  # UUID
        assert "actor" in d  # User ID or "System/AI"
        assert "action" in d  # EXTRACTED, MODIFIED, APPROVED
        assert "diff" in d  # Previous vs New Value
        assert "evidence_link" in d  # S3 URI to source PDF

    def test_audit_chain_tamper_detection(self):
        """Test that tampering is detected."""
        log = FSMAAuditLog()

        log.log(action=FSMAAuditAction.CREATED, target_type="Doc", target_id="d1")
        log.log(action=FSMAAuditAction.EXTRACTED, target_type="Lot", target_id="l1")

        # Tamper with the first entry's checksum
        log._entries[0].checksum = "tampered_checksum"

        integrity = log.verify_chain_integrity()

        assert integrity["is_valid"] is False
        assert len(integrity["violations"]) > 0

    def test_immutability_append_only(self):
        """Test that log is append-only."""
        log = FSMAAuditLog()

        entry1 = log.log(
            action=FSMAAuditAction.CREATED, target_type="Doc", target_id="d1"
        )
        initial_count = log.count()

        entry2 = log.log(
            action=FSMAAuditAction.EXTRACTED, target_type="Lot", target_id="l1"
        )

        # Count should only increase
        assert log.count() == initial_count + 1

        # Original entry should still be there
        all_entries = log.get_all()
        assert all_entries[0].event_id == entry1.event_id


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


class TestAuditIntegration:
    """Integration tests for audit workflow."""

    def test_full_document_lifecycle(self):
        """Test auditing a complete document processing lifecycle."""
        # 1. Document extracted
        log_extraction(
            target_type="Document",
            target_id="DOC-001",
            evidence_link="s3://docs/invoice.pdf",
            confidence=1.0,
            extracted_fields={"document_type": "INVOICE"},
        )

        # 2. Lot extracted from document
        log_extraction(
            target_type="Lot",
            target_id="LOT-001",
            evidence_link="s3://docs/invoice.pdf",
            confidence=0.92,
            extracted_fields={
                "product_description": "Romaine Lettuce",
                "quantity": 500,
            },
        )

        # 3. Human approval
        log_approval(
            target_type="Lot",
            target_id="LOT-001",
            actor="reviewer@company.com",
        )

        # 4. Trace query
        log_trace_query(
            target_id="LOT-001",
            direction="forward",
        )

        # 5. Export for recall
        log_export(
            target_id="LOT-001",
            export_type="csv",
        )

        # Verify audit trail
        log = get_audit_log()
        lot_entries = log.get_by_target("LOT-001")

        assert len(lot_entries) == 4  # extraction, approval, trace, export

        # Verify chain integrity
        integrity = log.verify_chain_integrity()
        assert integrity["is_valid"] is True
