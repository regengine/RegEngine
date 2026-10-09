"""Regression coverage: ``verify_chain`` must verify per-tenant chains.

The docstring promises entries ordered by ``(tenant_id, sequence_num)``,
so multi-tenant input is in contract. The verifier previously kept a
single global ``expected_prev_hash`` / ``prev_sequence_num`` across all
entries, so the first row of the second tenant always reported a
``prev_hash_mismatch`` (and usually a ``sequence_gap``) even when both
tenants' chains were healthy.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

service_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(service_dir))

from app.audit_integrity import verify_chain  # noqa: E402


def _hash(prev_hash, tenant, seq):
    body = {
        "prev_hash": prev_hash or "GENESIS",
        "tenant_id": tenant,
        "timestamp": f"2026-01-01T00:00:{seq:02d}Z",
        "event_type": "data.write",
        "action": "create",
        "resource_id": None,
        "metadata": {},
        "version": 3,
        "actor_id": None,
        "actor_email": None,
        "severity": "info",
        "endpoint": None,
        "sequence_num": seq,
    }
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _entry(*, id_, tenant, seq, prev_hash):
    return {
        "id": id_,
        "tenant_id": tenant,
        "timestamp": f"2026-01-01T00:00:{seq:02d}Z",
        "event": {"type": "data.write", "action": "create"},
        "resource": {"id": None},
        "metadata": {},
        "actor": {"id": None, "email": None},
        "severity": "info",
        "endpoint": None,
        "integrity": {"prev_hash": prev_hash, "hash": _hash(prev_hash, tenant, seq), "sequence_num": seq},
    }


def _two_tenant_chain():
    a1 = _entry(id_=1, tenant="tenant-a", seq=1, prev_hash=None)
    a2 = _entry(id_=2, tenant="tenant-a", seq=2, prev_hash=a1["integrity"]["hash"])
    b1 = _entry(id_=3, tenant="tenant-b", seq=1, prev_hash=None)
    b2 = _entry(id_=4, tenant="tenant-b", seq=2, prev_hash=b1["integrity"]["hash"])
    return [a1, a2, b1, b2]


class TestVerifyChainTenantGrouping:
    def test_healthy_multi_tenant_chain_is_valid(self):
        """Two healthy per-tenant chains in ``(tenant_id, sequence_num)``
        order must verify clean, with no cross-tenant linkage errors."""
        result = verify_chain(_two_tenant_chain())
        assert result["valid"] is True, result
        assert result["errors"] == []

    def test_break_in_one_tenant_does_not_taint_other(self):
        """A broken linkage in tenant-b must be reported against
        tenant-b's entry only, while tenant-a's rows stay clean."""
        entries = _two_tenant_chain()
        entries[3]["integrity"]["prev_hash"] = "0" * 64
        result = verify_chain(entries)
        assert result["valid"] is False
        # Every error must belong to tenant-b's tampered row; the
        # tampered prev also invalidates that row's own hash, so two
        # errors on id 4 is correct.
        assert {e["id"] for e in result["errors"]} == {4}
        assert any(e["error"] == "prev_hash_mismatch" for e in result["errors"])
        assert result["first_break"] == 4

    def test_sequence_gap_is_per_tenant(self):
        """A removed middle row in tenant-b must flag a sequence gap
        measured against tenant-b's own prior row, not a cross-tenant
        comparison (which previously reported expected 3, actual 3)."""
        entries = _two_tenant_chain()
        a1, a2, b1, _b2 = entries
        # tenant-b seq 2 removed: b3 chains directly off b1 with a
        # self-consistent hash, so only the contiguity check fires.
        b3 = _entry(id_=5, tenant="tenant-b", seq=3, prev_hash=b1["integrity"]["hash"])
        result = verify_chain([a1, a2, b1, b3])
        assert result["valid"] is False
        # Only tenant-b's gap row reports; the old global tracker also
        # flagged tenant-b's first row against tenant-a's sequence.
        assert len(result["errors"]) == 1
        gap = result["errors"][0]
        assert gap["error"] == "sequence_gap"
        assert gap["id"] == 5
        assert gap["expected"] == 2
        assert gap["actual"] == 3
