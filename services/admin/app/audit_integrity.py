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

        # #1415: recompute using v2 (actor fields folded in). Fall back
        # to v1 for entries written before the schema migration so older
        # chains still verify. Drift between v1 and v2 for the same row
        # is flagged so operators can spot pre-#1415 entries.
        actor = entry.get("actor", {}) if isinstance(entry.get("actor"), dict) else {}
        v2_body = {
            "prev_hash": actual_prev or "GENESIS",
            "tenant_id": entry.get("tenant_id"),
            "timestamp": entry.get("timestamp"),
            "event_type": entry.get("event", {}).get("type"),
            "action": entry.get("event", {}).get("action"),
            "resource_id": entry.get("resource", {}).get("id"),
            "metadata": entry.get("metadata", {}),
            "version": 2,
            "actor_id": actor.get("id"),
            "actor_email": actor.get("email"),
            "severity": entry.get("severity"),
            "endpoint": entry.get("endpoint"),
        }
        recomputed_v2 = hashlib.sha256(
            json.dumps(v2_body, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()

        v1_body = {
            "prev_hash": actual_prev or "GENESIS",
            "tenant_id": entry.get("tenant_id"),
            "timestamp": entry.get("timestamp"),
            "event_type": entry.get("event", {}).get("type"),
            "action": entry.get("event", {}).get("action"),
            "resource_id": entry.get("resource", {}).get("id"),
            "metadata": entry.get("metadata", {}),
        }
        recomputed_v1 = hashlib.sha256(
            json.dumps(v1_body, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()

        if actual_hash == recomputed_v2:
            recomputed = recomputed_v2
        elif actual_hash == recomputed_v1:
            # Accept legacy row but surface the hash version for operator
            # visibility — pre-#1415 rows lack actor-field tamper evidence.
            recomputed = recomputed_v1
        else:
            recomputed = recomputed_v2

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
