"""
TRUST-CRITICAL: Audit integrity and tamper-evidence.

This module contains the hash chain / HMAC logic that makes audit
records tamper-evident. Changes here risk silent audit chain corruption.
Modify with extreme care and verify with tests/shared/test_audit_logging.py.
"""

import hashlib
import hmac
import json
import logging
import os
from typing import Any, Dict, List, Optional

from shared.audit_logging.schema import AuditEvent

logger = logging.getLogger(__name__)


class AuditIntegrity:
    """Ensure audit log integrity with hash chains."""

    def __init__(self, secret_key: Optional[str] = None):
        """Initialize integrity checker.

        Args:
            secret_key: Secret key for HMAC (uses env var if not provided)
        """
        resolved = secret_key or os.environ.get("AUDIT_INTEGRITY_KEY")
        if not resolved:
            raise ValueError(
                "Audit integrity key is required. Set the AUDIT_INTEGRITY_KEY "
                "environment variable or pass secret_key explicitly."
            )
        self._secret_key = resolved.encode()
        self._last_hash: Optional[str] = None

    def compute_hash(self, event: AuditEvent) -> str:
        """Compute integrity hash for an event.

        Args:
            event: Audit event to hash

        Returns:
            Hex-encoded HMAC hash
        """
        # Create canonical representation (excluding hash fields)
        canonical = {
            "event_id": event.event_id,
            "timestamp": event.timestamp.isoformat(),
            "event_type": event.event_type.value,
            "category": event.category.value,
            "actor": event.actor.to_dict(),
            "action": event.action,
            "outcome": event.outcome,
            "previous_hash": event.previous_hash,
        }

        if event.resource:
            canonical["resource"] = event.resource.to_dict()
        if event.details:
            canonical["details"] = event.details

        data = json.dumps(canonical, sort_keys=True, default=str)

        return hmac.new(
            self._secret_key,
            data.encode(),
            hashlib.sha256
        ).hexdigest()

    def sign_event(self, event: AuditEvent) -> AuditEvent:
        """Sign an event with integrity hash.

        Args:
            event: Event to sign

        Returns:
            Event with integrity hash set
        """
        event.previous_hash = self._last_hash
        event.integrity_hash = self.compute_hash(event)
        self._last_hash = event.integrity_hash
        return event

    def verify_event(self, event: AuditEvent) -> bool:
        """Verify an event's integrity.

        Args:
            event: Event to verify

        Returns:
            True if integrity hash is valid
        """
        if not event.integrity_hash:
            return False

        expected = self.compute_hash(event)
        return hmac.compare_digest(event.integrity_hash, expected)

    def verify_chain(self, events: List[AuditEvent]) -> bool:
        """Verify integrity of an event chain.

        Args:
            events: List of events in order

        Returns:
            True if chain is valid
        """
        if not events:
            return True

        previous_hash = None

        for event in events:
            # Check previous hash reference
            if event.previous_hash != previous_hash:
                logger.warning(
                    "Audit chain broken at event %s",
                    event.event_id,
                )
                return False

            # Verify event integrity
            if not self.verify_event(event):
                logger.warning(
                    "Audit event integrity failed: %s",
                    event.event_id,
                )
                return False

            previous_hash = event.integrity_hash

        return True


def verify_audit_chain(
    events: List[AuditEvent],
    integrity: Optional[AuditIntegrity] = None,
) -> Dict[str, Any]:
    """
    Verify hash-chain integrity for a sequence of audit log entries.

    Each audit entry contains an ``integrity_hash`` computed over its contents
    plus a ``previous_hash`` that references the preceding entry's hash.
    This function walks the chain and detects:

    1. **Hash tampering** -- an entry's ``integrity_hash`` does not match a
       fresh recomputation of its canonical fields.
    2. **Chain breaks** -- an entry's ``previous_hash`` does not match the
       ``integrity_hash`` of its predecessor.
    3. **Missing hashes** -- an entry has no ``integrity_hash`` at all.

    Args:
        events: Ordered list of ``AuditEvent`` objects (oldest first).
        integrity: Optional ``AuditIntegrity`` instance for HMAC
            verification.  If ``None``, a default instance is created.

    Returns:
        Dict with:
            - ``total_entries`` (int): Number of entries examined.
            - ``is_valid`` (bool): ``True`` if the entire chain is intact.
            - ``tampered_entries`` (list[dict]): Details for each
              violation found, with ``event_id``, ``index``, and
              ``issue`` keys.
    """
    if integrity is None:
        integrity = AuditIntegrity()

    tampered: List[Dict[str, Any]] = []

    if not events:
        return {
            "total_entries": 0,
            "is_valid": True,
            "tampered_entries": [],
        }

    previous_hash: Optional[str] = None

    for i, event in enumerate(events):
        # Check 1: integrity_hash must be present.
        if not event.integrity_hash:
            tampered.append({
                "event_id": event.event_id,
                "index": i,
                "issue": "missing_integrity_hash",
            })
            previous_hash = None
            continue

        # Check 2: previous_hash must reference predecessor.
        if event.previous_hash != previous_hash:
            tampered.append({
                "event_id": event.event_id,
                "index": i,
                "issue": "chain_link_broken",
                "expected_previous": previous_hash,
                "actual_previous": event.previous_hash,
            })

        # Check 3: recompute the HMAC and compare.
        if not integrity.verify_event(event):
            tampered.append({
                "event_id": event.event_id,
                "index": i,
                "issue": "hash_mismatch",
            })

        previous_hash = event.integrity_hash

    return {
        "total_entries": len(events),
        "is_valid": len(tampered) == 0,
        "tampered_entries": tampered,
    }
