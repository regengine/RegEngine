"""
Audit Chain Integrity Verifier
ISO 27001: 12.7.1

Recomputes the SHA-256 hash chain and reports any breaks.
Can be used in CI, in the export endpoint, or as a standalone script.
"""

import hashlib
import json
from typing import List


def verify_chain(entries: List[dict]) -> dict:
    """
    Verify the integrity hash chain of a list of audit entries.

    Args:
        entries: List of audit log entries (as returned by export endpoint),
                 ordered by id ASC. Each entry must have:
                 - tenant_id: str
                 - timestamp: str (ISO 8601)
                 - event.type: str
                 - event.action: str
                 - resource.id: str | None
                 - metadata: dict
                 - integrity.prev_hash: str | None
                 - integrity.hash: str

    Returns:
        {
            "valid": bool,
            "total_entries": int,
            "verified": int,
            "first_break": int | None,  # entry id where chain breaks
            "errors": [{"id": ..., "error": ..., "expected": ..., "actual": ...}]
        }
    """
    if not entries:
        return {
            "valid": True,
            "total_entries": 0,
            "verified": 0,
            "first_break": None,
            "errors": [],
        }

    errors = []
    expected_prev_hash = None

    for i, entry in enumerate(entries):
        # Extract integrity block
        integrity = entry.get("integrity", {})
        actual_prev = integrity.get("prev_hash")
        actual_hash = integrity.get("hash")

        # Verify prev_hash linkage
        if i == 0:
            # First entry: prev_hash can be None (genesis)
            expected_prev_hash = actual_prev
        else:
            if actual_prev != expected_prev_hash:
                errors.append({
                    "id": entry.get("id"),
                    "error": "prev_hash_mismatch",
                    "expected": expected_prev_hash,
                    "actual": actual_prev,
                })

        # Recompute integrity hash
        payload = json.dumps(
            {
                "prev_hash": actual_prev or "GENESIS",
                "tenant_id": entry.get("tenant_id"),
                "timestamp": entry.get("timestamp"),
                "event_type": entry.get("event", {}).get("type"),
                "action": entry.get("event", {}).get("action"),
                "resource_id": entry.get("resource", {}).get("id"),
                "metadata": entry.get("metadata", {}),
            },
            sort_keys=True,
            default=str,
        )
        recomputed = hashlib.sha256(payload.encode("utf-8")).hexdigest()

        if recomputed != actual_hash:
            errors.append({
                "id": entry.get("id"),
                "error": "integrity_hash_mismatch",
                "expected": recomputed,
                "actual": actual_hash,
            })

        # Next entry should reference this hash
        expected_prev_hash = actual_hash

    return {
        "valid": len(errors) == 0,
        "total_entries": len(entries),
        "verified": len(entries) - len(errors),
        "first_break": errors[0]["id"] if errors else None,
        "errors": errors,
    }
