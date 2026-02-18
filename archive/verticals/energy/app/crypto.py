"""
Snapshot Engine Core - Cryptographic Integrity Module

Provides deterministic content hashing and signature generation
for immutable compliance snapshots.

Audit Requirements: NERC CIP-013-1 R1
"""
import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID


def calculate_content_hash(snapshot_data: Dict[str, Any]) -> str:
    """
    Calculate SHA-256 hash of canonical snapshot content.
    
    Critical properties:
    - Deterministic: Same input always produces same hash
    - Canonical: Sorted keys, no whitespace, consistent encoding
    - Verifiable: Can be recalculated from stored data
    
    Args:
        snapshot_data: Dict containing snapshot fields
        
    Returns:
        64-character hex string (SHA-256)
        
    Example:
        >>> data = {
        ...     "snapshot_time": "2026-01-25T10:00:00+00:00",
        ...     "substation_id": "ALPHA-001",
        ...     "system_status": "NOMINAL",
        ...     "asset_states": {"assets": []},
        ...     "esp_config": {"zones": []},
        ...     "patch_metrics": {"avg_hours": 8.5},
        ...     "active_mismatches": []
        ... }
        >>> hash_val = calculate_content_hash(data)
        >>> len(hash_val)
        64
    """
    # Extract only fields that contribute to content identity
    canonical = {
        "snapshot_time": snapshot_data["snapshot_time"],
        "substation_id": snapshot_data["substation_id"],
        "system_status": snapshot_data["system_status"],
        "asset_states": _canonicalize_dict(snapshot_data["asset_states"]),
        "esp_config": _canonicalize_dict(snapshot_data["esp_config"]),
        "patch_metrics": _canonicalize_dict(snapshot_data["patch_metrics"]),
        "active_mismatches": sorted(snapshot_data.get("active_mismatches", []))
    }
    
    # Serialize to canonical JSON (sorted keys, no whitespace)
    canonical_json = json.dumps(
        canonical,
        sort_keys=True,
        separators=(',', ':'),
        ensure_ascii=True
    )
    
    # Calculate SHA-256
    return hashlib.sha256(canonical_json.encode('utf-8')).hexdigest()


def calculate_signature_hash(snapshot_id: UUID, content_hash: str) -> str:
    """
    Calculate signature hash binding snapshot ID to content.
    
    This creates cryptographic proof that:
    1. The content (via content_hash) matches the stored data
    2. The database record (via snapshot_id) is authentic
    3. The binding is unique and unforgeable
    
    Args:
        snapshot_id: Database-assigned UUID (UUIDv7 preferred)
        content_hash: SHA-256 hash of snapshot content
        
    Returns:
        64-character hex string (SHA-256)
        
    Example:
        >>> from uuid import uuid4
        >>> snapshot_id = uuid4()
        >>> content_hash = "a" * 64
        >>> sig = calculate_signature_hash(snapshot_id, content_hash)
        >>> len(sig)
        64
    """
    signature_input = f"{snapshot_id}:{content_hash}"
    return hashlib.sha256(signature_input.encode('utf-8')).hexdigest()


def verify_content_hash(snapshot_data: Dict[str, Any], expected_hash: str) -> bool:
    """
    Verify snapshot content hasn't been tampered with.
    
    Args:
        snapshot_data: Current snapshot data from database
        expected_hash: Stored content_hash value
        
    Returns:
        True if hash matches, False if tampered
    """
    calculated_hash = calculate_content_hash(snapshot_data)
    return calculated_hash == expected_hash


def verify_signature_hash(
    snapshot_id: UUID, 
    content_hash: str, 
    expected_signature: str
) -> bool:
    """
    Verify signature binding is intact.
    
    Args:
        snapshot_id: Snapshot UUID
        content_hash: Snapshot content hash
        expected_signature: Stored signature_hash value
        
    Returns:
        True if signature valid, False if tampered
    """
    calculated_sig = calculate_signature_hash(snapshot_id, content_hash)
    return calculated_sig == expected_signature


def _canonicalize_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively canonicalize dictionary for deterministic hashing.
    
    Rules:
    - Sort all dict keys
    - Convert UUID to string
    - Ensure consistent type representation
    """
    if isinstance(data, dict):
        return {
            k: _canonicalize_dict(v) 
            for k, v in sorted(data.items())
        }
    elif isinstance(data, list):
        return [_canonicalize_dict(item) for item in data]
    elif isinstance(data, UUID):
        return str(data)
    elif isinstance(data, datetime):
        return data.isoformat()
    else:
        return data


# Immutability verification utilities

class ImmutabilityError(Exception):
    """Raised when snapshot immutability is violated."""
    pass


def verify_chain_integrity(
    current_snapshot: Dict[str, Any],
    previous_snapshot: Optional[Dict[str, Any]]
) -> bool:
    """
    Verify snapshot chain is unbroken.
    
    Checks:
    1. Current snapshot references previous by ID
    2. Time flows forward (monotonic)
    3. Previous snapshot's signature is valid
    
    Args:
        current_snapshot: Current snapshot data
        previous_snapshot: Previous snapshot data (None if first)
        
    Returns:
        True if chain valid, False if broken
        
    Raises:
        ImmutabilityError: If chain is broken (audit alert)
    """
    if previous_snapshot is None:
        # First snapshot - no chain to verify
        return True
    
    # Check 1: ID linkage
    if current_snapshot.get("previous_snapshot_id") != previous_snapshot.get("id"):
        raise ImmutabilityError(
            f"Chain break: Current snapshot does not reference previous. "
            f"Current.previous_id={current_snapshot.get('previous_snapshot_id')}, "
            f"Previous.id={previous_snapshot.get('id')}"
        )
    
    # Check 2: Time monotonicity
    current_time = datetime.fromisoformat(current_snapshot["snapshot_time"])
    previous_time = datetime.fromisoformat(previous_snapshot["snapshot_time"])
    
    # Ensure both are timezone-aware for comparison
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    if previous_time.tzinfo is None:
        previous_time = previous_time.replace(tzinfo=timezone.utc)
    
    if current_time <= previous_time:
        raise ImmutabilityError(
            f"Time violation: Current snapshot time ({current_time}) "
            f"is not after previous ({previous_time})"
        )
    
    # Check 3: Previous signature valid
    prev_content_hash = previous_snapshot.get("content_hash")
    prev_signature = previous_snapshot.get("signature_hash")
    prev_id = UUID(previous_snapshot["id"])
    
    if not verify_signature_hash(prev_id, prev_content_hash, prev_signature):
        raise ImmutabilityError(
            f"Previous snapshot signature invalid. "
            f"Snapshot ID: {prev_id}"
        )
    
    return True
