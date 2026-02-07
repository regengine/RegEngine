"""
Test suite for RegEngine Customer Verification SDK.

Validates that verification script correctly identifies:
1. Valid snapshot chains (should pass)
2. Modified content (should fail)
3. Broken chains (should fail)
4. Time violations (should fail)
"""

import json
import pytest
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime, timedelta, timezone
import hashlib


# Import the verification module
import sys
sys.path.insert(0, str(Path(__file__).parent))
from verify_snapshot_chain import SnapshotVerifier, VerificationError


class TestSnapshotVerification:
    """Test cases for customer verification SDK."""
    
    def create_valid_snapshot(
        self,
        snapshot_id: str,
        snapshot_time: datetime,
        substation_id: str = "ALPHA-001",
        previous_id: str = None
    ) -> dict:
        """Create a valid snapshot with correct hashes."""
        snapshot = {
            "id": snapshot_id,
            "snapshot_time": snapshot_time.isoformat(),
            "substation_id": substation_id,
            "facility_name": "Test Facility",
            "system_status": "NOMINAL",
            "asset_states": {
                "summary": {
                    "total_assets": 10,
                    "verified_count": 10
                },
                "assets": []
            },
            "esp_config": {
                "zones": []
            },
            "patch_metrics": {
                "avg_hours": 8.5
            },
            "active_mismatches": [],
            "previous_snapshot_id": previous_id
        }
        
        # Calculate content hash
        canonical = {
            "snapshot_time": snapshot["snapshot_time"],
            "substation_id": snapshot["substation_id"],
            "system_status": snapshot["system_status"],
            "asset_states": snapshot["asset_states"],
            "esp_config": snapshot["esp_config"],
            "patch_metrics": snapshot["patch_metrics"],
            "active_mismatches": []
        }
        
        canonical_json = json.dumps(canonical, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
        content_hash = hashlib.sha256(canonical_json.encode('utf-8')).hexdigest()
        
        # Calculate signature hash
        signature_input = f"{snapshot_id}:{content_hash}"
        signature_hash = hashlib.sha256(signature_input.encode('utf-8')).hexdigest()
        
        snapshot["content_hash"] = content_hash
        snapshot["signature_hash"] = signature_hash
        
        return snapshot
    
    def test_valid_single_snapshot(self):
        """Test verification of single valid snapshot."""
        snapshot = self.create_valid_snapshot(
            snapshot_id="test-uuid-001",
            snapshot_time=datetime.now(timezone.utc)
        )
        
        export_data = {
            "metadata": {
                "substation_id": "ALPHA-001",
                "export_time": datetime.now(timezone.utc).isoformat()
            },
            "snapshots": [snapshot]
        }
        
        verifier = SnapshotVerifier(export_data)
        results = verifier.verify_all()
        
        assert results["verified_count"] == 1
        assert results["chain_intact"] is True
        assert len(results["content_hash_failures"]) == 0
        assert len(results["signature_hash_failures"]) == 0
    
    def test_valid_snapshot_chain(self):
        """Test verification of valid multi-snapshot chain."""
        base_time = datetime.now(timezone.utc)
        
        snapshot1 = self.create_valid_snapshot(
            snapshot_id="test-uuid-001",
            snapshot_time=base_time,
            previous_id=None
        )
        
        snapshot2 = self.create_valid_snapshot(
            snapshot_id="test-uuid-002",
            snapshot_time=base_time + timedelta(hours=1),
            previous_id="test-uuid-001"
        )
        
        snapshot3 = self.create_valid_snapshot(
            snapshot_id="test-uuid-003",
            snapshot_time=base_time + timedelta(hours=2),
            previous_id="test-uuid-002"
        )
        
        export_data = {
            "metadata": {
                "substation_id": "ALPHA-001",
                "export_time": datetime.now(timezone.utc).isoformat()
            },
            "snapshots": [snapshot1, snapshot2, snapshot3]
        }
        
        verifier = SnapshotVerifier(export_data)
        results = verifier.verify_all()
        
        assert results["verified_count"] == 3
        assert results["chain_intact"] is True
        assert len(results["content_hash_failures"]) == 0
    
    def test_content_tampering_detection(self):
        """Test detection of modified snapshot content."""
        snapshot = self.create_valid_snapshot(
            snapshot_id="test-uuid-001",
            snapshot_time=datetime.now(timezone.utc)
        )
        
        # Tamper with content (change system_status)
        snapshot["system_status"] = "DEGRADED"
        # DO NOT recalculate hash — this simulates tampering
        
        export_data = {
            "metadata": {
                "substation_id": "ALPHA-001",
                "export_time": datetime.now(timezone.utc).isoformat()
            },
            "snapshots": [snapshot]
        }
        
        verifier = SnapshotVerifier(export_data)
        results = verifier.verify_all()
        
        assert results["verified_count"] == 0
        assert results["chain_intact"] is False
        assert len(results["content_hash_failures"]) == 1
        assert "test-uuid-001" in results["content_hash_failures"]
    
    def test_broken_chain_detection(self):
        """Test detection of broken chain linkage."""
        base_time = datetime.now(timezone.utc)
        
        snapshot1 = self.create_valid_snapshot(
            snapshot_id="test-uuid-001",
            snapshot_time=base_time,
            previous_id=None
        )
        
        snapshot2 = self.create_valid_snapshot(
            snapshot_id="test-uuid-002",
            snapshot_time=base_time + timedelta(hours=1),
            previous_id="WRONG-UUID"  # Chain break!
        )
        
        export_data = {
            "metadata": {
                "substation_id": "ALPHA-001",
                "export_time": datetime.now(timezone.utc).isoformat()
            },
            "snapshots": [snapshot1, snapshot2]
        }
        
        verifier = SnapshotVerifier(export_data)
        results = verifier.verify_all()
        
        assert results["chain_intact"] is False
        assert len(results["chain_integrity_failures"]) == 1
    
    def test_time_violation_detection(self):
        """Test detection of non-monotonic timestamps."""
        base_time = datetime.now(timezone.utc)
        
        snapshot1 = self.create_valid_snapshot(
            snapshot_id="test-uuid-001",
            snapshot_time=base_time,
            previous_id=None
        )
        
        # Snapshot 2 has EARLIER timestamp (violation)
        snapshot2 = self.create_valid_snapshot(
            snapshot_id="test-uuid-002",
            snapshot_time=base_time - timedelta(hours=1),  # Earlier!
            previous_id="test-uuid-001"
        )
        
        export_data = {
            "metadata": {
                "substation_id": "ALPHA-001",
                "export_time": datetime.now(timezone.utc).isoformat()
            },
            "snapshots": [snapshot1, snapshot2]
        }
        
        verifier = SnapshotVerifier(export_data)
        results = verifier.verify_all()
        
        assert results["chain_intact"] is False
        assert len(results["time_violations"]) == 1
    
    def test_signature_forgery_detection(self):
        """Test detection of forged signature (modified content + modified hash)."""
        snapshot = self.create_valid_snapshot(
            snapshot_id="test-uuid-001",
            snapshot_time=datetime.now(timezone.utc)
        )
        
        # Tamper with content
        snapshot["system_status"] = "DEGRADED"
        
        # Recalculate content hash (attacker trying to hide tampering)
        canonical = {
            "snapshot_time": snapshot["snapshot_time"],
            "substation_id": snapshot["substation_id"],
            "system_status": snapshot["system_status"],  # Modified
            "asset_states": snapshot["asset_states"],
            "esp_config": snapshot["esp_config"],
            "patch_metrics": snapshot["patch_metrics"],
            "active_mismatches": []
        }
        canonical_json = json.dumps(canonical, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
        new_content_hash = hashlib.sha256(canonical_json.encode('utf-8')).hexdigest()
        snapshot["content_hash"] = new_content_hash
        
        # DO NOT recalculate signature — signature still binds to OLD content hash
        # This simulates attacker who modified content + content_hash but can't forge signature
        
        export_data = {
            "metadata": {
                "substation_id": "ALPHA-001",
                "export_time": datetime.now(timezone.utc).isoformat()
            },
            "snapshots": [snapshot]
        }
        
        verifier = SnapshotVerifier(export_data)
        results = verifier.verify_all()
        
        assert results["chain_intact"] is False
        assert len(results["signature_hash_failures"]) == 1
    
    def test_empty_chain(self):
        """Test handling of empty snapshot chain."""
        export_data = {
            "metadata": {
                "substation_id": "ALPHA-001",
                "export_time": datetime.now(timezone.utc).isoformat()
            },
            "snapshots": []
        }
        
        verifier = SnapshotVerifier(export_data)
        
        with pytest.raises(VerificationError, match="No snapshots found"):
            verifier.verify_all()


class TestCLIInterface:
    """Test command-line interface."""
    
    def test_cli_success(self):
        """Test CLI with valid snapshot chain."""
        base_time = datetime.now(timezone.utc)
        
        # Create valid chain
        snapshot1 = TestSnapshotVerification().create_valid_snapshot(
            snapshot_id="test-uuid-001",
            snapshot_time=base_time,
            previous_id=None
        )
        
        snapshot2 = TestSnapshotVerification().create_valid_snapshot(
            snapshot_id="test-uuid-002",
            snapshot_time=base_time + timedelta(hours=1),
            previous_id="test-uuid-001"
        )
        
        export_data = {
            "metadata": {
                "substation_id": "ALPHA-001",
                "export_time": datetime.now(timezone.utc).isoformat()
            },
            "snapshots": [snapshot1, snapshot2]
        }
        
        # Write to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(export_data, f)
            temp_file = f.name
        
        try:
            # Run CLI
            result = subprocess.run(
                ["python", "verify_snapshot_chain.py", temp_file],
                capture_output=True,
                text=True
            )
            
            assert result.returncode == 0
            assert "VERIFICATION PASSED" in result.stdout
        finally:
            Path(temp_file).unlink()
    
    def test_cli_failure(self):
        """Test CLI with tampered snapshot."""
        snapshot = TestSnapshotVerification().create_valid_snapshot(
            snapshot_id="test-uuid-001",
            snapshot_time=datetime.now(timezone.utc)
        )
        
        # Tamper with content
        snapshot["system_status"] = "DEGRADED"
        
        export_data = {
            "metadata": {
                "substation_id": "ALPHA-001",
                "export_time": datetime.now(timezone.utc).isoformat()
            },
            "snapshots": [snapshot]
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(export_data, f)
            temp_file = f.name
        
        try:
            result = subprocess.run(
                ["python", "verify_snapshot_chain.py", temp_file],
                capture_output=True,
                text=True
            )
            
            assert result.returncode == 1
            assert "VERIFICATION FAILED" in result.stdout
        finally:
            Path(temp_file).unlink()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
