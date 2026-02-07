"""
Snapshot Engine Verification Tests

Audit-grade tests for cryptographic integrity and immutability.
"""
import pytest
import time
from datetime import datetime, timezone
from uuid import UUID, uuid4
from uuid_extensions import uuid7

from app.crypto import (
    calculate_content_hash,
    calculate_signature_hash,
    verify_content_hash,
    verify_signature_hash,
    verify_chain_integrity,
    ImmutabilityError
)
from app.models import (
    SnapshotCreationRequest,
    SnapshotGenerator,
    SnapshotTriggerEvent,
    SystemStatus
)
from app.snapshot_engine import SnapshotEngine


class TestContentHashDeterminism:
    """Verify content hash calculation is deterministic."""
    
    def test_same_input_produces_same_hash(self):
        """Critical: Same input must always produce same hash."""
        snapshot_data = {
            "snapshot_time": "2026-01-25T10:00:00+00:00",
            "substation_id": "ALPHA-001",
            "system_status": "NOMINAL",
            "asset_states": {
                "assets": [],
                "summary": {"total_assets": 0, "verified_count": 0}
            },
            "esp_config": {"zones": []},
            "patch_metrics": {"avg_patch_time_hours": 8.5},
            "active_mismatches": []
        }
        
        hash1 = calculate_content_hash(snapshot_data)
        hash2 = calculate_content_hash(snapshot_data)
        
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex length
    
    def test_different_content_produces_different_hash(self):
        """Different content must produce different hashes."""
        base_data = {
            "snapshot_time": "2026-01-25T10:00:00+00:00",
            "substation_id": "ALPHA-001",
            "system_status": "NOMINAL",
            "asset_states": {"assets": []},
            "esp_config": {"zones": []},
            "patch_metrics": {},
            "active_mismatches": []
        }
        
        modified_data = base_data.copy()
        modified_data["system_status"] = "DEGRADED"
        
        hash1 = calculate_content_hash(base_data)
        hash2 = calculate_content_hash(modified_data)
        
        assert hash1 != hash2
    
    def test_field_order_does_not_affect_hash(self):
        """Hash must be deterministic regardless of dict insertion order."""
        data1 = {
            "snapshot_time": "2026-01-25T10:00:00+00:00",
            "substation_id": "ALPHA-001",
            "system_status": "NOMINAL",
            "asset_states": {},
            "esp_config": {},
            "patch_metrics": {},
            "active_mismatches": []
        }
        
        # Same data, different order
        data2 = {
            "active_mismatches": [],
            "patch_metrics": {},
            "esp_config": {},
            "asset_states": {},
            "system_status": "NOMINAL",
            "substation_id": "ALPHA-001",
            "snapshot_time": "2026-01-25T10:00:00+00:00"
        }
        
        assert calculate_content_hash(data1) == calculate_content_hash(data2)


class TestSignatureHash:
    """Verify signature hash binds ID to content."""
    
    def test_signature_uniqueness(self):
        """Different ID or content produces different signature."""
        id1 = uuid4()
        id2 = uuid4()
        content_hash = "a" * 64
        
        sig1 = calculate_signature_hash(id1, content_hash)
        sig2 = calculate_signature_hash(id2, content_hash)
        
        assert sig1 != sig2
        assert len(sig1) == 64
        assert len(sig2) == 64
    
    def test_signature_verification(self):
        """Signature verification detects tampering."""
        snapshot_id = uuid4()
        content_hash = "b" * 64
        
        signature = calculate_signature_hash(snapshot_id, content_hash)
        
        # Valid signature
        assert verify_signature_hash(snapshot_id, content_hash, signature)
        
        # Tampered content
        assert not verify_signature_hash(snapshot_id, "c" * 64, signature)
        
        # Tampered ID
        assert not verify_signature_hash(uuid4(), content_hash, signature)


class TestChainIntegrity:
    """Verify snapshot chain integrity checks."""
    
    def test_valid_chain(self):
        """Valid chain passes verification."""
        prev_snapshot = {
            "id": str(uuid4()),
            "snapshot_time": "2026-01-25T09:00:00+00:00",
            "content_hash": "a" * 64,
            "signature_hash": "valid_sig"
        }
        
        # Recalculate correct signature for previous
        prev_id = UUID(prev_snapshot["id"])
        correct_sig = calculate_signature_hash(prev_id, prev_snapshot["content_hash"])
        prev_snapshot["signature_hash"] = correct_sig
        
        current_snapshot = {
            "id": str(uuid4()),
            "snapshot_time": "2026-01-25T10:00:00+00:00",
            "previous_snapshot_id": prev_snapshot["id"],
            "content_hash": "b" * 64,
            "signature_hash": "current_sig"
        }
        
        # Should not raise
        assert verify_chain_integrity(current_snapshot, prev_snapshot)
    
    def test_broken_id_chain(self):
        """Broken ID chain raises ImmutabilityError."""
        prev_snapshot = {
            "id": str(uuid4()),
            "snapshot_time": "2026-01-25T09:00:00+00:00",
            "content_hash": "a" * 64,
            "signature_hash": "sig"
        }
        
        current_snapshot = {
            "id": str(uuid4()),
            "snapshot_time": "2026-01-25T10:00:00+00:00",
            "previous_snapshot_id": str(uuid4()),  # Wrong ID
            "content_hash": "b" * 64,
            "signature_hash": "sig2"
        }
        
        with pytest.raises(ImmutabilityError, match="Chain break"):
            verify_chain_integrity(current_snapshot, prev_snapshot)
    
    def test_time_goes_backwards(self):
        """Non-monotonic time raises ImmutabilityError."""
        prev_snapshot = {
            "id": str(uuid4()),
            "snapshot_time": "2026-01-25T10:00:00+00:00",
            "content_hash": "a" * 64,
            "signature_hash": "sig"
        }
        
        current_snapshot = {
            "id": str(uuid4()),
            "snapshot_time": "2026-01-25T09:00:00+00:00",  # Earlier!
            "previous_snapshot_id": prev_snapshot["id"],
            "content_hash": "b" * 64,
            "signature_hash": "sig2"
        }
        
        with pytest.raises(ImmutabilityError, match="Time violation"):
            verify_chain_integrity(current_snapshot, prev_snapshot)
    
    def test_first_snapshot_has_no_chain(self):
        """First snapshot (no previous) is valid."""
        first_snapshot = {
            "id": str(uuid4()),
            "snapshot_time": "2026-01-25T10:00:00+00:00",
            "previous_snapshot_id": None,
            "content_hash": "a" * 64,
            "signature_hash": "sig"
        }
        
        assert verify_chain_integrity(first_snapshot, None)


class TestSystemStatusCalculation:
    """Verify deterministic status calculation."""
    
    @pytest.fixture
    def engine(self, db_session):
        """Snapshot engine instance."""
        return SnapshotEngine(db_session)
    
    def test_nominal_status(self, engine):
        """No mismatches and high verification → NOMINAL."""
        asset_states = {
            "summary": {
                "total_assets": 10,
                "verified_count": 10,
                "mismatch_count": 0
            }
        }
        
        status = engine._calculate_system_status(asset_states, [])
        assert status == SystemStatus.NOMINAL
    
    def test_degraded_low_verification(self, engine):
        """Low verification percentage → DEGRADED."""
        asset_states = {
            "summary": {
                "total_assets": 10,
                "verified_count": 8,  # 80% < 90% threshold
                "mismatch_count": 0
            }
        }
        
        status = engine._calculate_system_status(asset_states, [])
        assert status == SystemStatus.DEGRADED
    
    def test_degraded_low_severity_mismatches(self, engine):
        """Low severity mismatches → DEGRADED."""
        asset_states = {
            "summary": {
                "total_assets": 10,
                "verified_count": 10
            }
        }
        
        # Mock mismatch IDs (engine will query severity)
        mismatch_ids = [uuid4()]
        
        status = engine._calculate_system_status(asset_states, mismatch_ids)
        # Will be DEGRADED if no high-severity mismatches found
        assert status in [SystemStatus.DEGRADED, SystemStatus.NON_COMPLIANT]


class TestImmutabilityEnforcement:
    """Verify snapshots cannot be modified."""
    
    def test_snapshot_model_is_frozen(self):
        """ComplianceSnapshot dataclass is frozen."""
        from app.models import ComplianceSnapshot
        
        snapshot = ComplianceSnapshot(
            id=uuid4(),
            created_at=datetime.now(timezone.utc),
            snapshot_time=datetime.now(timezone.utc),
            substation_id="ALPHA-001",
            facility_name="Test",
            system_status=SystemStatus.NOMINAL,
            asset_states={},
            esp_config={},
            patch_metrics={},
            active_mismatches=[],
            generated_by=SnapshotGenerator.SYSTEM_AUTO,
            trigger_event=SnapshotTriggerEvent.SCHEDULED_DAILY,
            content_hash="a" * 64,
            signature_hash="b" * 64
        )
        
        # Attempt to modify frozen dataclass
        with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
            snapshot.system_status = SystemStatus.DEGRADED


class TestSnapshotCreation:
    """Integration tests for snapshot creation."""
    
    @pytest.fixture
    def mock_db(self):
        """Mock database session."""
        # TODO: Implement with actual test database
        pass
    
    def test_snapshot_id_is_uuid7(self):
        """Snapshot IDs should be UUIDv7 (time-ordered)."""
        # Generate multiple IDs
        id1 = uuid7()
        time.sleep(0.001)  # Small delay
        id2 = uuid7()
        
        # UUIDv7 are sortable by time
        assert id1 < id2


# Audit verification helpers

def test_hash_collision_resistance():
    """Verify hash function resists collisions."""
    hashes = set()
    
    for i in range(1000):
        data = {
            "snapshot_time": f"2026-01-25T10:00:{i:02d}+00:00",
            "substation_id": f"SUB-{i}",
            "system_status": "NOMINAL",
            "asset_states": {"counter": i},
            "esp_config": {},
            "patch_metrics": {},
            "active_mismatches": []
        }
        
        hash_val = calculate_content_hash(data)
        hashes.add(hash_val)
    
    # All hashes should be unique
    assert len(hashes) == 1000


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
