"""
Tests for the tamper-evident audit log system.

Tests:
1. compute_integrity_hash() determinism
2. verify_chain() with valid chain
3. verify_chain() with broken chain
4. verify_chain() with empty chain
5. verify_chain() with corrupt entry
"""

import hashlib
import json
import uuid
from datetime import datetime, timezone

import pytest

# Import the modules under test
import sys
from pathlib import Path

# Add the admin service to path for imports
_admin_dir = Path(__file__).parent.parent.parent / "services" / "admin"
sys.path.insert(0, str(_admin_dir))
# Also add shared for transitive imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "shared"))

from app.audit import compute_integrity_hash
from app.audit_integrity import verify_chain


class TestComputeIntegrityHash:
    """Test the SHA-256 hash computation is deterministic and correct."""

    def test_deterministic(self):
        """Same inputs always produce the same hash."""
        kwargs = {
            "prev_hash": None,
            "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
            "timestamp": "2026-02-07T00:00:00+00:00",
            "event_type": "auth.login",
            "action": "login",
            "resource_id": "user-123",
            "metadata": {"ip": "10.0.0.1"},
        }
        h1 = compute_integrity_hash(**kwargs)
        h2 = compute_integrity_hash(**kwargs)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex digest

    def test_different_inputs_different_hash(self):
        """Different inputs produce different hashes."""
        base = {
            "prev_hash": None,
            "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
            "timestamp": "2026-02-07T00:00:00+00:00",
            "event_type": "auth.login",
            "action": "login",
            "resource_id": "user-123",
            "metadata": {},
        }
        h1 = compute_integrity_hash(**base)
        h2 = compute_integrity_hash(**{**base, "action": "logout"})
        assert h1 != h2

    def test_genesis_uses_string(self):
        """When prev_hash is None, 'GENESIS' is used in the payload."""
        kwargs = {
            "prev_hash": None,
            "tenant_id": "test-tenant",
            "timestamp": "2026-01-01T00:00:00Z",
            "event_type": "system.start",
            "action": "create",
            "resource_id": None,
            "metadata": {},
        }
        h = compute_integrity_hash(**kwargs)
        # Manually compute to verify
        payload = json.dumps(
            {
                "prev_hash": "GENESIS",
                "tenant_id": "test-tenant",
                "timestamp": "2026-01-01T00:00:00Z",
                "event_type": "system.start",
                "action": "create",
                "resource_id": None,
                "metadata": {},
            },
            sort_keys=True,
            default=str,
        )
        expected = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        assert h == expected

    def test_prev_hash_chaining(self):
        """Hash includes prev_hash, proving chain linkage."""
        h1 = compute_integrity_hash(
            prev_hash=None,
            tenant_id="t",
            timestamp="ts",
            event_type="e",
            action="a",
            resource_id=None,
            metadata={},
        )
        h2 = compute_integrity_hash(
            prev_hash=h1,
            tenant_id="t",
            timestamp="ts2",
            event_type="e",
            action="a",
            resource_id=None,
            metadata={},
        )
        assert h1 != h2
        # h2 depends on h1
        h2_different_prev = compute_integrity_hash(
            prev_hash="tampered",
            tenant_id="t",
            timestamp="ts2",
            event_type="e",
            action="a",
            resource_id=None,
            metadata={},
        )
        assert h2 != h2_different_prev


class TestVerifyChain:
    """Test the chain verification logic."""

    def _make_entry(
        self, entry_id, tenant_id, timestamp, event_type, action, resource_id, metadata, prev_hash
    ):
        """Build an entry in the export format with a correct integrity hash."""
        integrity_hash = compute_integrity_hash(
            prev_hash=prev_hash,
            tenant_id=tenant_id,
            timestamp=timestamp,
            event_type=event_type,
            action=action,
            resource_id=resource_id,
            metadata=metadata,
        )
        return {
            "id": entry_id,
            "tenant_id": tenant_id,
            "timestamp": timestamp,
            "event": {
                "type": event_type,
                "action": action,
            },
            "resource": {
                "id": resource_id,
            },
            "metadata": metadata,
            "integrity": {
                "prev_hash": prev_hash,
                "hash": integrity_hash,
            },
        }

    def test_empty_chain(self):
        """Empty chain is valid."""
        result = verify_chain([])
        assert result["valid"] is True
        assert result["total_entries"] == 0

    def test_single_entry(self):
        """Single entry chain is valid."""
        entry = self._make_entry(
            entry_id=1,
            tenant_id="tenant-1",
            timestamp="2026-01-01T00:00:00Z",
            event_type="auth.login",
            action="login",
            resource_id="user-1",
            metadata={"ip": "10.0.0.1"},
            prev_hash=None,
        )
        result = verify_chain([entry])
        assert result["valid"] is True
        assert result["verified"] == 1

    def test_valid_chain(self):
        """Multi-entry chain with correct linkage is valid."""
        entries = []
        prev_hash = None
        for i in range(5):
            entry = self._make_entry(
                entry_id=i + 1,
                tenant_id="tenant-1",
                timestamp=f"2026-01-01T00:0{i}:00Z",
                event_type="data.write",
                action="create",
                resource_id=f"doc-{i}",
                metadata={"index": i},
                prev_hash=prev_hash,
            )
            prev_hash = entry["integrity"]["hash"]
            entries.append(entry)
        result = verify_chain(entries)
        assert result["valid"] is True
        assert result["verified"] == 5
        assert result["first_break"] is None

    def test_broken_chain_hash_tampered(self):
        """Tampering with an integrity hash breaks the chain."""
        entries = []
        prev_hash = None
        for i in range(3):
            entry = self._make_entry(
                entry_id=i + 1,
                tenant_id="tenant-1",
                timestamp=f"2026-01-01T00:0{i}:00Z",
                event_type="data.write",
                action="create",
                resource_id=f"doc-{i}",
                metadata={},
                prev_hash=prev_hash,
            )
            prev_hash = entry["integrity"]["hash"]
            entries.append(entry)

        # Tamper with the second entry's hash
        entries[1]["integrity"]["hash"] = "tampered_hash_value"

        result = verify_chain(entries)
        assert result["valid"] is False
        assert len(result["errors"]) > 0

    def test_broken_chain_prev_hash_mismatch(self):
        """A prev_hash that doesn't match the previous entry's hash is detected."""
        entry1 = self._make_entry(
            entry_id=1,
            tenant_id="tenant-1",
            timestamp="2026-01-01T00:00:00Z",
            event_type="auth.login",
            action="login",
            resource_id="user-1",
            metadata={},
            prev_hash=None,
        )
        entry2 = self._make_entry(
            entry_id=2,
            tenant_id="tenant-1",
            timestamp="2026-01-01T00:01:00Z",
            event_type="auth.logout",
            action="logout",
            resource_id="user-1",
            metadata={},
            prev_hash="wrong_prev_hash",
        )
        result = verify_chain([entry1, entry2])
        assert result["valid"] is False
        assert any(e["error"] == "prev_hash_mismatch" for e in result["errors"])
