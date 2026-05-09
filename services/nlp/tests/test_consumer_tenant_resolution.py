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


class TestPayloadAuthoritative:
    """Signed payload is the ONLY authoritative source (RE-SEC-001).

    Kafka headers are not covered by the HMAC — preferring them would let
    a capture+rewrite attacker swap tenants on a signed envelope. The
    header is retained only for cross-trace correlation and as a
    defensive mismatch signal.
    """

    def test_header_alone_is_rejected(self):
        """Header without a signed-body tenant_id MUST NOT be trusted —
        the header is unsigned. This is the RE-SEC-001 attack defense."""
        resolved, reason = _resolve_tenant_id(
            header_tenant_id=TENANT_A, payload_tenant_id=None
        )
        assert resolved is None
        # Either rejected as missing-body or as a mismatch — both are
        # acceptable outcomes; what matters is the header is NEVER
        # promoted to authoritative in isolation.
        assert reason is not None

    def test_agreeing_header_and_payload_resolves_to_payload(self):
        """Both present and agreeing is the happy path; payload is returned."""
        resolved, reason = _resolve_tenant_id(
            header_tenant_id=TENANT_A, payload_tenant_id=TENANT_A
        )
        assert resolved == TENANT_A
        assert reason is None

    def test_case_insensitive_match_passes(self):
        """UUIDs are case-insensitive per RFC4122; upper/lower mix must pass."""
        resolved, reason = _resolve_tenant_id(
            header_tenant_id=TENANT_A.upper(), payload_tenant_id=TENANT_A.lower()
        )
        # Payload is authoritative; resolved is the payload-cased value.
        assert resolved == TENANT_A.lower()
        assert reason is None

    def test_payload_used_when_header_missing(self):
        """Body-only is the standard happy path: signed body, no header."""
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

    def test_default_sentinel_in_payload_with_header_present_rejects(self):
        """F-NLP-8: a header tenant must NOT rescue a missing/sentinel body
        tenant. The body is the only authoritative (signed) source."""
        resolved, reason = _resolve_tenant_id(
            header_tenant_id=TENANT_A,
            payload_tenant_id="default",
        )
        assert resolved is None
        # Explicit reason from the new early-return path.
        assert "no_tenant_id_in_payload" in (reason or "")

    def test_none_payload_with_header_present_rejects_explicitly(self):
        """F-NLP-8: explicit early-return replaces implicit fall-through to
        ``uuid.UUID(None)``."""
        resolved, reason = _resolve_tenant_id(
            header_tenant_id=TENANT_A,
            payload_tenant_id=None,
        )
        assert resolved is None
        assert "no_tenant_id_in_payload" in (reason or "")

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
        """Arbitrary string in the header is not a tenant_id — reject.

        F-NLP-8: when the body is missing/sentinel and only the (untrusted)
        header is set, the function now returns the explicit
        ``no_tenant_id_in_payload`` reason rather than implicitly falling
        through to ``uuid.UUID(None)`` and emitting
        ``invalid_tenant_id_format``. Either reason is a rejection — the
        change just makes the control flow explicit.
        """
        resolved, reason = _resolve_tenant_id(
            header_tenant_id="tenant-a", payload_tenant_id=None
        )
        assert resolved is None
        assert "no_tenant_id_in_payload" in (reason or "")

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

    def test_header_only_message_rejected_post_re_sec_001(self):
        """RE-SEC-001 reversal: header-only messages MUST be rejected.
        Kafka headers are unsigned; the body field is the only authority.
        Producers that previously emitted header-only must also include
        the tenant_id in the signed body."""
        resolved, reason = _resolve_tenant_id(
            header_tenant_id=TENANT_B, payload_tenant_id=None
        )
        assert resolved is None
        assert reason is not None

    def test_strips_whitespace_around_valid_uuid(self):
        """Over-zealous producer pads the UUID in the signed body — strip and accept."""
        resolved, reason = _resolve_tenant_id(
            header_tenant_id=None, payload_tenant_id=f"  {TENANT_A}  "
        )
        assert resolved == TENANT_A
        assert reason is None


class TestReSec001CaptureRewriteDefense:
    """Direct attack-scenario coverage for RE-SEC-001.

    Threat model: a network-adjacent attacker captures a legitimately
    signed envelope from tenant A and rewrites the (unsigned) Kafka
    header ``X-RegEngine-Tenant-ID`` to tenant B before replaying. The
    HMAC over the body still validates because the body is unchanged.
    The NLP consumer must ignore the rewritten header — the signed body
    field is the ONLY tenant authority.
    """

    def test_body_a_header_b_rejects_as_mismatch(self):
        """Body=A, Header=B → mismatch reject. The attacker's rewritten
        header is the disagreement signal. Even if mismatch detection
        were bypassed, the resolver would still return A (body), never B."""
        resolved, reason = _resolve_tenant_id(
            header_tenant_id=TENANT_B,  # attacker-rewritten
            payload_tenant_id=TENANT_A,  # signed body
        )
        assert resolved is None
        assert reason is not None
        assert "mismatch" in reason.lower()
        # Critically: even on the reject path, the attacker's tenant B
        # is NEVER the resolved value.
        assert resolved != TENANT_B

    def test_body_a_no_header_returns_a(self):
        """Body=A, no header → returns A. Standard signed-body path."""
        resolved, reason = _resolve_tenant_id(
            header_tenant_id=None,
            payload_tenant_id=TENANT_A,
        )
        assert resolved == TENANT_A
        assert reason is None

    def test_body_empty_header_b_does_not_promote_header(self):
        """Body sentinel/empty + attacker header=B must NOT return B.

        This is the precise primitive RE-SEC-001 closes: lines 175-176
        of consumer.py strip body sentinels, so a hostile producer who
        sends ``payload.tenant_id = 'default'`` and a header ``B`` could,
        under the old code, get the header promoted to authoritative.
        After the fix: payload_tid is None post-strip, resolved is None,
        and we never touch tenant B's data.
        """
        for sentinel in ("", "default", "None", "null", "   "):
            resolved, reason = _resolve_tenant_id(
                header_tenant_id=TENANT_B,
                payload_tenant_id=sentinel,
            )
            assert resolved is None, (
                f"sentinel={sentinel!r} attacker-promoted header to {resolved!r}"
            )
            assert resolved != TENANT_B
            assert reason is not None

    def test_both_missing_returns_none(self):
        """No header, no body → reject. Already covered by
        TestMissingRejection but restated here as an RE-SEC-001 baseline
        so the contract is locked together."""
        resolved, reason = _resolve_tenant_id(
            header_tenant_id=None, payload_tenant_id=None
        )
        assert resolved is None
        assert reason is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
