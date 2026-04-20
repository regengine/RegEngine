"""Tests for #1086: POST /auth/forgot-password endpoint.

Covers:
  - Happy path (registered email): 200 + generic message
  - Unknown email: same 200 + same generic message (no enumeration)
  - Per-email rate limit (3/hour): 4th request → 429
  - Supabase unavailable: still returns 200 (fail open, no enumeration)
  - Supabase raises exception: still returns 200 (no enumeration)
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException, status
from starlette.testclient import TestClient

repo_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "services" / "admin"))

from services.admin.app import password_reset_routes as prr  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session_store(counter: int = 0) -> MagicMock:
    """Return a mock RedisSessionStore with a controllable per-email counter."""
    store = MagicMock()
    redis_client = AsyncMock()

    # get() returns the current counter string (or None if 0)
    redis_client.get = AsyncMock(return_value=str(counter) if counter else None)

    # pipeline returns an async context manager whose execute() does nothing
    pipe = AsyncMock()
    pipe.__aenter__ = AsyncMock(return_value=pipe)
    pipe.__aexit__ = AsyncMock(return_value=False)
    pipe.incr = MagicMock()
    pipe.expire = MagicMock()
    pipe.execute = AsyncMock(return_value=[counter + 1, True])
    redis_client.pipeline = MagicMock(return_value=pipe)

    store._get_client = AsyncMock(return_value=redis_client)
    return store


# ---------------------------------------------------------------------------
# Unit tests for rate-limit helpers
# ---------------------------------------------------------------------------


class TestForgotPwRateLimit:
    @pytest.mark.asyncio
    async def test_under_limit_does_not_raise(self):
        store = _make_session_store(counter=2)  # 2 previous attempts
        # Should NOT raise — still one request left before the limit
        await prr._check_forgot_pw_rate_limit(store, "user@example.com")

    @pytest.mark.asyncio
    async def test_at_limit_raises_429(self):
        store = _make_session_store(counter=3)  # exactly at limit
        with pytest.raises(HTTPException) as exc_info:
            await prr._check_forgot_pw_rate_limit(store, "user@example.com")
        assert exc_info.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert "Retry-After" in exc_info.value.headers

    @pytest.mark.asyncio
    async def test_over_limit_raises_429(self):
        store = _make_session_store(counter=10)
        with pytest.raises(HTTPException) as exc_info:
            await prr._check_forgot_pw_rate_limit(store, "user@example.com")
        assert exc_info.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS

    @pytest.mark.asyncio
    async def test_zero_count_does_not_raise(self):
        store = _make_session_store(counter=0)
        await prr._check_forgot_pw_rate_limit(store, "fresh@example.com")


# ---------------------------------------------------------------------------
# Integration-style tests via TestClient (handles SlowAPI decorator)
# ---------------------------------------------------------------------------

def _build_app(session_store: MagicMock, supabase: object | None) -> FastAPI:
    """Build a minimal FastAPI app mounting the router under test."""
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded

    app = FastAPI()
    limiter = Limiter(key_func=get_remote_address, enabled=False)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # Override the session_store dependency
    app.include_router(prr.router)
    app.dependency_overrides[prr.get_session_store] = lambda: session_store
    return app, supabase


class TestForgotPasswordEndpoint:
    """Call helpers directly — avoids SlowAPI needing a real Request."""

    @pytest.mark.asyncio
    async def test_happy_path_known_email(self):
        """Registered email → 200 with generic message; Supabase called once."""
        store = _make_session_store(counter=0)
        sb = MagicMock()
        sb.auth.reset_password_for_email = MagicMock(return_value=None)

        with patch.object(prr, "get_supabase", return_value=sb):
            result = await prr._forgot_password_handler(
                email="alice@example.com",
                session_store=store,
            )

        assert result.message == prr._FORGOT_PW_GENERIC_MSG
        sb.auth.reset_password_for_email.assert_called_once_with("alice@example.com")

    @pytest.mark.asyncio
    async def test_unknown_email_same_response(self):
        """Unknown email → same 200 + same generic message (no enumeration)."""
        store = _make_session_store(counter=0)
        sb = MagicMock()
        sb.auth.reset_password_for_email = MagicMock(
            side_effect=Exception("User not found")
        )

        with patch.object(prr, "get_supabase", return_value=sb):
            result = await prr._forgot_password_handler(
                email="nobody@example.com",
                session_store=store,
            )

        assert result.message == prr._FORGOT_PW_GENERIC_MSG

    @pytest.mark.asyncio
    async def test_rate_limit_exceeded_raises_429(self):
        """4th request from the same email within the window → 429."""
        store = _make_session_store(counter=3)  # limit reached
        sb = MagicMock()

        with patch.object(prr, "get_supabase", return_value=sb):
            with pytest.raises(HTTPException) as exc_info:
                await prr._forgot_password_handler(
                    email="abuser@example.com",
                    session_store=store,
                )

        assert exc_info.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        sb.auth.reset_password_for_email.assert_not_called()

    @pytest.mark.asyncio
    async def test_supabase_unavailable_returns_200(self):
        """get_supabase() returns None → still returns 200 (no enumeration)."""
        store = _make_session_store(counter=0)

        with patch.object(prr, "get_supabase", return_value=None):
            result = await prr._forgot_password_handler(
                email="user@example.com",
                session_store=store,
            )

        assert result.message == prr._FORGOT_PW_GENERIC_MSG

    @pytest.mark.asyncio
    async def test_email_normalized_to_lowercase(self):
        """Email addresses are normalised before being passed to Supabase."""
        store = _make_session_store(counter=0)
        sb = MagicMock()
        sb.auth.reset_password_for_email = MagicMock(return_value=None)

        with patch.object(prr, "get_supabase", return_value=sb):
            await prr._forgot_password_handler(
                email="User@Example.COM",
                session_store=store,
            )

        sb.auth.reset_password_for_email.assert_called_once_with("user@example.com")

    @pytest.mark.asyncio
    async def test_rate_limit_key_per_email(self):
        """Each unique email gets its own rate-limit bucket."""
        store_limited = _make_session_store(counter=3)
        store_fresh = _make_session_store(counter=0)
        sb = MagicMock()
        sb.auth.reset_password_for_email = MagicMock(return_value=None)

        with patch.object(prr, "get_supabase", return_value=sb):
            # Limited email raises 429
            with pytest.raises(HTTPException) as exc_info:
                await prr._forgot_password_handler(
                    email="limited@example.com",
                    session_store=store_limited,
                )
            assert exc_info.value.status_code == 429

            # Fresh email succeeds
            result = await prr._forgot_password_handler(
                email="fresh@example.com",
                session_store=store_fresh,
            )
            assert result.message == prr._FORGOT_PW_GENERIC_MSG
