#!/usr/bin/env python3
"""
RegEngine Verification SDK
Customer-facing tool for independent verification of cryptographic integrity.

This script mirrors the exact hash calculation logic from services/energy/app/crypto.py
to enable customers to independently verify snapshot chain integrity.

Usage:
    python verify_snapshot_chain.py snapshot_export.json
    
Exit Codes:
    0 - All snapshots valid
    1 - Integrity violation detected
    2 - Invalid input file
"""

import hashlib
import json
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional
from pathlib import Path


class VerificationError(Exception):
    """Raised when cryptographic verification fails."""
    pass


class SnapshotVerifier:
    """
    Independent verification engine for RegEngine snapshot chains.
    
    Implements the same cryptographic algorithms as RegEngine backend
    to enable customer-side validation without trusting RegEngine assertions.
    """
    
    def __init__(self, export_data: Dict[str, Any]):
        """
        Initialize verifier with exported snapshot chain.
        
        Args:
            export_data: JSON export from RegEngine /snapshots/export endpoint
        """
        self.export_data = export_data
        self.snapshots = export_data.get("snapshots", [])
        self.metadata = export_data.get("metadata", {})
        self.results = {
            "total_snapshots": len(self.snapshots),
            "verified_count": 0,
            "chain_intact": True,
            "content_hash_failures": [],
            "signature_hash_failures": [],
            "chain_integrity_failures": [],
            "time_violations": []
        }
    
    def verify_all(self) -> Dict[str, Any]:
        """
        Verify entire snapshot chain.
        
        Performs:
        1. Content hash verification (data integrity)
        2. Signature hash verification (binding integrity)
        3. Chain linkage verification (chronological integrity)
        4. Time monotonicity verification
        
        Returns:
            Verification results dictionary
        """
        if not self.snapshots:
            raise VerificationError("No snapshots found in export")
        
        previous_snapshot = None
        
        for idx, snapshot in enumerate(self.snapshots):
            snapshot_id = snapshot.get("id")
            
            try:
                # Check 1: Content hash (data integrity)
                self._verify_content_hash(snapshot)
                
                # Check 2: Signature hash (binding integrity)
                self._verify_signature_hash(snapshot)
                
                # Check 3: Chain linkage (chronological integrity)
                if previous_snapshot:
                    self._verify_chain_linkage(previous_snapshot, snapshot, idx)
                
                # Check 4: Time monotonicity
                if previous_snapshot:
                    self._verify_time_monotonicity(previous_snapshot, snapshot)
                
                self.results["verified_count"] += 1
                previous_snapshot = snapshot
                
            except VerificationError as e:
                # Record failure but continue verification
                print(f"⚠️  Snapshot {idx + 1}/{len(self.snapshots)} ({snapshot_id}): {str(e)}")
                self.results["chain_intact"] = False
        
        return self.results
    
    def _verify_content_hash(self, snapshot: Dict[str, Any]) -> None:
        """
        Verify snapshot content hash matches recalculated hash.
        
        This proves the snapshot content has not been modified since creation.
        Uses the same canonical JSON serialization as RegEngine backend.
        """
        stored_hash = snapshot.get("content_hash")
        if not stored_hash:
            raise VerificationError("Missing content_hash field")
        
        recalculated_hash = self._calculate_content_hash(snapshot)
        
        if recalculated_hash != stored_hash:
            self.results["content_hash_failures"].append(snapshot["id"])
            raise VerificationError(
                f"Content hash mismatch: expected {stored_hash}, got {recalculated_hash}"
            )
    
    def _verify_signature_hash(self, snapshot: Dict[str, Any]) -> None:
        """
        Verify signature hash binds snapshot ID to content.
        
        This proves the database record (ID) is authentically linked to the content.
        """
        stored_signature = snapshot.get("signature_hash")
        if not stored_signature:
            raise VerificationError("Missing signature_hash field")
        
        snapshot_id = snapshot["id"]
        content_hash = snapshot["content_hash"]
        
        recalculated_signature = self._calculate_signature_hash(snapshot_id, content_hash)
        
        if recalculated_signature != stored_signature:
            self.results["signature_hash_failures"].append(snapshot["id"])
            raise VerificationError(
                f"Signature hash mismatch: expected {stored_signature}, got {recalculated_signature}"
            )
    
    def _verify_chain_linkage(
        self, 
        previous: Dict[str, Any], 
        current: Dict[str, Any],
        current_index: int
    ) -> None:
        """
        Verify current snapshot correctly references previous snapshot.
        
        This proves snapshots form an unbroken chain (cannot insert/delete snapshots).
        """
        if current.get("previous_snapshot_id") != previous.get("id"):
            self.results["chain_integrity_failures"].append({
                "snapshot_index": current_index,
                "current_id": current["id"],
                "expected_previous": previous["id"],
                "actual_previous": current.get("previous_snapshot_id")
            })
            raise VerificationError(
                f"Chain break: Current snapshot references {current.get('previous_snapshot_id')}, "
                f"but previous snapshot ID is {previous['id']}"
            )
    
    def _verify_time_monotonicity(
        self, 
        previous: Dict[str, Any], 
        current: Dict[str, Any]
    ) -> None:
        """
        Verify timestamps flow forward (no backdating).
        
        This proves snapshots were created in chronological order.
        """
        prev_time = datetime.fromisoformat(previous["snapshot_time"].replace("Z", "+00:00"))
        curr_time = datetime.fromisoformat(current["snapshot_time"].replace("Z", "+00:00"))
        
        if curr_time <= prev_time:
            self.results["time_violations"].append({
                "current_id": current["id"],
                "previous_time": previous["snapshot_time"],
                "current_time": current["snapshot_time"]
            })
            raise VerificationError(
                f"Time violation: Current snapshot time ({curr_time}) is not after "
                f"previous snapshot time ({prev_time})"
            )
    
    def _calculate_content_hash(self, snapshot: Dict[str, Any]) -> str:
        """
        Calculate SHA-256 hash of canonical snapshot content.
        
        CRITICAL: This MUST match services/energy/app/crypto.py:calculate_content_hash()
        exactly, or verification will fail on valid snapshots.
        
        Algorithm:
        1. Extract only content fields (not ID, not created_at)
        2. Canonicalize nested dicts (sorted keys, consistent types)
        3. Serialize to JSON (sorted keys, no whitespace)
        4. SHA-256 hash
        """
        # Extract content fields (matches crypto.py lines 46-54)
        canonical = {
            "snapshot_time": snapshot["snapshot_time"],
            "substation_id": snapshot["substation_id"],
            "system_status": snapshot["system_status"],
            "asset_states": self._canonicalize_dict(snapshot["asset_states"]),
            "esp_config": self._canonicalize_dict(snapshot["esp_config"]),
            "patch_metrics": self._canonicalize_dict(snapshot["patch_metrics"]),
            "active_mismatches": sorted(snapshot.get("active_mismatches", []))
        }
        
        # Serialize to canonical JSON (matches crypto.py lines 57-62)
        canonical_json = json.dumps(
            canonical,
            sort_keys=True,
            separators=(',', ':'),
            ensure_ascii=True
        )
        
        # Calculate SHA-256 (matches crypto.py line 65)
        return hashlib.sha256(canonical_json.encode('utf-8')).hexdigest()
    
    def _calculate_signature_hash(self, snapshot_id: str, content_hash: str) -> str:
        """
        Calculate signature hash binding ID to content.
        
        CRITICAL: This MUST match services/energy/app/crypto.py:calculate_signature_hash()
        
        Algorithm (matches crypto.py lines 92-93):
        1. Concatenate snapshot_id and content_hash with colon
        2. SHA-256 hash
        """
        signature_input = f"{snapshot_id}:{content_hash}"
        return hashlib.sha256(signature_input.encode('utf-8')).hexdigest()
    
    def _canonicalize_dict(self, data: Any) -> Any:
        """
        Recursively canonicalize data for deterministic hashing.
        
        CRITICAL: This MUST match services/energy/app/crypto.py:_canonicalize_dict()
        
        Rules (matches crypto.py lines 131-152):
        - Sort all dict keys
        - Recursively process nested dicts/lists
        - Convert datetime to ISO format
        - Preserve all other types
        """
        if isinstance(data, dict):
            return {
                k: self._canonicalize_dict(v)
                for k, v in sorted(data.items())
            }
        elif isinstance(data, list):
            return [self._canonicalize_dict(item) for item in data]
        elif isinstance(data, str):
            # Handle datetime strings (keep as-is, already ISO format)
            return data
        else:
            return data
    
    def print_report(self) -> None:
        """Print human-readable verification report."""
        print("\n" + "="*70)
        print("RegEngine Snapshot Chain Verification Report")
        print("="*70)
        
        print(f"\nExport Metadata:")
        print(f"  Substation ID: {self.metadata.get('substation_id', 'N/A')}")
        print(f"  Export Time: {self.metadata.get('export_time', 'N/A')}")
        print(f"  Total Snapshots: {self.results['total_snapshots']}")
        
        print(f"\nVerification Results:")
        print(f"  Snapshots Verified: {self.results['verified_count']}/{self.results['total_snapshots']}")
        print(f"  Chain Integrity: {'✓ INTACT' if self.results['chain_intact'] else '✗ BROKEN'}")
        
        if self.results["content_hash_failures"]:
            print(f"\n❌ Content Hash Failures ({len(self.results['content_hash_failures'])}):")
            for failure_id in self.results["content_hash_failures"]:
                print(f"     - {failure_id}")
        
        if self.results["signature_hash_failures"]:
            print(f"\n❌ Signature Hash Failures ({len(self.results['signature_hash_failures'])}):")
            for failure_id in self.results["signature_hash_failures"]:
                print(f"     - {failure_id}")
        
        if self.results["chain_integrity_failures"]:
            print(f"\n❌ Chain Integrity Failures ({len(self.results['chain_integrity_failures'])}):")
            for failure in self.results["chain_integrity_failures"]:
                print(f"     - Index {failure['snapshot_index']}: {failure['current_id']}")
        
        if self.results["time_violations"]:
            print(f"\n❌ Time Violations ({len(self.results['time_violations'])}):")
            for violation in self.results["time_violations"]:
                print(f"     - {violation['current_id']}: {violation['current_time']} <= {violation['previous_time']}")
        
        print("\n" + "="*70)
        
        if self.results["chain_intact"] and self.results["verified_count"] == self.results["total_snapshots"]:
            print("✓ VERIFICATION PASSED - All cryptographic checks succeeded")
            print("="*70 + "\n")
            return 0
        else:
            print("✗ VERIFICATION FAILED - Integrity violations detected")
            print("="*70 + "\n")
            return 1


def main():
    """CLI entry point."""
    if len(sys.argv) != 2:
        print("Usage: python verify_snapshot_chain.py <snapshot_export.json>")
        print("\nExample:")
        print("  python verify_snapshot_chain.py ~/Downloads/substation_alpha_export.json")
        sys.exit(2)
    
    export_file = Path(sys.argv[1])
    
    if not export_file.exists():
        print(f"Error: File not found: {export_file}")
        sys.exit(2)
    
    try:
        with open(export_file, 'r') as f:
            export_data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON file: {e}")
        sys.exit(2)
    
    try:
        verifier = SnapshotVerifier(export_data)
        verifier.verify_all()
        exit_code = verifier.print_report()
        sys.exit(exit_code)
    except VerificationError as e:
        print(f"Verification Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
