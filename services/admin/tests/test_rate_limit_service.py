"""Unit tests for Redis-backed auth rate limiting."""

from __future__ import annotations

import hashlib

import pytest

from services.admin.app import rate_limit_service as rls
from services.admin.app.rate_limit_service import (
    OTP_EMAIL_BROWSER_LIMIT,
    OTP_EMAIL_BROWSER_WINDOW_SECONDS,
    OTP_EMAIL_LIMIT,
    OTP_EMAIL_WINDOW_SECONDS,
    OTP_IP_LIMIT,
    OTP_IP_WINDOW_SECONDS,
    RateLimitExceededException,
    RateLimitService,
)
from services.admin.app.session_store import InMemoryAsyncRedis


class FakeRedis:
    """Small Redis eval mock that implements the service's token-bucket scripts."""

    def __init__(self):
        self.buckets: dict[str, tuple[int, int]] = {}
        self.eval_calls = []

    async def eval(self, script: str, numkeys: int, *values):
        self.eval_calls.append((script, numkeys, values))
        keys = [str(value) for value in values[:numkeys]]
        args = list(values[numkeys:])
        if script == rls._TOKEN_BUCKET_SCRIPT:
            limit, window_seconds, now_ms = [int(value) for value in args]
            return self._check_bucket(
                key=keys[0],
                limit=limit,
                window_seconds=window_seconds,
                now_ms=now_ms,
                consume=True,
            )
        if script == rls._MULTI_TOKEN_BUCKET_SCRIPT:
            now_ms = int(args[0])
            specs = []
            for index, key in enumerate(keys):
                limit = int(args[1 + (index * 2)])
                window_seconds = int(args[2 + (index * 2)])
                result = self._check_bucket(
                    key=key,
                    limit=limit,
                    window_seconds=window_seconds,
                    now_ms=now_ms,
                    consume=False,
                )
                specs.append((key, limit, window_seconds, result))
                if int(result[0]) != 1:
                    return [0, index + 1, result[1], result[2]]

            response = [1]
            for key, limit, window_seconds, _result in specs:
                consumed = self._check_bucket(
                    key=key,
                    limit=limit,
                    window_seconds=window_seconds,
                    now_ms=now_ms,
                    consume=True,
                )
                response.append(consumed[1])
            return response
        raise AssertionError("unexpected Redis script")

    def _check_bucket(
        self,
        *,
        key: str,
        limit: int,
        window_seconds: int,
        now_ms: int,
        consume: bool,
    ) -> list[int]:
        capacity = limit * 1000
        window_ms = window_seconds * 1000
        tokens, updated_ms = self.buckets.get(key, (capacity, now_ms))
        elapsed_ms = max(0, now_ms - updated_ms)
        refill = (elapsed_ms * capacity) // window_ms
        tokens = min(capacity, tokens + refill)

        if tokens < 1000:
            retry_ms = ((1000 - tokens) * window_ms + capacity - 1) // capacity
            if consume:
                self.buckets[key] = (tokens, now_ms)
            return [0, tokens, retry_ms]

        remaining = tokens - 1000
        if consume:
            self.buckets[key] = (remaining, now_ms)
        return [1, remaining, 0]


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _service():
    clock = Clock()
    redis = FakeRedis()
    return RateLimitService(redis, clock=clock), redis, clock


@pytest.mark.asyncio
async def test_check_and_consume_allows_limit_then_raises_specific_exception():
    service, redis, _clock = _service()
    key = "auth:otp:generate:email:email-fp"

    for expected_remaining in [2.0, 1.0, 0.0]:
        decision = await service.check_and_consume(key, OTP_EMAIL_LIMIT, OTP_EMAIL_WINDOW_SECONDS)
        assert decision.remaining == expected_remaining

    with pytest.raises(RateLimitExceededException) as exc_info:
        await service.check_and_consume(key, OTP_EMAIL_LIMIT, OTP_EMAIL_WINDOW_SECONDS)

    assert exc_info.value.key == key
    assert exc_info.value.limit == OTP_EMAIL_LIMIT
    assert exc_info.value.window_seconds == OTP_EMAIL_WINDOW_SECONDS
    assert exc_info.value.retry_after_seconds == 300
    assert redis.eval_calls[-1][0] == rls._TOKEN_BUCKET_SCRIPT


@pytest.mark.asyncio
async def test_email_browser_bucket_refills_after_sixty_seconds():
    service, _redis, clock = _service()
    key = "auth:otp:generate:email_browser:email-fp:browser-fp"

    await service.check_and_consume(key, OTP_EMAIL_BROWSER_LIMIT, OTP_EMAIL_BROWSER_WINDOW_SECONDS)
    with pytest.raises(RateLimitExceededException) as exc_info:
        await service.check_and_consume(key, OTP_EMAIL_BROWSER_LIMIT, OTP_EMAIL_BROWSER_WINDOW_SECONDS)

    assert exc_info.value.retry_after_seconds == 60

    clock.advance(60)
    decision = await service.check_and_consume(key, OTP_EMAIL_BROWSER_LIMIT, OTP_EMAIL_BROWSER_WINDOW_SECONDS)
    assert decision.remaining == 0.0


@pytest.mark.asyncio
async def test_otp_generation_buckets_are_independent_and_no_partial_consumption():
    service, _redis, _clock = _service()

    await service.check_otp_generation(
        email_fingerprint="email-fp",
        browser_binding_hash="browser-a",
        ip_address="203.0.113.10",
    )
    with pytest.raises(RateLimitExceededException) as browser_exc:
        await service.check_otp_generation(
            email_fingerprint="email-fp",
            browser_binding_hash="browser-a",
            ip_address="203.0.113.10",
        )
    assert browser_exc.value.bucket_name == "email_browser"

    await service.check_otp_generation(
        email_fingerprint="email-fp",
        browser_binding_hash="browser-b",
        ip_address="203.0.113.10",
    )
    await service.check_otp_generation(
        email_fingerprint="email-fp",
        browser_binding_hash="browser-c",
        ip_address="203.0.113.10",
    )
    with pytest.raises(RateLimitExceededException) as email_exc:
        await service.check_otp_generation(
            email_fingerprint="email-fp",
            browser_binding_hash="browser-d",
            ip_address="203.0.113.10",
        )

    assert email_exc.value.bucket_name == "email"
    assert email_exc.value.limit == OTP_EMAIL_LIMIT


@pytest.mark.asyncio
async def test_in_memory_redis_eval_preserves_multi_bucket_atomicity():
    clock = Clock()
    redis = InMemoryAsyncRedis()
    service = RateLimitService(redis, clock=clock)

    await service.check_otp_generation(
        email_fingerprint="email-fp",
        browser_binding_hash="browser-a",
        ip_address="203.0.113.10",
    )
    with pytest.raises(RateLimitExceededException) as browser_exc:
        await service.check_otp_generation(
            email_fingerprint="email-fp",
            browser_binding_hash="browser-a",
            ip_address="203.0.113.10",
        )
    assert browser_exc.value.bucket_name == "email_browser"

    await service.check_otp_generation(
        email_fingerprint="email-fp",
        browser_binding_hash="browser-b",
        ip_address="203.0.113.10",
    )
    await service.check_otp_generation(
        email_fingerprint="email-fp",
        browser_binding_hash="browser-c",
        ip_address="203.0.113.10",
    )
    with pytest.raises(RateLimitExceededException) as email_exc:
        await service.check_otp_generation(
            email_fingerprint="email-fp",
            browser_binding_hash="browser-d",
            ip_address="203.0.113.10",
        )

    assert email_exc.value.bucket_name == "email"


@pytest.mark.asyncio
async def test_per_ip_bucket_is_independent_from_email_and_browser_buckets():
    service, _redis, _clock = _service()

    for index in range(OTP_IP_LIMIT):
        await service.check_otp_generation(
            email_fingerprint=f"email-fp-{index}",
            browser_binding_hash=f"browser-{index}",
            ip_address="198.51.100.20",
        )

    with pytest.raises(RateLimitExceededException) as exc_info:
        await service.check_otp_generation(
            email_fingerprint="fresh-email",
            browser_binding_hash="fresh-browser",
            ip_address="198.51.100.20",
        )

    assert exc_info.value.bucket_name == "ip"
    assert exc_info.value.limit == OTP_IP_LIMIT
    assert exc_info.value.window_seconds == OTP_IP_WINDOW_SECONDS

    await service.check_otp_generation(
        email_fingerprint="fresh-email",
        browser_binding_hash="fresh-browser",
        ip_address="198.51.100.21",
    )


@pytest.mark.asyncio
async def test_per_ip_token_bucket_refills_adaptively():
    service, _redis, clock = _service()
    key = service.ip_generation_key("192.0.2.55")

    for _ in range(OTP_IP_LIMIT):
        await service.check_and_consume(key, OTP_IP_LIMIT, OTP_IP_WINDOW_SECONDS)

    with pytest.raises(RateLimitExceededException):
        await service.check_and_consume(key, OTP_IP_LIMIT, OTP_IP_WINDOW_SECONDS)

    clock.advance(30)
    decision = await service.check_and_consume(key, OTP_IP_LIMIT, OTP_IP_WINDOW_SECONDS)
    assert decision.remaining == 0.0


def test_rate_limit_keys_do_not_store_raw_ip_addresses():
    ip = "192.0.2.10"
    key = RateLimitService.ip_generation_key(ip)

    assert ip not in key
    assert key.endswith(hashlib.sha256(ip.encode("utf-8")).hexdigest())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "key,limit,window_seconds",
    [
        ("", 1, 60),
        ("key", 0, 60),
        ("key", 1, 0),
    ],
)
async def test_check_and_consume_rejects_invalid_bucket_config(key, limit, window_seconds):
    service, _redis, _clock = _service()

    with pytest.raises(ValueError):
        await service.check_and_consume(key, limit, window_seconds)
