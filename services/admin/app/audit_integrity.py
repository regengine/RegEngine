"""
Audit Chain Integrity Verifier
ISO 27001: 12.7.1

Recomputes the SHA-256 hash chain and reports any breaks.
Can be used in CI, in the export endpoint, or as a standalone script.
"""

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, List, Optional


def chain_timestamp(value: Any) -> Optional[str]:
    """Return the timestamp string stored in an integrity hash.

    Writers hash ``datetime.now(timezone.utc).isoformat()``, which always
    carries a UTC offset. SQLite hands that column back as a naive datetime,
    so a naive value is read as UTC. Aware values keep the offset they have.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return str(value)


def _as_dict(value: Any) -> Optional[dict]:
    """Return ``value`` when it is a dict. Anything else is not a chain block."""
    if isinstance(value, dict):
        return value
    return None


def verify_chain(
    entries: List[dict],
    *,
    predecessor: Optional[dict] = None,
    missing_anchor: bool = False,
) -> dict:
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
    # One row can fail the link, the sequence, and the hash. Count rows,
    # not error objects, or ``verified`` goes negative.
    broken_indexes: set[int] = set()
    # #2513: track the previous entry's per-tenant sequence so a gap
    # (a removed/deleted middle row) is flagged with a distinct
    # contiguity error rather than masquerading as a prev_hash_mismatch.
    prev_sequence_num = None
    expected_prev_hash = None
    anchored = False
    if isinstance(predecessor, dict):
        pred_integrity = _as_dict(predecessor.get("integrity")) or {}
        expected_prev_hash = pred_integrity.get("hash")
        prev_sequence_num = pred_integrity.get("sequence_num")
        anchored = True

    def fail(index: int, entry: Any, error: str, expected: Any = None, actual: Any = None) -> None:
        broken_indexes.add(index)
        entry_id = entry.get("id") if isinstance(entry, dict) else None
        errors.append(
            {
                "id": entry_id,
                "error": error,
                "expected": expected,
                "actual": actual,
            }
        )

    if missing_anchor and entries:
        fail(
            0,
            entries[0],
            "chain_anchor_missing",
            expected="predecessor row",
            actual=None,
        )

    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            fail(i, entry, "malformed_entry", expected="object", actual=type(entry).__name__)
            continue

        raw_integrity = entry.get("integrity", {})
        raw_event = entry.get("event", {})
        raw_resource = entry.get("resource", {})
        raw_metadata = entry.get("metadata", {})
        integrity = _as_dict(raw_integrity)
        event = _as_dict(raw_event)
        resource = _as_dict(raw_resource)
        metadata = _as_dict(raw_metadata)
        if integrity is None or event is None or resource is None or metadata is None:
            fail(i, entry, "malformed_entry", expected="object", actual="invalid block")
        integrity = integrity or {}
        event = event or {}
        resource = resource or {}
        metadata = metadata or {}

        actual_prev = integrity.get("prev_hash")
        actual_hash = integrity.get("hash")
        sequence_num = integrity.get("sequence_num")

        # Verify prev_hash linkage. A caller that passes ``predecessor``
        # is checking a window, so the first row must link to that parent.
        # Without a predecessor the first row is the start of this slice.
        if i == 0 and not anchored:
            expected_prev_hash = actual_prev
        elif actual_prev != expected_prev_hash:
            fail(i, entry, "prev_hash_mismatch", expected_prev_hash, actual_prev)

        # #2513: per-tenant sequence contiguity. A gap of more than 1
        # between consecutive sequences means a row was removed; a
        # non-increasing sequence means reordering/duplication. Only
        # checked when both sequences are present (legacy pre-#2513 rows
        # carry sequence_num=None and are exempt from the gap check).
        if sequence_num is not None and prev_sequence_num is not None:
            if sequence_num != prev_sequence_num + 1:
                fail(i, entry, "sequence_gap", prev_sequence_num + 1, sequence_num)
        if sequence_num is not None:
            prev_sequence_num = sequence_num

        # #1415/#2513: recompute using v3 (actor fields + sequence_num
        # folded in). Fall back to v2 then v1 for entries written before
        # the respective migrations so older chains still verify.
        actor = entry.get("actor", {}) if isinstance(entry.get("actor"), dict) else {}
        base_body = {
            "prev_hash": actual_prev or "GENESIS",
            "tenant_id": entry.get("tenant_id"),
            "timestamp": entry.get("timestamp"),
            "event_type": event.get("type"),
            "action": event.get("action"),
            "resource_id": resource.get("id"),
            "metadata": metadata,
        }
        # Severity lives at the top level in writer-shaped entries but
        # under ``event.severity`` in export-shaped entries
        # (audit_routes builds ``"event": {..., "severity": ...}``).
        # Without the fallback every export-shaped row recomputes with
        # ``severity=None`` and can never match its stored hash.
        event_block = entry.get("event", {}) if isinstance(entry.get("event"), dict) else {}
        severity = entry.get("severity", event_block.get("severity"))
        actor_fields = {
            "actor_id": actor.get("id"),
            "actor_email": actor.get("email"),
            "severity": severity,
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
            fail(i, entry, "integrity_hash_mismatch", recomputed, actual_hash)

        # Next entry should reference this hash
        expected_prev_hash = actual_hash

    return {
        "valid": len(errors) == 0,
        "total_entries": len(entries),
        "verified": len(entries) - len(broken_indexes),
        "first_break": errors[0]["id"] if errors else None,
        "errors": errors,
        "legacy_v1_rows": legacy_v1_rows,
        "has_legacy_v1_rows": bool(legacy_v1_rows),
    }
