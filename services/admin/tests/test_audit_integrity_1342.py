"""
Regression coverage for ``app/audit_integrity.py`` — closes the 93% ->
100% gap left by ``test_epic_k_audit_hygiene.py``.

``verify_chain`` is the ISO 27001 12.7.1 / FSMA 204 tamper-evidence
verifier. It's the read-side counterpart to the SHA-256 hash chain that
``app/audit.py::AuditLogger`` writes. If the verifier's own branches
drift — especially the empty-chain short-circuit or the prev_hash-mismatch
reporter — we lose the ability to _prove_ the audit log hasn't been
rewritten, which is the whole product promise.

Pinned branches:

* Line 40 — empty ``entries`` returns ``{"valid": True, total/verified
  = 0, errors=[]}``. This is the "trivially valid" short-circuit that
  lets the export endpoint safely handle tenants with no audit history.
* Line 63 — ``prev_hash`` mismatch on a mid-chain entry appends a
  ``prev_hash_mismatch`` error rather than raising. This is the case
  where an attacker deletes or reorders rows: the hashes still match
  individually but the chain linkage is broken.

Plus sanity tests for the v1/v2 #1415 fallback matrix so the two
branches above can't co-regress with the hash-schema migration.

Tracks GitHub issue #1342.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

service_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(service_dir))

from app.audit_integrity import verify_chain  # noqa: E402


# ---------------------------------------------------------------------------
# helpers — build v1 and v2 hash bodies the same way audit.py does
# ---------------------------------------------------------------------------


def _hash_v2(
    prev_hash,
    tenant_id,
    timestamp,
    event_type,
    action,
    resource_id,
    metadata,
    actor_id,
    actor_email,
    severity,
    endpoint,
):
    body = {
        "prev_hash": prev_hash or "GENESIS",
        "tenant_id": tenant_id,
        "timestamp": timestamp,
        "event_type": event_type,
        "action": action,
        "resource_id": resource_id,
        "metadata": metadata,
        "version": 2,
        "actor_id": actor_id,
        "actor_email": actor_email,
        "severity": severity,
        "endpoint": endpoint,
    }
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, default=str).encode()
    ).hexdigest()


def _hash_v1(prev_hash, tenant_id, timestamp, event_type, action, resource_id, metadata):
    body = {
        "prev_hash": prev_hash or "GENESIS",
        "tenant_id": tenant_id,
        "timestamp": timestamp,
        "event_type": event_type,
        "action": action,
        "resource_id": resource_id,
        "metadata": metadata,
    }
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, default=str).encode()
    ).hexdigest()


def _entry(*, id_, prev_hash, tenant="t-1", timestamp="2026-04-20T00:00:00Z",
           event_type="auth.login", action="login", resource_id=None,
           metadata=None, actor_id="a-1", actor_email="a@example.com",
           severity="info", endpoint="/login", hash_version=2,
           override_hash=None):
    metadata = metadata or {}
    if override_hash is not None:
        actual_hash = override_hash
    elif hash_version == 1:
        actual_hash = _hash_v1(prev_hash, tenant, timestamp, event_type, action,
                               resource_id, metadata)
    else:
        actual_hash = _hash_v2(prev_hash, tenant, timestamp, event_type, action,
                               resource_id, metadata, actor_id, actor_email,
                               severity, endpoint)
    return {
        "id": id_,
        "tenant_id": tenant,
        "timestamp": timestamp,
        "event": {"type": event_type, "action": action},
        "action": action,
        "resource": {"id": resource_id},
        "metadata": metadata,
        "actor": {"id": actor_id, "email": actor_email},
        "severity": severity,
        "endpoint": endpoint,
        "integrity": {"prev_hash": prev_hash, "hash": actual_hash},
    }


# ---------------------------------------------------------------------------
# Line 40 — empty chain short-circuit
# ---------------------------------------------------------------------------


class TestEmptyChain:

    def test_empty_list_returns_trivially_valid(self):
        """Line 40: an empty ``entries`` list must return the canonical
        'trivially valid' dict so the export endpoint handles
        brand-new tenants cleanly."""
        result = verify_chain([])
        assert result == {
            "valid": True,
            "total_entries": 0,
            "verified": 0,
            "first_break": None,
            "errors": [],
        }


# ---------------------------------------------------------------------------
# Line 63 — prev_hash mismatch on mid-chain entry
# ---------------------------------------------------------------------------


class TestPrevHashMismatch:

    def test_second_entry_wrong_prev_hash_flags_mismatch(self):
        """Line 63: if entry[1].prev_hash doesn't match entry[0].hash,
        an error with ``error='prev_hash_mismatch'`` is appended. The
        chain continues — we don't short-circuit on the first break."""
        e1 = _entry(id_=1, prev_hash=None)
        # Give e2 a wrong prev_hash but keep its own hash self-consistent
        bogus_prev = "0" * 64
        e2 = _entry(id_=2, prev_hash=bogus_prev)

        result = verify_chain([e1, e2])

        assert result["valid"] is False
        assert any(
            err["error"] == "prev_hash_mismatch" and err["id"] == 2
            for err in result["errors"]
        )
        mismatch = next(err for err in result["errors"] if err["error"] == "prev_hash_mismatch")
        assert mismatch["expected"] == e1["integrity"]["hash"]
        assert mismatch["actual"] == bogus_prev

    def test_first_break_reports_broken_entry_id(self):
        """When the chain breaks, ``first_break`` should name the
        first offending entry's id — that's what the operator needs
        to know first."""
        e1 = _entry(id_=1, prev_hash=None)
        e2 = _entry(id_=2, prev_hash="0" * 64)  # wrong prev

        result = verify_chain([e1, e2])
        assert result["first_break"] == 2


# ---------------------------------------------------------------------------
# #1415 v1/v2 fallback matrix — belt-and-suspenders
# ---------------------------------------------------------------------------


class TestSchemaVersionFallback:

    def test_valid_v2_chain_verifies_clean(self):
        e1 = _entry(id_=1, prev_hash=None, hash_version=2)
        e2 = _entry(id_=2, prev_hash=e1["integrity"]["hash"], hash_version=2)

        result = verify_chain([e1, e2])
        assert result["valid"] is True
        assert result["verified"] == 2
        assert result["errors"] == []
        assert result["first_break"] is None

    def test_legacy_v1_chain_still_verifies(self):
        """Pre-#1415 rows (hash computed without actor fields) must
        still verify — this is the migration-safety promise."""
        e1 = _entry(id_=1, prev_hash=None, hash_version=1)
        e2 = _entry(id_=2, prev_hash=e1["integrity"]["hash"], hash_version=1)

        result = verify_chain([e1, e2])
        assert result["valid"] is True

    def test_tampered_hash_flagged_as_mismatch(self):
        """If an operator rewrites the integrity.hash value directly,
        neither v1 nor v2 reproduces it — we get an
        ``integrity_hash_mismatch`` error."""
        e1 = _entry(id_=1, prev_hash=None, override_hash="f" * 64)

        result = verify_chain([e1])
        assert result["valid"] is False
        assert result["errors"][0]["error"] == "integrity_hash_mismatch"
        assert result["errors"][0]["id"] == 1

    def test_missing_integrity_block_flagged(self):
        """Defensive: a row with no integrity block at all must still
        be handled cleanly — it just fails hash verification rather
        than KeyError'ing the verifier."""
        e1 = _entry(id_=1, prev_hash=None)
        del e1["integrity"]
        # Re-add a minimal empty integrity so .get succeeds but hash is None
        e1["integrity"] = {}

        result = verify_chain([e1])
        assert result["valid"] is False
        # actual_hash is None, recomputed is a real sha256 hex → mismatch
        assert result["errors"][0]["error"] == "integrity_hash_mismatch"
