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
                 ordered by (tenant_id, sequence_num) ASC. Each entry must have:
                 - tenant_id: str
                 - timestamp: str (ISO 8601)
                 - event.type: str
                 - event.action: str
                 - resource.id: str | None
                 - metadata: dict
                 - integrity.prev_hash: str | None
                 - integrity.hash: str
                 - integrity.sequence_num: int | None  (#2513)

    Returns:
        {
            "valid": bool,
            "total_entries": int,
            "verified": int,
            "first_break": int | None,  # entry id where chain breaks
            "errors": [{"id": ..., "error": ..., "expected": ..., "actual": ...}],
            "legacy_v1_rows": [id, ...],  # ids verified only under the v1 hash
            "has_legacy_v1_rows": bool,   # any row lacks actor-field tamper-evidence
        }

    #2523: a row that verifies only under the v1 fallback lacks actor-field
    (actor_id/actor_email/severity/endpoint) tamper-evidence — a DB-write
    attacker can rewrite those "who did this" fields on a pre-#1415 row and
    the chain still reports valid. We now record each such row's id in
    ``legacy_v1_rows`` (and set ``has_legacy_v1_rows``) so the marker
    propagates into the auditor-facing export instead of being invisible.
    """
    if not entries:
        return {
            "valid": True,
            "total_entries": 0,
            "verified": 0,
            "first_break": None,
            "errors": [],
            "legacy_v1_rows": [],
            "has_legacy_v1_rows": False,
        }

    errors = []
    legacy_v1_rows: List = []
    # Per-tenant chain state: each tenant has its own hash chain and
    # sequence counter, since entries may span tenants in
    # (tenant_id, sequence_num) order. A single global tracker would
    # compare one tenant's rows against another's and report false
    # breaks at every tenant boundary.
    expected_prev_by_tenant = {}
    # #2513: track the previous entry's per-tenant sequence so a gap
    # (a removed/deleted middle row) is flagged with a distinct
    # contiguity error rather than masquerading as a prev_hash_mismatch.
    prev_sequence_by_tenant = {}

    for entry in entries:
        # Extract integrity block
        integrity = entry.get("integrity", {})
        actual_prev = integrity.get("prev_hash")
        actual_hash = integrity.get("hash")
        sequence_num = integrity.get("sequence_num")
        # str() normalizes UUID vs string forms of the same tenant id
        # to one chain; missing tenant ids group under "None".
        tenant_key = str(entry.get("tenant_id"))

        # Verify prev_hash linkage within this tenant's chain
        if tenant_key not in expected_prev_by_tenant:
            # First entry seen for this tenant: prev_hash can be
            # None (genesis)
            expected_prev_by_tenant[tenant_key] = actual_prev
        else:
            if actual_prev != expected_prev_by_tenant[tenant_key]:
                errors.append(
                    {
                        "id": entry.get("id"),
                        "error": "prev_hash_mismatch",
                        "expected": expected_prev_by_tenant[tenant_key],
                        "actual": actual_prev,
                    }
                )

        # #2513: per-tenant sequence contiguity. A gap of more than 1
        # between consecutive sequences means a row was removed; a
        # non-increasing sequence means reordering/duplication. Only
        # checked when both sequences are present (legacy pre-#2513 rows
        # carry sequence_num=None and are exempt from the gap check).
        prev_sequence_num = prev_sequence_by_tenant.get(tenant_key)
        if sequence_num is not None and prev_sequence_num is not None:
            if sequence_num != prev_sequence_num + 1:
                errors.append(
                    {
                        "id": entry.get("id"),
                        "error": "sequence_gap",
                        "expected": prev_sequence_num + 1,
                        "actual": sequence_num,
                    }
                )
        if sequence_num is not None:
            prev_sequence_by_tenant[tenant_key] = sequence_num

        # #1415/#2513: recompute using v3 (actor fields + sequence_num
        # folded in). Fall back to v2 then v1 for entries written before
        # the respective migrations so older chains still verify.
        actor = entry.get("actor", {}) if isinstance(entry.get("actor"), dict) else {}
        base_body = {
            "prev_hash": actual_prev or "GENESIS",
            "tenant_id": entry.get("tenant_id"),
            "timestamp": entry.get("timestamp"),
            "event_type": entry.get("event", {}).get("type"),
            "action": entry.get("event", {}).get("action"),
            "resource_id": entry.get("resource", {}).get("id"),
            "metadata": entry.get("metadata", {}),
        }
        actor_fields = {
            "actor_id": actor.get("id"),
            "actor_email": actor.get("email"),
            "severity": entry.get("severity"),
            "endpoint": entry.get("endpoint"),
        }

        v3_body = {**base_body, "version": 3, **actor_fields, "sequence_num": sequence_num}
        recomputed_v3 = hashlib.sha256(json.dumps(v3_body, sort_keys=True, default=str).encode("utf-8")).hexdigest()

        v2_body = {**base_body, "version": 2, **actor_fields}
        recomputed_v2 = hashlib.sha256(json.dumps(v2_body, sort_keys=True, default=str).encode("utf-8")).hexdigest()

        v1_body = dict(base_body)
        recomputed_v1 = hashlib.sha256(json.dumps(v1_body, sort_keys=True, default=str).encode("utf-8")).hexdigest()

        if actual_hash == recomputed_v3:
            recomputed = recomputed_v3
        elif actual_hash == recomputed_v2:
            # Accept pre-#2513 row (no sequence in hash) but it remains
            # covered by the sequence-gap check above when present.
            recomputed = recomputed_v2
        elif actual_hash == recomputed_v1:
            # Accept legacy row but record it so the v1-only status is
            # surfaced to the caller (and the export) — pre-#1415 rows lack
            # actor-field tamper-evidence (#2523).
            recomputed = recomputed_v1
            legacy_v1_rows.append(entry.get("id"))
        else:
            recomputed = recomputed_v3

        if recomputed != actual_hash:
            errors.append(
                {
                    "id": entry.get("id"),
                    "error": "integrity_hash_mismatch",
                    "expected": recomputed,
                    "actual": actual_hash,
                }
            )

        # Next entry in this tenant's chain should reference this hash
        expected_prev_by_tenant[tenant_key] = actual_hash

    return {
        "valid": len(errors) == 0,
        "total_entries": len(entries),
        "verified": len(entries) - len(errors),
        "first_break": errors[0]["id"] if errors else None,
        "errors": errors,
        "legacy_v1_rows": legacy_v1_rows,
        "has_legacy_v1_rows": bool(legacy_v1_rows),
    }
