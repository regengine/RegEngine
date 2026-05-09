"""
Evidence Hashing Module
========================
Deterministic SHA-256 hash computation for evidence payloads.

Critical: Hashing MUST be deterministic to enable tamper detection.
"""

import hashlib
import json
from typing import Dict, Any


def compute_payload_hash(payload: Dict[str, Any]) -> str:
    """
    Compute deterministic SHA-256 hash of evidence payload.
    
    Uses JSON canonical form to ensure consistency:
    - Keys sorted alphabetically
    - No whitespace
    - Consistent encoding
    
    Args:
        payload: Evidence payload dict
        
    Returns:
        SHA-256 hash (hex string)
    """
    # Convert to canonical JSON (sorted keys, no whitespace)
    canonical_json = json.dumps(payload, sort_keys=True, separators=(',', ':'))
    
    # Encode to bytes
    payload_bytes = canonical_json.encode('utf-8')
    
    # Compute SHA-256
    hash_obj = hashlib.sha256(payload_bytes)
    hash_hex = hash_obj.hexdigest()
    
    return hash_hex


def compute_envelope_hash(envelope_data: Dict[str, Any]) -> str:
    """
    Compute hash of entire envelope (excluding current_hash field itself).
    
    Args:
        envelope_data: Envelope dict (without current_hash)
        
    Returns:
        SHA-256 hash (hex string)
    """
    # Remove current_hash if present (can't hash itself)
    envelope_copy = envelope_data.copy()
    envelope_copy.pop('current_hash', None)
    envelope_copy.pop('tamper_detected', None)  # Exclude computed field
    
    return compute_payload_hash(envelope_copy)


def verify_hash(payload: Dict[str, Any], expected_hash: str) -> bool:
    """
    Verify that payload hash matches expected hash.
    
    Args:
        payload: Evidence payload
        expected_hash: Expected SHA-256 hash
        
    Returns:
        True if hashes match
    """
    actual_hash = compute_payload_hash(payload)
    return actual_hash == expected_hash
