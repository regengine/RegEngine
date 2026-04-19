"""Regression tests for NLP consumer tenant_id resolution (#1176).

Before the fix, ``services/nlp/app/consumer.py`` read tenant_id from the
Kafka **payload** only (``evt.get("tenant_id")``) with no fallback to the
header, no UUID validation, and no fail-fast on missing. That meant a
malformed / hostile / legacy message without tenant context would
propagate as ``tenant_id=None`` through the extraction pipeline — and the
downstream writes (graph upsert, review queue insert, task_queue RLS)
would silently lose tenant provenance, potentially writing tenant A's
extractions into tenant B's stores.

These tests exercise ``_resolve_tenant_id`` directly (the new helper) so
the priority rules and rejection semantics are locked in. Full
consumer-loop integration is out of scope — the loop requires a running
Kafka cluster.
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from services.nlp.app.consumer import _resolve_tenant_id


TENANT_A = str(uuid.UUID("11111111-1111-1111-1111-111111111111"))
TENANT_B = str(uuid.UUID("22222222-2222-2222-2222-222222222222"))


class TestHeaderPriority:
    """Kafka header is the authoritative source — set by authenticated producers."""

    def test_header_tenant_used_when_present(self):
        resolved, reason = _resolve_tenant_id(
            header_tenant_id=TENANT_A, payload_tenant_id=None
        )
        assert resolved == TENANT_A
        assert reason is None

    def test_header_wins_over_agreeing_payload(self):
        """Both present and agreeing is the happy path."""
        resolved, reason = _resolve_tenant_id(
            header_tenant_id=TENANT_A, payload_tenant_id=TENANT_A
        )
        assert resolved == TENANT_A
        assert reason is None

    def test_header_wins_case_insensitively(self):
        """UUIDs are case-insensitive per RFC4122; upper/lower mix must pass."""
        resolved, reason = _resolve_tenant_id(
            header_tenant_id=TENANT_A.upper(), payload_tenant_id=TENANT_A.lower()
        )
        assert resolved is not None  # header preserved as-is (upper)
        assert reason is None

    def test_payload_used_when_header_missing(self):
        """Fallback: legacy path with only payload tenant_id still resolves."""
        resolved, reason = _resolve_tenant_id(
            header_tenant_id=None, payload_tenant_id=TENANT_A
        )
        assert resolved == TENANT_A
        assert reason is None


class TestMismatchRejection:
    """Header vs payload disagreement → hostile → reject to DLQ (never proceed)."""

    def test_mismatch_rejects(self):
        """If the producer says tenant A in the header and the payload says B,
        something's wrong — refuse to pick one."""
        resolved, reason = _resolve_tenant_id(
            header_tenant_id=TENANT_A, payload_tenant_id=TENANT_B
        )
        assert resolved is None
        assert reason is not None
        assert "mismatch" in reason.lower()
        # Both values must appear in the reason so SRE can diagnose which
        # producer is lying without re-reading the raw message.
        assert TENANT_A in reason
        assert TENANT_B in reason


class TestMissingRejection:
    """Neither present → the producer didn't set tenant context at all."""

    def test_both_none_rejects(self):
        resolved, reason = _resolve_tenant_id(
            header_tenant_id=None, payload_tenant_id=None
        )
        assert resolved is None
        assert "no_tenant_id" in (reason or "")

    def test_both_empty_string_rejects(self):
        """Empty strings must not count as 'present' — they previously
        propagated as ``tenant_id=''`` which confused downstream filters."""
        resolved, reason = _resolve_tenant_id(
            header_tenant_id="", payload_tenant_id=""
        )
        assert resolved is None
        assert "no_tenant_id" in (reason or "")

    def test_whitespace_only_rejects(self):
        """Tabs, spaces, and newlines are not a tenant_id."""
        resolved, reason = _resolve_tenant_id(
            header_tenant_id="   ", payload_tenant_id="\t\n"
        )
        assert resolved is None
        assert "no_tenant_id" in (reason or "")


class TestSentinelRejection:
    """The ``'default'`` sentinel (from #1268) must be rejected as payload."""

    def test_default_sentinel_in_payload_rejects(self):
        """Even if an old ingestion path wrote ``tenant_id='default'``, we
        must not treat it as a valid tenant. This closes the #1268 bypass."""
        resolved, reason = _resolve_tenant_id(
            header_tenant_id=None, payload_tenant_id="default"
        )
        assert resolved is None
        assert "no_tenant_id" in (reason or "")

    def test_none_string_sentinel_rejects(self):
        """JSON serializers sometimes stringify None — guard against it."""
        resolved, reason = _resolve_tenant_id(
            header_tenant_id=None, payload_tenant_id="None"
        )
        assert resolved is None

    def test_null_string_sentinel_rejects(self):
        resolved, reason = _resolve_tenant_id(
            header_tenant_id=None, payload_tenant_id="null"
        )
        assert resolved is None


class TestFormatValidation:
    """Only well-formed UUIDs pass — anything else is a reject."""

    def test_non_uuid_header_rejects(self):
        """Arbitrary string in the header is not a tenant_id — reject."""
        resolved, reason = _resolve_tenant_id(
            header_tenant_id="tenant-a", payload_tenant_id=None
        )
        assert resolved is None
        assert "invalid_tenant_id_format" in (reason or "")

    def test_non_uuid_payload_rejects(self):
        resolved, reason = _resolve_tenant_id(
            header_tenant_id=None, payload_tenant_id="not-a-uuid-at-all"
        )
        assert resolved is None
        assert "invalid_tenant_id_format" in (reason or "")

    def test_numeric_string_rejects(self):
        resolved, reason = _resolve_tenant_id(
            header_tenant_id=None, payload_tenant_id="42"
        )
        assert resolved is None


class TestRegressionTenantCoexistence:
    """Validate that the fix doesn't break existing legitimate flows."""

    def test_legacy_payload_only_message_still_accepted(self):
        """Many existing producers inject tenant via payload only (legacy).
        Those must keep working so we don't break the ingestion pipeline."""
        resolved, reason = _resolve_tenant_id(
            header_tenant_id=None, payload_tenant_id=TENANT_B
        )
        assert resolved == TENANT_B
        assert reason is None

    def test_new_header_only_message_accepted(self):
        """New producers (post-fix) will use headers. Those must work
        without forcing the payload to also carry the field."""
        resolved, reason = _resolve_tenant_id(
            header_tenant_id=TENANT_B, payload_tenant_id=None
        )
        assert resolved == TENANT_B
        assert reason is None

    def test_strips_whitespace_around_valid_uuid(self):
        """Over-zealous producer pads the UUID — strip and accept."""
        resolved, reason = _resolve_tenant_id(
            header_tenant_id=f"  {TENANT_A}  ", payload_tenant_id=None
        )
        assert resolved == TENANT_A
        assert reason is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
