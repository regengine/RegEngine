"""Signature verification must gate BEFORE rate limiting — #2929.

Before this fix both webhook routes called
``_check_stripe_webhook_rate_limit(request)`` as their *first* statement,
ahead of ``_process_stripe_webhook`` (and therefore ahead of
``stripe.Webhook.construct_event``). The bucket was keyed on
``request.client.host``, which behind a shared reverse proxy collapses to
the proxy peer address for every caller at once — Stripe included.

The consequence needed no secret: a few unsigned POSTs per second filled
the one shared 100/60s bucket and every genuine Stripe delivery in that
window got a 429. Stripe backs off, then gives up, and billing state
stops moving: ``invoice.payment_failed`` never sets ``past_due``,
``customer.subscription.deleted`` never sets ``canceled`` (churned tenants
keep paid access), ``invoice.paid`` never restores ``active`` (paying
tenants stay stuck at HTTP 402 behind ``subscription_gate``).

The fix splits the budget in two and reorders the checks:

* Unverified traffic (no signature, bad signature, unparseable body) is
  charged to a per-source-IP bucket AFTER it has been shown not to be
  Stripe. Its collapse is harmless by construction — a verified delivery
  never consumes it.
* Verified traffic is charged to a bucket keyed off the *verified event
  envelope*. Landing anything in that bucket requires an HMAC-SHA256
  signature over the exact request body made with
  ``STRIPE_WEBHOOK_SECRET``, so no client-supplied header participates in
  the key and an anonymous caller cannot consume the budget at all.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional

import pytest
import stripe

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

import services.ingestion.app.stripe_billing.rate_limiting as rl  # noqa: E402
from services.ingestion.app.stripe_billing import (  # noqa: E402
    helpers as helpers_mod,
    routes as routes_mod,
    state as state_mod,
    webhooks as webhooks_mod,
)
from fastapi import HTTPException  # noqa: E402

GOOD_SIG = "t=1,v1=genuine-stripe-signature"
BAD_SIG = "t=1,v1=forged"


class _FakeRequest:
    """Minimal ASGI-request stand-in for the webhook routes."""

    def __init__(
        self,
        ip: str = "198.51.100.42",
        headers: Optional[dict[str, str]] = None,
        body: bytes = b"{}",
    ) -> None:
        self.client = SimpleNamespace(host=ip)
        self.headers = dict(headers or {})
        self._body = body

    async def body(self) -> bytes:
        return self._body


def _install_webhook_stubs(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Stub everything downstream of signature verification.

    Returns the list that handled events are appended to.
    """
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test_2929")
    monkeypatch.setattr(helpers_mod, "_configure_stripe", lambda: None)
    monkeypatch.setattr(state_mod, "_mark_event_seen", lambda _event_id: True)

    handled: list[dict[str, Any]] = []

    async def _handle(event: dict[str, Any]) -> None:
        handled.append(event)

    monkeypatch.setattr(webhooks_mod, "_handle_stripe_event", _handle)

    def _construct_event(payload: Any, sig_header: str, secret: str, **_kw: Any) -> dict[str, Any]:
        # Only a caller holding the webhook secret can produce GOOD_SIG.
        if sig_header != GOOD_SIG:
            raise stripe.error.SignatureVerificationError("bad sig", sig_header=sig_header)
        return {
            "id": f"evt_{len(handled)}",
            "type": "invoice.paid",
            "created": 1_800_000_000,
            "data": {"object": {}},
        }

    monkeypatch.setattr(stripe.Webhook, "construct_event", _construct_event)
    return handled


def _force_in_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the limiter to its in-memory window with fresh state."""
    monkeypatch.setattr(rl, "_redis_failed", True)
    monkeypatch.setattr(rl, "_redis_retry_at", time.time() + 300)
    monkeypatch.setattr(rl, "_rate_buckets", {})


def _signed_request(ip: str = "198.51.100.42", **kwargs: Any) -> _FakeRequest:
    headers = {"Stripe-Signature": GOOD_SIG}
    headers.update(kwargs.pop("headers", {}) or {})
    return _FakeRequest(ip=ip, headers=headers, **kwargs)


class TestUnsignedFloodCannotStarveStripe_Issue2929:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("route", ["stripe_webhooks", "stripe_webhook_legacy"])
    async def test_unsigned_flood_does_not_429_a_signed_delivery(
        self,
        monkeypatch: pytest.MonkeyPatch,
        route: str,
    ) -> None:
        """The acceptance criterion for #2929.

        N unsigned POSTs from one source must not cause a subsequent
        correctly-signed Stripe delivery *from the same peer address* to
        be rejected. Pre-fix the limiter ran first and both shared one
        per-peer bucket, so the genuine delivery got a 429.
        """
        _force_in_memory(monkeypatch)
        monkeypatch.setattr(rl, "_WEBHOOK_RATE_LIMIT", 5)  # unverified budget
        _install_webhook_stubs(monkeypatch)

        endpoint = getattr(routes_mod, route)
        attacker_peer = "198.51.100.42"

        rejected_429 = 0
        for _ in range(12):
            with pytest.raises(HTTPException) as excinfo:
                await endpoint(_FakeRequest(ip=attacker_peer), None)
            assert excinfo.value.status_code in (400, 429), (
                f"unsigned POST should be refused as unsigned (400) or throttled (429), "
                f"got {excinfo.value.status_code}"
            )
            if excinfo.value.status_code == 429:
                rejected_429 += 1

        assert rejected_429 > 0, (
            "the unverified bucket must still throttle a junk flood — "
            "the fix reorders the limiter, it does not remove it"
        )

        # The genuine, signature-verified delivery arriving on the very same
        # peer address must still be processed.
        result = await endpoint(_signed_request(ip=attacker_peer), GOOD_SIG)
        assert result["received"] is True
        assert result["event_type"] == "invoice.paid"

    @pytest.mark.asyncio
    async def test_forged_signature_flood_does_not_429_a_signed_delivery(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Same guarantee for junk that *does* carry a Stripe-Signature.

        A forged signature is charged to the unverified bucket, never to
        the verified one, so it cannot starve real deliveries either.
        """
        _force_in_memory(monkeypatch)
        monkeypatch.setattr(rl, "_WEBHOOK_RATE_LIMIT", 4)
        _install_webhook_stubs(monkeypatch)

        peer = "203.0.113.77"
        for _ in range(10):
            with pytest.raises(HTTPException) as excinfo:
                await routes_mod.stripe_webhooks(
                    _FakeRequest(ip=peer, headers={"Stripe-Signature": BAD_SIG}), BAD_SIG
                )
            assert excinfo.value.status_code in (401, 429)

        result = await routes_mod.stripe_webhooks(_signed_request(ip=peer), GOOD_SIG)
        assert result["received"] is True


class TestVerifiedBucketKey_Issue2929:
    @pytest.mark.asyncio
    async def test_verified_bucket_is_not_keyed_on_peer_or_forwarded_header(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The verified bucket key must come from the verified event only.

        Two consequences are asserted together: the key is not the peer
        address (so a shared proxy cannot collapse genuine traffic into a
        starvable bucket), and it cannot be split or steered by a
        client-supplied ``X-Forwarded-For`` (so it cannot be forged to
        evade the budget either).
        """
        _force_in_memory(monkeypatch)
        monkeypatch.setattr(rl, "_VERIFIED_WEBHOOK_RATE_LIMIT", 3)
        _install_webhook_stubs(monkeypatch)

        # Three signed deliveries, every one from a different peer and with
        # a different spoofed forwarded-for. All three must land in ONE
        # bucket — the event-derived key.
        for i, peer in enumerate(("192.0.2.1", "192.0.2.2", "192.0.2.3")):
            await routes_mod.stripe_webhooks(
                _signed_request(ip=peer, headers={"X-Forwarded-For": f"203.0.113.{i}"}),
                GOOD_SIG,
            )

        with pytest.raises(HTTPException) as excinfo:
            await routes_mod.stripe_webhooks(
                _signed_request(ip="192.0.2.9", headers={"X-Forwarded-For": "203.0.113.9"}),
                GOOD_SIG,
            )
        assert excinfo.value.status_code == 429, (
            "verified traffic must still be bounded; rotating the peer address or "
            "X-Forwarded-For must not mint a fresh verified bucket"
        )

        buckets = list(rl._rate_buckets)
        assert len(buckets) == 1, f"verified traffic must share one event-derived bucket, got {buckets!r}"
        assert "192.0.2." not in str(buckets[0]), "verified bucket key must not contain the peer address"
        assert "203.0.113." not in str(buckets[0]), "verified bucket key must not contain a forwarded-for value"


class TestRateLimitRejectionCounter_Issue2929:
    @pytest.mark.asyncio
    async def test_rejection_increments_exported_counter_naming_the_bucket(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A rejected webhook must increment an exported counter naming the
        resolved bucket key, so throttling is visible rather than silent."""
        _force_in_memory(monkeypatch)
        monkeypatch.setattr(rl, "_WEBHOOK_RATE_LIMIT", 1)
        monkeypatch.setattr(rl, "_rate_limit_rejections", {}, raising=False)
        _install_webhook_stubs(monkeypatch)

        peer = "198.51.100.200"
        for _ in range(3):
            with pytest.raises(HTTPException):
                await routes_mod.stripe_webhooks(_FakeRequest(ip=peer), None)

        counts = rl.rate_limit_rejection_counts()
        assert peer in counts, f"counter must name the resolved bucket key; got {counts!r}"
        assert counts[peer] >= 1

    def test_rejection_counter_cardinality_is_capped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The unverified key is a client IP, i.e. attacker-chosen. The map
        must not grow without bound (cf. #2858)."""
        monkeypatch.setattr(rl, "_rate_limit_rejections", {}, raising=False)
        monkeypatch.setattr(rl, "_MAX_TRACKED_REJECTION_KEYS", 3, raising=False)

        for octet in range(10):
            rl._record_rejection(f"198.51.100.{octet}")

        counts = rl.rate_limit_rejection_counts()
        assert len(counts) == 4, f"3 tracked keys plus the overflow bucket, got {counts!r}"
        assert counts[rl._REJECTION_OVERFLOW_KEY] == 7
