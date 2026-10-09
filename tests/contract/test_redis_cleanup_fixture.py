"""Cleanup-failure visibility for the contract-suite Redis fixture.

The autouse fixture in ``conftest.py`` clears privileged-auth counters from
local Redis before each test. It must swallow only "no local Redis"
connection failures (logged, so skips stay visible) and must let any other
Redis failure propagate instead of hiding it behind a bare except-pass.
"""

import logging
import sys
import types

import pytest

from tests.contract import conftest

FIXTURE = conftest._clear_admin_brute_force_state.__wrapped__


def _install_fake_redis(monkeypatch, failure):
    """Point ``import redis`` at a stub whose client raises ``failure``."""
    import redis

    fake = types.ModuleType("redis")

    class FakeClient:
        @staticmethod
        def from_url(*args, **kwargs):
            raise failure

    fake.Redis = FakeClient
    fake.exceptions = redis.exceptions
    monkeypatch.setitem(sys.modules, "redis", fake)


def test_unexpected_redis_error_propagates(monkeypatch):
    """A non-connection Redis failure must fail loudly, not pass silently."""
    import redis

    _install_fake_redis(monkeypatch, redis.exceptions.ResponseError("ERR unknown command"))
    with pytest.raises(redis.exceptions.ResponseError):
        FIXTURE()


def test_connection_error_is_logged_and_swallowed(monkeypatch, caplog):
    """A missing local Redis stays a skip, but the skip is logged."""
    import redis

    _install_fake_redis(
        monkeypatch,
        redis.exceptions.ConnectionError("connection refused"),
    )
    with caplog.at_level(logging.WARNING, logger=conftest.__name__):
        FIXTURE()
    assert "local Redis unavailable" in caplog.text


def test_timeout_error_is_logged_and_swallowed(monkeypatch, caplog):
    """A slow local Redis stays a skip, but the skip is logged."""
    import redis

    _install_fake_redis(monkeypatch, redis.exceptions.TimeoutError("timed out"))
    with caplog.at_level(logging.WARNING, logger=conftest.__name__):
        FIXTURE()
    assert "local Redis unavailable" in caplog.text
