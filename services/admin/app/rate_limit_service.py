"""Redis-backed rate limiting for passwordless authentication flows."""

from __future__ import annotations

import hashlib
import math
import time
from dataclasses import dataclass
from typing import Callable, Sequence


OTP_EMAIL_LIMIT = 3
OTP_EMAIL_WINDOW_SECONDS = 15 * 60
OTP_EMAIL_BROWSER_LIMIT = 1
OTP_EMAIL_BROWSER_WINDOW_SECONDS = 60
OTP_IP_LIMIT = 20
OTP_IP_WINDOW_SECONDS = 10 * 60

_MILLI_TOKEN = 1000


_TOKEN_BUCKET_SCRIPT = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2]) * 1000
local now_ms = tonumber(ARGV[3])
local capacity = limit * 1000

local bucket = redis.call("HMGET", key, "tokens", "updated_ms")
local tokens = tonumber(bucket[1])
local updated_ms = tonumber(bucket[2])
if tokens == nil or updated_ms == nil then
    tokens = capacity
    updated_ms = now_ms
end

local elapsed_ms = math.max(0, now_ms - updated_ms)
local refill = math.floor(elapsed_ms * capacity / window_ms)
tokens = math.min(capacity, tokens + refill)

if tokens < 1000 then
    redis.call("HSET", key, "tokens", tokens, "updated_ms", now_ms)
    redis.call("PEXPIRE", key, window_ms)
    local retry_ms = math.ceil((1000 - tokens) * window_ms / capacity)
    return {0, tokens, retry_ms}
end

tokens = tokens - 1000
redis.call("HSET", key, "tokens", tokens, "updated_ms", now_ms)
redis.call("PEXPIRE", key, window_ms)
return {1, tokens, 0}
"""


_MULTI_TOKEN_BUCKET_SCRIPT = """
local now_ms = tonumber(ARGV[1])
local states = {}

for i = 1, #KEYS do
    local limit = tonumber(ARGV[2 + ((i - 1) * 2)])
    local window_ms = tonumber(ARGV[3 + ((i - 1) * 2)]) * 1000
    local capacity = limit * 1000
    local bucket = redis.call("HMGET", KEYS[i], "tokens", "updated_ms")
    local tokens = tonumber(bucket[1])
    local updated_ms = tonumber(bucket[2])
    if tokens == nil or updated_ms == nil then
        tokens = capacity
        updated_ms = now_ms
    end

    local elapsed_ms = math.max(0, now_ms - updated_ms)
    local refill = math.floor(elapsed_ms * capacity / window_ms)
    tokens = math.min(capacity, tokens + refill)
    states[i] = {tokens, window_ms, capacity}

    if tokens < 1000 then
        local retry_ms = math.ceil((1000 - tokens) * window_ms / capacity)
        return {0, i, tokens, retry_ms}
    end
end

local response = {1}
for i = 1, #KEYS do
    local tokens = states[i][1] - 1000
    local window_ms = states[i][2]
    redis.call("HSET", KEYS[i], "tokens", tokens, "updated_ms", now_ms)
    redis.call("PEXPIRE", KEYS[i], window_ms)
    response[#response + 1] = tokens
end

return response
"""


@dataclass(frozen=True)
class RateLimitBucket:
    name: str
    key: str
    limit: int
    window_seconds: int


@dataclass(frozen=True)
class RateLimitDecision:
    key: str
    limit: int
    window_seconds: int
    remaining: float
    retry_after_seconds: int = 0


class RateLimitExceededException(Exception):
    """Raised when a Redis-backed rate limit bucket has no tokens left."""

    def __init__(
        self,
        *,
        key: str,
        limit: int,
        window_seconds: int,
        retry_after_seconds: int,
        bucket_name: str | None = None,
    ):
        self.key = key
        self.limit = limit
        self.window_seconds = window_seconds
        self.retry_after_seconds = retry_after_seconds
        self.bucket_name = bucket_name
        label = bucket_name or key
        super().__init__(
            f"Rate limit exceeded for {label}; retry after {retry_after_seconds} seconds"
        )


class RateLimitService:
    """Token-bucket rate limiter backed by Redis.

    The same primitive protects email, email/browser, and IP buckets. OTP
    generation uses a multi-bucket Lua script so either every layer consumes a
    token or none of them do.
    """

    def __init__(self, redis_client, *, clock: Callable[[], float] | None = None):
        self._redis = redis_client
        self._clock = clock or time.time

    async def check_and_consume(
        self,
        key: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitDecision:
        self._validate_bucket(key=key, limit=limit, window_seconds=window_seconds)
        result = await self._redis.eval(
            _TOKEN_BUCKET_SCRIPT,
            1,
            key,
            int(limit),
            int(window_seconds),
            self._now_ms(),
        )
        allowed, remaining_milli_tokens, retry_ms = [int(value) for value in result]
        if allowed != 1:
            raise RateLimitExceededException(
                key=key,
                limit=limit,
                window_seconds=window_seconds,
                retry_after_seconds=self._retry_seconds(retry_ms),
            )
        return RateLimitDecision(
            key=key,
            limit=limit,
            window_seconds=window_seconds,
            remaining=remaining_milli_tokens / _MILLI_TOKEN,
        )

    async def check_and_consume_many(
        self,
        buckets: Sequence[RateLimitBucket],
    ) -> dict[str, RateLimitDecision]:
        if not buckets:
            return {}
        for bucket in buckets:
            self._validate_bucket(
                key=bucket.key,
                limit=bucket.limit,
                window_seconds=bucket.window_seconds,
            )

        keys = [bucket.key for bucket in buckets]
        args: list[int] = [self._now_ms()]
        for bucket in buckets:
            args.extend([int(bucket.limit), int(bucket.window_seconds)])

        result = await self._redis.eval(
            _MULTI_TOKEN_BUCKET_SCRIPT,
            len(keys),
            *keys,
            *args,
        )
        allowed = int(result[0])
        if allowed != 1:
            blocked_index = int(result[1]) - 1
            retry_ms = int(result[3])
            blocked = buckets[blocked_index]
            raise RateLimitExceededException(
                key=blocked.key,
                limit=blocked.limit,
                window_seconds=blocked.window_seconds,
                retry_after_seconds=self._retry_seconds(retry_ms),
                bucket_name=blocked.name,
            )

        decisions: dict[str, RateLimitDecision] = {}
        for bucket, remaining_milli_tokens in zip(buckets, result[1:]):
            decisions[bucket.name] = RateLimitDecision(
                key=bucket.key,
                limit=bucket.limit,
                window_seconds=bucket.window_seconds,
                remaining=int(remaining_milli_tokens) / _MILLI_TOKEN,
            )
        return decisions

    async def check_otp_generation(
        self,
        *,
        email_fingerprint: str,
        browser_binding_hash: str,
        ip_address: str,
    ) -> dict[str, RateLimitDecision]:
        return await self.check_and_consume_many(
            [
                RateLimitBucket(
                    name="email",
                    key=self.email_generation_key(email_fingerprint),
                    limit=OTP_EMAIL_LIMIT,
                    window_seconds=OTP_EMAIL_WINDOW_SECONDS,
                ),
                RateLimitBucket(
                    name="email_browser",
                    key=self.email_browser_generation_key(email_fingerprint, browser_binding_hash),
                    limit=OTP_EMAIL_BROWSER_LIMIT,
                    window_seconds=OTP_EMAIL_BROWSER_WINDOW_SECONDS,
                ),
                RateLimitBucket(
                    name="ip",
                    key=self.ip_generation_key(ip_address),
                    limit=OTP_IP_LIMIT,
                    window_seconds=OTP_IP_WINDOW_SECONDS,
                ),
            ]
        )

    @staticmethod
    def email_generation_key(email_fingerprint: str) -> str:
        return f"auth:otp:generate:email:{RateLimitService._required_component(email_fingerprint)}"

    @staticmethod
    def email_browser_generation_key(email_fingerprint: str, browser_binding_hash: str) -> str:
        email_part = RateLimitService._required_component(email_fingerprint)
        browser_part = RateLimitService._required_component(browser_binding_hash)
        return f"auth:otp:generate:email_browser:{email_part}:{browser_part}"

    @staticmethod
    def ip_generation_key(ip_address: str) -> str:
        ip_text = RateLimitService._required_component(ip_address)
        ip_digest = hashlib.sha256(ip_text.encode("utf-8")).hexdigest()
        return f"auth:otp:generate:ip:{ip_digest}"

    def _now_ms(self) -> int:
        return int(self._clock() * 1000)

    @staticmethod
    def _retry_seconds(retry_ms: int) -> int:
        return max(1, math.ceil(retry_ms / 1000))

    @staticmethod
    def _validate_bucket(*, key: str, limit: int, window_seconds: int) -> None:
        if not isinstance(key, str) or not key.strip():
            raise ValueError("rate-limit key is required")
        if int(limit) <= 0:
            raise ValueError("rate-limit limit must be positive")
        if int(window_seconds) <= 0:
            raise ValueError("rate-limit window_seconds must be positive")

    @staticmethod
    def _required_component(value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("rate-limit key component is required")
        return value.strip()
