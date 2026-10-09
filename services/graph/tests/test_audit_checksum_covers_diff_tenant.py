"""Checksum must cover the field diff and the tenant (audit finding 20).

Before the fix, ``FSMAAuditEntry._calculate_checksum`` hashed only the
identity fields, so altering ``diff`` or ``tenant_id`` left
``verify_integrity()`` passing. These tests fail on the old code and pass
on the new code, plus one test pinning the legacy fallback so entries
persisted before the fix still verify after upgrade.
"""

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.fsma_audit import FSMAAuditAction, FSMAAuditDiff, FSMAAuditEntry


def _make_entry(**kwargs):
    kwargs.setdefault("action", FSMAAuditAction.MODIFIED)
    kwargs.setdefault("target_type", "Lot")
    kwargs.setdefault("target_id", "LOT-001")
    kwargs.setdefault("tenant_id", "tenant-a")
    kwargs.setdefault(
        "diff",
        [FSMAAuditDiff(field_name="quantity", previous_value=100, new_value=150)],
    )
    return FSMAAuditEntry(**kwargs)


def test_diff_tampering_breaks_integrity():
    entry = _make_entry()
    assert entry.verify_integrity() is True
    entry.diff[0].new_value = 999
    assert entry.verify_integrity() is False


def test_tenant_tampering_breaks_integrity():
    entry = _make_entry()
    assert entry.verify_integrity() is True
    entry.tenant_id = "tenant-b"
    assert entry.verify_integrity() is False


def test_checksum_covers_diff_and_tenant():
    entry = _make_entry()
    data = {
        "event_id": entry.event_id,
        "actor": entry.actor,
        "action": entry.action.value,
        "timestamp": entry.timestamp,
        "target_type": entry.target_type,
        "target_id": entry.target_id,
        "tenant_id": entry.tenant_id,
        "diff": [d.to_dict() for d in entry.diff],
        "evidence_link": entry.evidence_link,
        "previous_checksum": entry.previous_checksum,
    }
    expected = hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()
    assert entry.checksum == expected


def test_legacy_checksum_still_verifies():
    """Entries persisted before diff/tenant coverage still verify."""
    entry = _make_entry()
    entry.checksum = entry._calculate_legacy_checksum()
    assert entry.verify_integrity() is True
