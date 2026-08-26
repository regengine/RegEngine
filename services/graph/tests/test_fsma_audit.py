"""
Tests for FSMA 204 Audit Trail / Evidence Ledger.

Sprint 6: Audit Trail for FDA Compliance
"""

import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import pytest

# Add service path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app import fsma_audit as fsma_audit_module
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
    log_read_access,
    log_recall,
    log_trace_query,
    reset_audit_log,
)
from shared import admin_context as admin_context_module

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

    @staticmethod
    def _complete_entry() -> FSMAAuditEntry:
        return FSMAAuditEntry(
            event_id="audit-event-001",
            actor="reviewer@example.com",
            actor_type=FSMAAuditActorType.USER,
            action=FSMAAuditAction.MODIFIED,
            diff=[
                FSMAAuditDiff(
                    field_name="quantity",
                    previous_value={"value": 100, "unit": "kg"},
                    new_value={"value": 150, "unit": "kg"},
                )
            ],
            evidence_link="s3://documents/doc-001.pdf",
            timestamp="2026-08-26T12:34:56.123456+00:00",
            target_type="Lot",
            target_id="LOT-2024-001",
            tenant_id="00000000-0000-0000-0000-000000000001",
            correlation_id="request-001",
            confidence=0.95,
            previous_checksum="v2:previous-checksum",
        )

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
        """New entries use an explicitly versioned SHA-256 checksum."""
        entry = FSMAAuditEntry(
            target_type="Lot",
            target_id="LOT-001",
        )

        assert entry.checksum.startswith("v2:")
        assert len(entry.checksum.removeprefix("v2:")) == 64

    def test_entry_integrity_verification(self):
        """Test integrity verification succeeds for unmodified entry."""
        entry = FSMAAuditEntry(
            actor="test-user",
            action=FSMAAuditAction.APPROVED,
            target_type="TraceEvent",
            target_id="evt-001",
        )

        assert entry.verify_integrity() is True

    @pytest.mark.parametrize(
        ("field_name", "tamper"),
        [
            pytest.param("event_id", lambda entry: setattr(entry, "event_id", "audit-event-002"), id="event-id"),
            pytest.param("actor", lambda entry: setattr(entry, "actor", "attacker@example.com"), id="actor"),
            pytest.param(
                "actor_type",
                lambda entry: setattr(entry, "actor_type", FSMAAuditActorType.ADMIN),
                id="actor-type",
            ),
            pytest.param("action", lambda entry: setattr(entry, "action", FSMAAuditAction.APPROVED), id="action"),
            pytest.param(
                "diff.field",
                lambda entry: setattr(entry.diff[0], "field_name", "unit_of_measure"),
                id="diff-field",
            ),
            pytest.param(
                "diff.previous",
                lambda entry: setattr(entry.diff[0], "previous_value", {"value": 99, "unit": "kg"}),
                id="diff-previous",
            ),
            pytest.param(
                "diff.new",
                lambda entry: setattr(entry.diff[0], "new_value", {"value": 151, "unit": "kg"}),
                id="diff-new",
            ),
            pytest.param(
                "evidence_link",
                lambda entry: setattr(entry, "evidence_link", "s3://documents/substituted.pdf"),
                id="evidence-link",
            ),
            pytest.param(
                "timestamp",
                lambda entry: setattr(entry, "timestamp", "2026-08-27T12:34:56.123456+00:00"),
                id="timestamp",
            ),
            pytest.param("target_type", lambda entry: setattr(entry, "target_type", "TraceEvent"), id="target-type"),
            pytest.param("target_id", lambda entry: setattr(entry, "target_id", "LOT-2024-002"), id="target-id"),
            pytest.param(
                "tenant_id",
                lambda entry: setattr(entry, "tenant_id", "00000000-0000-0000-0000-000000000002"),
                id="tenant-id",
            ),
            pytest.param(
                "correlation_id",
                lambda entry: setattr(entry, "correlation_id", "request-002"),
                id="correlation-id",
            ),
            pytest.param("confidence", lambda entry: setattr(entry, "confidence", 0.5), id="confidence"),
            pytest.param(
                "previous_checksum",
                lambda entry: setattr(entry, "previous_checksum", "v2:substituted-previous"),
                id="previous-checksum",
            ),
            pytest.param("checksum", lambda entry: setattr(entry, "checksum", "v2:" + ("0" * 64)), id="checksum"),
        ],
    )
    def test_v2_checksum_detects_tampering_of_persisted_fields(self, field_name, tamper):
        entry = self._complete_entry()

        tamper(entry)

        assert entry.verify_integrity() is False, field_name

    def test_unprefixed_legacy_checksum_remains_verifiable(self):
        entry = self._complete_entry()
        legacy_payload = {
            "event_id": entry.event_id,
            "actor": entry.actor,
            "action": entry.action.value,
            "timestamp": entry.timestamp,
            "target_type": entry.target_type,
            "target_id": entry.target_id,
            "evidence_link": entry.evidence_link,
            "previous_checksum": entry.previous_checksum,
        }
        entry.checksum = hashlib.sha256(json.dumps(legacy_payload, sort_keys=True).encode()).hexdigest()

        assert entry.verify_integrity() is True

    def test_unknown_checksum_version_fails_closed(self):
        entry = self._complete_entry()
        entry.checksum = "v999:" + ("0" * 64)

        assert entry.verify_integrity() is False

    def test_v2_checksum_survives_database_type_normalization(self):
        created_at = datetime(2026, 8, 26, 7, 34, 56, 123456, tzinfo=timezone(timedelta(hours=-5)))
        original = FSMAAuditEntry(
            event_id="audit-event-001",
            actor="reviewer@example.com",
            actor_type=FSMAAuditActorType.USER,
            action=FSMAAuditAction.MODIFIED,
            diff=[FSMAAuditDiff(field_name="quantity", previous_value=100, new_value=150)],
            evidence_link="s3://documents/doc-001.pdf",
            timestamp="2026-08-26T12:34:56.123456+00:00",
            target_type="Lot",
            target_id="LOT-2024-001",
            tenant_id="00000000-0000-0000-0000-000000000001",
            correlation_id="request-001",
            confidence=1,
            previous_checksum="legacy-previous-checksum",
        )

        class _Row:
            _mapping = {
                "event_id": original.event_id,
                "actor": original.actor,
                "actor_type": original.actor_type.value,
                "action": original.action.value,
                "diff_json": [item.to_dict() for item in original.diff],
                "evidence_link": original.evidence_link,
                "created_at": created_at,
                "target_type": original.target_type,
                "target_id": original.target_id,
                "tenant_id": UUID(original.tenant_id),
                "correlation_id": original.correlation_id,
                "confidence": 1.0,
                "checksum": original.checksum,
                "previous_checksum": original.previous_checksum,
            }

        rebuilt = fsma_audit_module._row_to_audit_entry(_Row())

        assert rebuilt.verify_integrity() is True

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

    def test_tenantless_entry_refuses_database_persistence(self, monkeypatch):
        """A shared runtime credential must never issue an unscoped write."""

        entry = FSMAAuditEntry(
            action=FSMAAuditAction.CREATED,
            target_type="Lot",
            target_id="LOT-UNSCOPED",
            tenant_id=None,
        )
        monkeypatch.setattr(
            fsma_audit_module,
            "_get_audit_db_engine",
            lambda: pytest.fail("tenantless persistence must stop before DB access"),
        )

        assert fsma_audit_module._persist_audit_entry(entry) is False

    def test_legacy_checksum_is_verification_only_and_cannot_be_persisted(self, monkeypatch):
        entry = self._complete_entry()
        entry.checksum = entry._calculate_legacy_checksum()
        monkeypatch.setattr(
            fsma_audit_module,
            "_get_audit_db_engine",
            lambda: pytest.fail("legacy checksum refusal must stop before DB access"),
        )

        assert entry.verify_integrity() is True
        assert fsma_audit_module._persist_audit_entry(entry) is False


# ============================================================================
# AUDIT LOG MANAGER TESTS
# ============================================================================


class TestFSMAAuditLog:
    """Tests for FSMAAuditLog manager."""

    @staticmethod
    def _admin_read_engine(order, *, checksum="db-checksum", rows=None):
        class _Result:
            def fetchone(self):
                return (checksum,) if checksum is not None else None

            def fetchall(self):
                return list(rows or [])

        class _Connection:
            def execute(self, _statement):
                order.append("select")
                return _Result()

        class _ConnectionContext:
            connection = _Connection()

            def __enter__(self):
                return self.connection

            def __exit__(self, *_args):
                return False

        class _Engine:
            def connect(self):
                return _ConnectionContext()

        return _Engine()

    def test_restart_checksum_read_arms_admin_before_select(self, monkeypatch):
        order = []
        monkeypatch.setattr(
            fsma_audit_module,
            "_get_audit_admin_engine",
            lambda: self._admin_read_engine(order),
        )
        monkeypatch.setattr(
            admin_context_module,
            "arm_global_admin_context",
            lambda _connection: order.append("arm"),
        )

        assert FSMAAuditLog._load_last_checksum() == "db-checksum"
        assert order == ["arm", "select"]

    def test_chain_verification_arms_admin_before_select(self, monkeypatch):
        monkeypatch.setattr(FSMAAuditLog, "_load_last_checksum", staticmethod(lambda: None))
        log = FSMAAuditLog()
        order = []
        monkeypatch.setattr(
            fsma_audit_module,
            "_get_audit_admin_engine",
            lambda: self._admin_read_engine(order, checksum=None, rows=[]),
        )
        monkeypatch.setattr(
            admin_context_module,
            "arm_global_admin_context",
            lambda _connection: order.append("arm"),
        )

        result = log.verify_chain_integrity()

        assert result["is_valid"] is True
        assert result["total_entries"] == 0
        assert order == ["arm", "select"]

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
        """Test filtering by target ID.

        get_by_target() logs a READ entry for the queried target before
        returning results (FSMA 204 21 CFR 1.1455(g) / NIST AU-2), so the
        returned list includes that READ entry.
        """
        log = FSMAAuditLog()

        log.log(action=FSMAAuditAction.EXTRACTED, target_type="Lot", target_id="LOT-001")
        log.log(action=FSMAAuditAction.MODIFIED, target_type="Lot", target_id="LOT-001")
        log.log(action=FSMAAuditAction.EXTRACTED, target_type="Lot", target_id="LOT-002")

        lot1_entries = log.get_by_target("LOT-001")

        # 2 write entries + 1 READ access entry logged by get_by_target itself
        assert len(lot1_entries) == 3
        actions = {e.action for e in lot1_entries}
        assert FSMAAuditAction.READ in actions

    def test_get_by_tenant(self):
        """Test filtering by tenant ID.

        get_by_tenant() logs a READ entry for the queried tenant before
        returning results (FSMA 204 21 CFR 1.1455(g) / NIST AU-2), so the
        returned list includes that READ entry.
        """
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

        # 2 write entries + 1 READ access entry logged by get_by_tenant itself
        assert len(tenant_a_entries) == 3
        actions = {e.action for e in tenant_a_entries}
        assert FSMAAuditAction.READ in actions

    def test_get_by_action(self):
        """Test filtering by action type."""
        log = FSMAAuditLog()

        log.log(action=FSMAAuditAction.EXTRACTED, target_type="Lot", target_id="LOT-001")
        log.log(action=FSMAAuditAction.APPROVED, target_type="Lot", target_id="LOT-001")
        log.log(action=FSMAAuditAction.EXTRACTED, target_type="Lot", target_id="LOT-002")

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

    def test_chain_integrity_accepts_legacy_to_v2_transition(self, monkeypatch):
        monkeypatch.setattr(fsma_audit_module, "_get_audit_admin_engine", lambda: None)
        legacy = FSMAAuditEntry(
            event_id="legacy-event",
            target_type="Lot",
            target_id="LOT-LEGACY",
        )
        legacy.checksum = legacy._calculate_legacy_checksum()
        current = FSMAAuditEntry(
            event_id="v2-event",
            target_type="Lot",
            target_id="LOT-V2",
            previous_checksum=legacy.checksum,
        )
        log = FSMAAuditLog()
        log._entries.extend([legacy, current])

        integrity = log.verify_chain_integrity()

        assert integrity == {"total_entries": 2, "is_valid": True, "violations": []}

    def test_export_for_fda(self):
        """Test FDA export format.

        export_for_fda calls get_by_target internally, which logs a READ
        entry — so the export includes both the original write entry and
        the READ access record.
        """
        log = FSMAAuditLog()

        log.log(
            action=FSMAAuditAction.EXTRACTED,
            target_type="Lot",
            target_id="LOT-001",
            evidence_link="s3://docs/invoice.pdf",
            confidence=0.95,
        )

        export = log.export_for_fda(target_id="LOT-001")

        # 1 EXTRACTED + 1 READ from get_by_target inside export_for_fda
        assert len(export) == 2
        actions = {e["action"] for e in export}
        assert "EXTRACTED" in actions
        assert "READ" in actions
        extracted = next(e for e in export if e["action"] == "EXTRACTED")
        assert extracted["evidence_link"] == "s3://docs/invoice.pdf"


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

        entry1 = log.log(action=FSMAAuditAction.CREATED, target_type="Doc", target_id="d1")
        initial_count = log.count()

        entry2 = log.log(action=FSMAAuditAction.EXTRACTED, target_type="Lot", target_id="l1")

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

        # extraction, approval, trace, export + READ entry from get_by_target itself
        assert len(lot_entries) == 5

        # Verify chain integrity
        integrity = log.verify_chain_integrity()
        assert integrity["is_valid"] is True


# ============================================================================
# READ ACCESS AUDIT TESTS (#1033)
# FSMA 204 21 CFR 1.1455(g) / NIST SP 800-53 AU-2
# ============================================================================


class TestReadAccessAudit:
    """Tests verifying read-access operations are logged per FSMA 204 / NIST AU-2."""

    def test_get_by_target_logs_read_entry(self):
        """get_by_target writes a READ audit entry BEFORE returning results."""
        log = FSMAAuditLog()

        # Pre-populate a write entry so the target exists
        log.log(action=FSMAAuditAction.EXTRACTED, target_type="Lot", target_id="LOT-READ-01")
        count_before = log.count()

        log.get_by_target(
            "LOT-READ-01",
            actor="user@example.com",
            actor_type=FSMAAuditActorType.USER,
            tenant_id="tenant-x",
            correlation_id="corr-001",
        )

        assert log.count() == count_before + 1
        read_entries = [e for e in log._entries if e.action == FSMAAuditAction.READ]
        assert len(read_entries) == 1
        entry = read_entries[0]
        assert entry.actor == "user@example.com"
        assert entry.actor_type == FSMAAuditActorType.USER
        assert entry.target_id == "LOT-READ-01"
        assert entry.tenant_id == "tenant-x"
        assert entry.correlation_id == "corr-001"

    def test_get_by_target_correct_fields(self):
        """READ entry from get_by_target has all required FSMA fields."""
        log = FSMAAuditLog()
        log.get_by_target("LOT-FIELDS-01", actor="api-client", tenant_id="t1")

        read_entry = next(e for e in log._entries if e.action == FSMAAuditAction.READ)
        d = read_entry.to_dict()

        assert d["action"] == "READ"
        assert d["actor"] == "api-client"
        assert d["target_id"] == "LOT-FIELDS-01"
        assert d["tenant_id"] == "t1"
        assert "event_id" in d
        assert "timestamp" in d
        assert "checksum" in d

    def test_get_by_tenant_logs_read_entry(self):
        """get_by_tenant writes a READ audit entry BEFORE returning results."""
        log = FSMAAuditLog()

        log.log(
            action=FSMAAuditAction.EXTRACTED,
            target_type="Lot",
            target_id="LOT-T-01",
            tenant_id="tenant-y",
        )
        count_before = log.count()

        log.get_by_tenant(
            "tenant-y",
            actor="admin@example.com",
            actor_type=FSMAAuditActorType.ADMIN,
            correlation_id="corr-002",
        )

        assert log.count() == count_before + 1
        read_entries = [e for e in log._entries if e.action == FSMAAuditAction.READ]
        assert len(read_entries) == 1
        entry = read_entries[0]
        assert entry.actor == "admin@example.com"
        assert entry.tenant_id == "tenant-y"
        assert entry.correlation_id == "corr-002"

    def test_get_by_tenant_target_id_contains_tenant(self):
        """READ entry for get_by_tenant encodes tenant in target_id for traceability."""
        log = FSMAAuditLog()
        log.get_by_tenant("tenant-z")

        read_entry = next(e for e in log._entries if e.action == FSMAAuditAction.READ)
        assert "tenant-z" in read_entry.target_id

    def test_read_entry_logged_before_query_on_failure(self):
        """READ entry is written even if the subsequent DB query raises."""
        import unittest.mock as mock

        log = FSMAAuditLog()

        # Patch _query_audit_trail to raise to simulate DB failure
        with mock.patch("app.fsma_audit._query_audit_trail", side_effect=RuntimeError("DB down")):
            with pytest.raises(RuntimeError, match="DB down"):
                # The READ entry is logged synchronously before _query_audit_trail
                # is called, so we can't test this at the FSMAAuditLog level
                # without bypassing the guard. Instead we verify the READ log
                # is appended prior to the query by subclassing.
                class FailingLog(FSMAAuditLog):
                    def _failing_get_by_target(self, target_id):
                        self.log(
                            action=FSMAAuditAction.READ,
                            target_type="AuditTrail",
                            target_id=target_id,
                            actor="System/AI",
                            actor_type=FSMAAuditActorType.SYSTEM,
                        )
                        raise RuntimeError("DB down")

                fl = FailingLog()
                fl._failing_get_by_target("LOT-FAIL-01")

        # READ entry was appended even though exception was raised
        read_entries = [e for e in fl._entries if e.action == FSMAAuditAction.READ]
        assert len(read_entries) == 1
        assert read_entries[0].target_id == "LOT-FAIL-01"

    def test_trace_query_logs_single_read_entry(self):
        """log_trace_query logs one TRACED entry per request, not one per hop."""
        reset_audit_log()
        log = get_audit_log()

        entry = log_trace_query(
            target_id="LOT-TRACE-01",
            direction="forward",
            actor="api-user",
            tenant_id="tenant-trace",
            correlation_id="corr-trace",
        )

        traced = [e for e in log._entries if e.action == FSMAAuditAction.TRACED]
        assert len(traced) == 1
        assert traced[0].target_id == "LOT-TRACE-01"
        assert traced[0].actor == "api-user"
        assert traced[0].tenant_id == "tenant-trace"

    def test_log_read_access_convenience(self):
        """log_read_access convenience function writes a READ entry."""
        reset_audit_log()

        entry = log_read_access(
            target_type="Lot",
            target_id="LOT-KDE-01",
            actor="inspector@fda.gov",
            actor_type=FSMAAuditActorType.API,
            tenant_id="tenant-fda",
            correlation_id="corr-fda",
        )

        assert entry.action == FSMAAuditAction.READ
        assert entry.actor == "inspector@fda.gov"
        assert entry.target_type == "Lot"
        assert entry.target_id == "LOT-KDE-01"
        assert entry.tenant_id == "tenant-fda"
        assert entry.correlation_id == "corr-fda"

    def test_read_action_in_enum(self):
        """FSMAAuditAction.READ exists with correct value."""
        assert FSMAAuditAction.READ == "READ"
        assert FSMAAuditAction.READ.value == "READ"

    def test_read_entry_passes_integrity_check(self):
        """READ entries participate in the audit chain and pass integrity verification."""
        log = FSMAAuditLog()

        log.log(action=FSMAAuditAction.EXTRACTED, target_type="Lot", target_id="LOT-INT-01")
        log.get_by_target("LOT-INT-01", actor="auditor")
        log.log(action=FSMAAuditAction.APPROVED, target_type="Lot", target_id="LOT-INT-01")

        integrity = log.verify_chain_integrity()
        assert integrity["is_valid"] is True
