"""Tests for per-producer-service signing keys (RE-SEC-004).

These tests exercise the kid-rotation logic added in PR #2261:

* Each producer service holds its OWN HMAC key, looked up by the
  verified ``_producer_service`` body claim.
* A compromised service cannot forge events claiming a *different*
  producer_service — the verification key resolves from the body
  claim, so the only key that satisfies the HMAC is the one bound
  to that claim.
* During rollout, the legacy ``KAFKA_EVENT_SIGNING_KEY`` is honored
  as a fallback so deployments without per-service keys keep working.
* Per-service rotation overlap (``*_PREVIOUS``) accepts envelopes
  signed by the immediately-previous key while ``sign_event`` always
  uses the current key.

The test fixtures use ``monkeypatch`` exclusively — env state is
never mutated globally.
"""

from __future__ import annotations

from typing import Iterator

import pytest

from shared.kafka_auth import (
    BODY_FIELD_PRODUCER_SERVICE,
    ENV_SIGNING_KEY,
    KafkaAuthError,
    sign_event,
    verify_event,
)


# Per-service env vars under test. Mirrors the maps in kafka_auth.py.
ENV_NLP = "KAFKA_SIGNING_KEY_NLP"
ENV_NLP_PREV = "KAFKA_SIGNING_KEY_NLP_PREVIOUS"
ENV_INGESTION = "KAFKA_SIGNING_KEY_INGESTION"
ENV_ADMIN = "KAFKA_SIGNING_KEY_ADMIN"


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Wipe every kafka_auth env var so each test starts from clean."""
    for var in (
        ENV_SIGNING_KEY,
        ENV_NLP,
        ENV_NLP_PREV,
        ENV_INGESTION,
        ENV_ADMIN,
        "KAFKA_SIGNING_KEY_GRAPH",
        "KAFKA_SIGNING_KEY_GRAPH_PREVIOUS",
        "KAFKA_SIGNING_KEY_INGESTION_PREVIOUS",
        "KAFKA_SIGNING_KEY_ADMIN_PREVIOUS",
        "KAFKA_SIGNING_KEY_SCHEDULER",
        "KAFKA_SIGNING_KEY_SCHEDULER_PREVIOUS",
        "KAFKA_SIGNATURE_STRICT",
    ):
        monkeypatch.delenv(var, raising=False)
    yield


PAYLOAD = {"document_id": "doc-1", "tenant_id": "t-1"}


# ---------------------------------------------------------------------------
# 1. Per-service signing: keys are bound by producer_service claim
# ---------------------------------------------------------------------------


def test_per_service_keys_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each service signs/verifies with its own per-service env key."""
    monkeypatch.setenv(ENV_NLP, "key-A-nlp")
    monkeypatch.setenv(ENV_INGESTION, "key-B-ingestion")

    nlp_body, nlp_headers = sign_event(PAYLOAD, producer_service="nlp-service")
    evt, producer = verify_event(nlp_body, nlp_headers, topic="t.nlp")
    assert producer == "nlp-service"
    assert evt[BODY_FIELD_PRODUCER_SERVICE] == "nlp-service"

    ing_body, ing_headers = sign_event(PAYLOAD, producer_service="ingestion-service")
    evt2, producer2 = verify_event(ing_body, ing_headers, topic="t.ingest")
    assert producer2 == "ingestion-service"


def test_mutated_producer_claim_fails_verification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Swapping ``_producer_service`` after signing breaks the HMAC."""
    monkeypatch.setenv(ENV_NLP, "key-A-nlp")
    monkeypatch.setenv(ENV_INGESTION, "key-B-ingestion")

    body, headers = sign_event(PAYLOAD, producer_service="nlp-service")
    body["_producer_service"] = "ingestion-service"

    with pytest.raises(KafkaAuthError) as exc_info:
        verify_event(body, headers, topic="t.nlp")
    # Body/header mismatch is caught before HMAC; either reason proves
    # the swap is rejected.
    assert exc_info.value.reason in {
        "producer_service_header_body_mismatch",
        "signature_mismatch",
    }


# ---------------------------------------------------------------------------
# 2. Cross-service forgery defense: nlp key cannot sign as ingestion
# ---------------------------------------------------------------------------


def test_cross_service_forgery_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An attacker with the nlp key cannot forge an ingestion envelope.

    Setup: a compromised nlp-service holds ``key-A-nlp``. They craft
    an envelope with ``_producer_service=ingestion-service`` and sign
    with the only key they have (``key-A-nlp``). The header
    ``x-producer-service`` is set to ingestion-service to bypass the
    header/body mismatch guard.

    The consumer holds both keys (the legitimate deploy state). On
    verify, it sees ``_producer_service=ingestion-service`` and
    resolves the ingestion key (``key-B-ingestion``) — which does NOT
    match the signature.
    """
    monkeypatch.setenv(ENV_NLP, "key-A-nlp")
    monkeypatch.setenv(ENV_INGESTION, "key-B-ingestion")

    # Step 1: sign with the nlp key but lie about the producer claim.
    # We do this by passing the nlp key explicitly via signing_key,
    # which the resolver honors as an override.
    forged_body, forged_headers = sign_event(
        PAYLOAD,
        producer_service="ingestion-service",
        signing_key="key-A-nlp",
    )

    # Step 2: consumer verifies with env-driven keys (no override).
    # It will look up ingestion-service -> key-B-ingestion, which is
    # NOT what the envelope was signed with, so HMAC compare fails.
    with pytest.raises(KafkaAuthError) as exc_info:
        verify_event(forged_body, forged_headers, topic="t.ingest")
    assert exc_info.value.reason == "signature_mismatch"


# ---------------------------------------------------------------------------
# 3. Legacy fallback: KAFKA_EVENT_SIGNING_KEY alone still works
# ---------------------------------------------------------------------------


def test_legacy_shared_key_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """No per-service vars set; legacy shared key signs and verifies."""
    monkeypatch.setenv(ENV_SIGNING_KEY, "legacy-shared-key")

    body, headers = sign_event(PAYLOAD, producer_service="nlp-service")
    evt, producer = verify_event(body, headers, topic="t.nlp")
    assert producer == "nlp-service"


# ---------------------------------------------------------------------------
# 4. Mixed mode: per-service for some, legacy for others
# ---------------------------------------------------------------------------


def test_mixed_per_service_and_legacy(monkeypatch: pytest.MonkeyPatch) -> None:
    """Per-service NLP key + legacy shared key.

    NLP envelopes go through the per-service key (current path).
    Admin envelopes (no per-service key set) fall through to the
    legacy shared key — Phase-1 / Phase-2 transition state.
    """
    monkeypatch.setenv(ENV_NLP, "key-A-nlp")
    monkeypatch.setenv(ENV_SIGNING_KEY, "legacy-shared-key")

    # NLP signs with its per-service key (key-A-nlp).
    nlp_body, nlp_headers = sign_event(PAYLOAD, producer_service="nlp-service")
    _, p1 = verify_event(nlp_body, nlp_headers, topic="t.nlp")
    assert p1 == "nlp-service"

    # Admin has no per-service key, so signing falls through to the
    # legacy shared key (legacy-shared-key).
    admin_body, admin_headers = sign_event(PAYLOAD, producer_service="admin-service")
    _, p2 = verify_event(admin_body, admin_headers, topic="t.admin")
    assert p2 == "admin-service"


# ---------------------------------------------------------------------------
# 5. Rotation: *_PREVIOUS accepted on verify; sign uses current
# ---------------------------------------------------------------------------


def test_rotation_previous_key_accepted_on_verify(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """During rotation overlap, both current and previous keys verify."""
    # Producer signed an envelope under the OLD key before the rotation.
    monkeypatch.setenv(ENV_NLP, "old-key")
    old_body, old_headers = sign_event(PAYLOAD, producer_service="nlp-service")

    # Consumer is now in the rotation window: current=new-key,
    # previous=old-key. The old envelope must still verify.
    monkeypatch.setenv(ENV_NLP, "new-key")
    monkeypatch.setenv(ENV_NLP_PREV, "old-key")
    _, p = verify_event(old_body, old_headers, topic="t.nlp")
    assert p == "nlp-service"


def test_rotation_sign_uses_current_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """``sign_event`` always uses the current key, not the previous one."""
    monkeypatch.setenv(ENV_NLP, "new-key")
    monkeypatch.setenv(ENV_NLP_PREV, "old-key")

    body, headers = sign_event(PAYLOAD, producer_service="nlp-service")

    # An envelope freshly signed must verify against new-key.
    # If we drop the previous var entirely (post-rotation steady state)
    # it should still verify, proving sign used new-key, not old-key.
    monkeypatch.delenv(ENV_NLP_PREV, raising=False)
    _, p = verify_event(body, headers, topic="t.nlp")
    assert p == "nlp-service"


def test_rotation_old_envelope_rejected_after_window_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After the *_PREVIOUS env is unset, old-key envelopes no longer verify."""
    monkeypatch.setenv(ENV_NLP, "old-key")
    old_body, old_headers = sign_event(PAYLOAD, producer_service="nlp-service")

    # Rotation window closed: current=new-key, previous unset, no legacy.
    monkeypatch.setenv(ENV_NLP, "new-key")
    with pytest.raises(KafkaAuthError) as exc_info:
        verify_event(old_body, old_headers, topic="t.nlp")
    assert exc_info.value.reason == "signature_mismatch"


# ---------------------------------------------------------------------------
# 6. Unknown service + no legacy key
# ---------------------------------------------------------------------------


def test_unknown_service_no_legacy_signing_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Producer with no env mapping and no legacy fallback can't sign."""
    # Nothing in the env at all.
    with pytest.raises(KafkaAuthError) as exc_info:
        sign_event(PAYLOAD, producer_service="totally-unknown-service")
    assert exc_info.value.reason == "signing_key_not_configured"


def test_unknown_service_with_legacy_key_signs_via_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unmapped service still signs via the legacy shared key."""
    monkeypatch.setenv(ENV_SIGNING_KEY, "legacy-shared-key")
    body, headers = sign_event(PAYLOAD, producer_service="brand-new-service")
    _, producer = verify_event(body, headers, topic="t.new")
    assert producer == "brand-new-service"


# ---------------------------------------------------------------------------
# 7. Strict-mode interaction
# ---------------------------------------------------------------------------


def test_strict_mode_raises_when_no_key_anywhere(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Strict + no env key at all => verify raises."""
    # First produce an envelope using an explicit key (so we have something
    # to feed verify), then drop the env entirely.
    body, headers = sign_event(
        PAYLOAD,
        producer_service="nlp-service",
        signing_key="some-key",
    )
    # Env is already empty courtesy of the autouse fixture.
    with pytest.raises(KafkaAuthError) as exc_info:
        verify_event(body, headers, topic="t.nlp", strict=True)
    assert exc_info.value.reason == "signing_key_not_configured"


def test_non_strict_warns_and_passes_when_no_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-strict + no env key => warn and accept (rollout bypass)."""
    body, headers = sign_event(
        PAYLOAD,
        producer_service="nlp-service",
        signing_key="some-key",
    )
    evt, producer = verify_event(body, headers, topic="t.nlp", strict=False)
    assert producer == "nlp-service"
    assert evt[BODY_FIELD_PRODUCER_SERVICE] == "nlp-service"


def test_phase1_zero_behavior_change_legacy_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Phase-1 invariant: with ONLY ``KAFKA_EVENT_SIGNING_KEY`` set,
    producers and consumers behave exactly as before."""
    monkeypatch.setenv(ENV_SIGNING_KEY, "the-old-shared-key")

    for service in (
        "nlp-service",
        "ingestion-service",
        "graph-service",
        "admin-service",
        "scheduler-service",
        "some-uncategorized-service",
    ):
        body, headers = sign_event(PAYLOAD, producer_service=service)
        _, producer = verify_event(body, headers, topic=f"t.{service}")
        assert producer == service
