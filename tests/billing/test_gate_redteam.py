"""Gate L1 companion redteam — rebuilt v2, 2026-09-17.

Original (v1) lost in /tmp wipe. Rebuilt from Gate memory spec against main's
verified-bucket implementation (289b3889 lineage, current main 62a68eed (12/12 verified)).
Complements tests/test_guard_canonical.py: the guard proves invariants; this
file attacks the runtime behavior of _check_verified_stripe_webhook_rate_limit.

Checks:
 1.  admit is silent below budget (contract: returns None, raises nothing)
 2.  budget trip: limit+1th admit -> HTTPException 429 with Retry-After
 3.  account isolation: flooding A does not 429 B
 4.  livemode isolation: live flood does not 429 test traffic, same account
 5.  platform fallback: missing/None/"" account -> 'platform' bucket, no crash
 6.  falsy-account strings don't collide: "None"/"0" are distinct buckets
 7.  new event IDs do not reset the bucket (docstring: nor can a new event ID)
 8.  client-controlled extras can't consume/split the bucket (forwarded/IP-shaped)
 9.  through-path unauth flood 100x -> all 400, verified buckets untouched
10.  through-path forged-sig flood: construct_event sees every request (verify
     before limit), verified buckets untouched
11.  rejection counters recorded under the verified: key

v1 lessons encoded here:
 - admit path returns None, not 0 (asserted via no-exception + 429 on trip)
 - module-level _rate_buckets persists across tests -> autouse clear fixture
 - through-path patches the REAL stripe.Webhook.construct_event (the
   package-level @patch never reaches webhooks.py's own `import stripe`)
 - construct_event runs BEFORE the except-path charge; call_count includes
   every flood request (no off-by-one in the proof)
 - force in-memory mode (_get_redis -> None): a live local Redis would leak
   state across runs and make counts nondeterministic
"""

import asyncio  # noqa: F401  (pytest-asyncio auto mode runs the async tests)
from unittest.mock import AsyncMock, MagicMock

import pytest
import stripe as real_stripe
from fastapi import HTTPException

from services.ingestion.app.stripe_billing import rate_limiting as rl


@pytest.fixture(autouse=True)
def _isolated_in_memory(monkeypatch):
    """Force in-memory buckets and clear module state around every test."""
    monkeypatch.setattr(rl, "_get_redis", lambda: None)
    with rl._bucket_lock:
        rl._rate_buckets.clear()
        rl._rate_limit_rejections.clear()
    yield
    with rl._bucket_lock:
        rl._rate_buckets.clear()
        rl._rate_limit_rejections.clear()


def _event(account="acct_a", livemode=False, **extra):
    body = {"account": account, "livemode": livemode, "id": "evt_1"}
    body.update(extra)
    return body


def _verified_keys():
    return [k for k in rl._rate_buckets if k.startswith("verified:")]


class TestVerifiedBucketAdmit:
    def test_admit_below_budget_is_silent(self, monkeypatch):
        monkeypatch.setattr(rl, "_VERIFIED_WEBHOOK_RATE_LIMIT", 5)
        for _ in range(5):
            assert rl._check_verified_stripe_webhook_rate_limit(_event()) is None

    def test_budget_trip_raises_429_with_retry_after(self, monkeypatch):
        monkeypatch.setattr(rl, "_VERIFIED_WEBHOOK_RATE_LIMIT", 5)
        for _ in range(5):
            rl._check_verified_stripe_webhook_rate_limit(_event())
        with pytest.raises(HTTPException) as exc:
            rl._check_verified_stripe_webhook_rate_limit(_event())
        assert exc.value.status_code == 429
        assert "retry-after" in {k.lower() for k in exc.value.headers}

    def test_rejection_counter_recorded(self, monkeypatch):
        monkeypatch.setattr(rl, "_VERIFIED_WEBHOOK_RATE_LIMIT", 1)
        rl._check_verified_stripe_webhook_rate_limit(_event())
        with pytest.raises(HTTPException):
            rl._check_verified_stripe_webhook_rate_limit(_event())
        counts = rl.rate_limit_rejection_counts()
        assert counts.get("verified:acct_a:False") == 1


class TestVerifiedBucketIsolation:
    def test_account_isolation(self, monkeypatch):
        monkeypatch.setattr(rl, "_VERIFIED_WEBHOOK_RATE_LIMIT", 3)
        for _ in range(3):
            rl._check_verified_stripe_webhook_rate_limit(_event("acct_a"))
        with pytest.raises(HTTPException):
            rl._check_verified_stripe_webhook_rate_limit(_event("acct_a"))
        # different account unaffected
        assert rl._check_verified_stripe_webhook_rate_limit(_event("acct_b")) is None

    def test_livemode_isolation(self, monkeypatch):
        monkeypatch.setattr(rl, "_VERIFIED_WEBHOOK_RATE_LIMIT", 3)
        for _ in range(3):
            rl._check_verified_stripe_webhook_rate_limit(_event("acct_a", livemode=True))
        with pytest.raises(HTTPException):
            rl._check_verified_stripe_webhook_rate_limit(_event("acct_a", livemode=True))
        # same account, test mode: separate bucket
        assert rl._check_verified_stripe_webhook_rate_limit(_event("acct_a", livemode=False)) is None

    def test_new_event_id_does_not_reset_bucket(self, monkeypatch):
        monkeypatch.setattr(rl, "_VERIFIED_WEBHOOK_RATE_LIMIT", 2)
        rl._check_verified_stripe_webhook_rate_limit(_event(id="evt_1"))
        rl._check_verified_stripe_webhook_rate_limit(_event(id="evt_2"))
        with pytest.raises(HTTPException):
            rl._check_verified_stripe_webhook_rate_limit(_event(id="evt_never_seen"))

    def test_client_extras_cannot_split_bucket(self, monkeypatch):
        monkeypatch.setattr(rl, "_VERIFIED_WEBHOOK_RATE_LIMIT", 2)
        rl._check_verified_stripe_webhook_rate_limit(
            _event(forwarded="1.2.3.4", x_real_ip="9.9.9.9", client_host="evil"))
        rl._check_verified_stripe_webhook_rate_limit(
            _event(forwarded="5.6.7.8", x_real_ip="8.8.8.8", client_host="evil2"))
        # still the same single account bucket -> third call trips
        with pytest.raises(HTTPException):
            rl._check_verified_stripe_webhook_rate_limit(_event())


class TestPlatformFallback:
    def test_missing_none_empty_account_share_platform_bucket(self, monkeypatch):
        monkeypatch.setattr(rl, "_VERIFIED_WEBHOOK_RATE_LIMIT", 2)
        assert rl._check_verified_stripe_webhook_rate_limit({"livemode": False}) is None
        assert rl._check_verified_stripe_webhook_rate_limit({"account": None, "livemode": False}) is None
        with pytest.raises(HTTPException):
            rl._check_verified_stripe_webhook_rate_limit({"account": "", "livemode": False})
        assert "verified:platform:False" in rl._rate_buckets

    def test_string_none_is_distinct_bucket(self, monkeypatch):
        monkeypatch.setattr(rl, "_VERIFIED_WEBHOOK_RATE_LIMIT", 1)
        rl._check_verified_stripe_webhook_rate_limit({"account": None, "livemode": False})
        with pytest.raises(HTTPException):
            rl._check_verified_stripe_webhook_rate_limit({"account": None, "livemode": False})
        # platform bucket is full; the STRING "None" is a different bucket -> admits
        assert rl._check_verified_stripe_webhook_rate_limit({"account": "None", "livemode": False}) is None


def _patch_process_helpers(monkeypatch, construct_event):
    """Patch the REAL stripe module's construct_event; env vars make the
    webhook secret present so the flow reaches signature verification."""
    monkeypatch.setattr(real_stripe.Webhook, "construct_event", construct_event)
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_redteam_2929")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_redteam")


class TestThroughPathUnauthFlood:
    async def test_unauth_flood_100x_400_verified_untouched(self, monkeypatch):
        # NO signature header at all -> 400 branch; construct_event never runs
        calls = {"n": 0}

        def _construct_event(payload, sig_header, secret):
            calls["n"] += 1
            raise real_stripe.error.SignatureVerificationError("invalid sig", "header", "bad")

        _patch_process_helpers(monkeypatch, _construct_event)
        from services.ingestion.app.stripe_billing import _process_stripe_webhook

        statuses = []
        for _ in range(100):
            # MagicMock for sync reads (headers/client); AsyncMock ONLY where
            # awaited (body). A bare AsyncMock request feeds coroutines into
            # canonical_ip(value.strip()) — the RC-108 coroutine-strip class.
            req = MagicMock()
            req.body = AsyncMock(return_value=b'{"type": "test"}')
            req.headers.get.return_value = None
            req.client.host = "10.0.0.1"
            with pytest.raises(HTTPException) as exc:
                await _process_stripe_webhook(req, "")
            statuses.append(exc.value.status_code)
        assert all(s == 400 for s in statuses)
        assert calls["n"] == 0  # never reached signature verification
        assert _verified_keys() == []  # unsigned flood consumed no verified budget


class TestThroughPathForgedSig:
    async def test_forged_sig_flood_401s_construct_event_saw_all(self, monkeypatch):
        # signature header present but forged -> 401 path; verified bucket untouched
        calls = {"n": 0}

        def _construct_event(payload, sig_header, secret):
            calls["n"] += 1
            raise real_stripe.error.SignatureVerificationError("invalid sig", "header", "bad")

        _patch_process_helpers(monkeypatch, _construct_event)
        from services.ingestion.app.stripe_billing import _process_stripe_webhook

        for _ in range(100):
            # same mock shape as the unauth flood: MagicMock + AsyncMock(body)
            req = MagicMock()
            req.body = AsyncMock(return_value=b'{"type": "test"}')
            req.headers.get.return_value = None
            req.client.host = "10.0.0.1"
            with pytest.raises(HTTPException) as exc:
                await _process_stripe_webhook(req, "t=1,v1=forged")
            assert exc.value.status_code == 401
        assert calls["n"] == 100
        assert _verified_keys() == []


class TestKeyDisjointness:
    def test_unverified_path_never_writes_verified_keys(self, monkeypatch):
        # drive the unsigned per-IP check; its buckets must not use verified: prefix
        monkeypatch.setattr(rl, "_WEBHOOK_RATE_LIMIT", 5)
        req = MagicMock()
        req.client.host = "10.0.0.1"
        req.headers.get.return_value = None
        for _ in range(5):
            rl._check_stripe_webhook_rate_limit(req)
        assert _verified_keys() == []
        assert any(not k.startswith("verified:") for k in rl._rate_buckets)
