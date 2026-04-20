"""IP-based sliding-window rate limiter for Stripe webhook endpoints.

Uses an in-memory deque per IP.  Simple and zero-dependency — acceptable for a
single-process ingestion service.  Replace with Redis if the service is ever
horizontally scaled.

Limits
------
- 100 requests per 60-second window per IP (configurable via env vars
  STRIPE_WEBHOOK_RATE_LIMIT and STRIPE_WEBHOOK_RATE_WINDOW).
"""

from __future__ import annotations

import os
import time
from collections import deque
from threading import Lock
from typing import Deque, Dict

_DEFAULT_MAX_REQUESTS = 100
_DEFAULT_WINDOW_SECONDS = 60

# Global state: {ip: deque of float timestamps}
_buckets: Dict[str, Deque[float]] = {}
_lock = Lock()


def _max_requests() -> int:
    try:
        return int(os.getenv("STRIPE_WEBHOOK_RATE_LIMIT", str(_DEFAULT_MAX_REQUESTS)))
    except (TypeError, ValueError):
        return _DEFAULT_MAX_REQUESTS


def _window_seconds() -> int:
    try:
        return int(os.getenv("STRIPE_WEBHOOK_RATE_WINDOW", str(_DEFAULT_WINDOW_SECONDS)))
    except (TypeError, ValueError):
        return _DEFAULT_WINDOW_SECONDS


def is_rate_limited(ip: str) -> tuple[bool, int]:
    """Check whether *ip* has exceeded the allowed request rate.

    Returns
    -------
    (limited, retry_after)
        *limited* is True when the caller should receive a 429.
        *retry_after* is the number of seconds until the oldest slot expires
        (relevant only when *limited* is True).
    """
    now = time.monotonic()
    window = _window_seconds()
    max_req = _max_requests()
    cutoff = now - window

    with _lock:
        if ip not in _buckets:
            _buckets[ip] = deque()

        bucket = _buckets[ip]

        # Evict timestamps older than the window.
        while bucket and bucket[0] < cutoff:
            bucket.popleft()

        if len(bucket) >= max_req:
            oldest = bucket[0]
            retry_after = max(1, int(oldest - cutoff) + 1)
            return True, retry_after

        bucket.append(now)
        return False, 0


def reset_for_ip(ip: str) -> None:
    """Clear rate-limit state for *ip*  — test helper only."""
    with _lock:
        _buckets.pop(ip, None)
