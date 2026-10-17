"""Regression coverage for public tool email verification codes."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from starlette.requests import Request

_REPO_ADMIN = Path(__file__).resolve().parents[1]
if str(_REPO_ADMIN) not in sys.path:
    sys.path.insert(0, str(_REPO_ADMIN))


def _stub_request() -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/tools/verify-email",
        "headers": [],
        "query_string": b"",
        "client": ("127.0.0.1", 12345),
    }
    request = Request(scope)
    request.state.view_rate_limit = None
    return request


@pytest.fixture(autouse=True)
def disable_slowapi(monkeypatch):
    try:
        import slowapi.extension as slowapi_extension

        monkeypatch.setattr(slowapi_extension.Limiter, "_check_request_limit", lambda *a, **k: None)
    except Exception:
        pass


@pytest.fixture
def tvr(monkeypatch):
    monkeypatch.setenv("TOOL_ACCESS_SECRET", "tool-verification-test-secret")
    monkeypatch.setenv("REGENGINE_ENV", "test")
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    for modname in [
        "app.tool_verification_routes",
        "services.admin.app.tool_verification_routes",
    ]:
        sys.modules.pop(modname, None)
    module = importlib.import_module("app.tool_verification_routes")
    module._memory_store.clear()
    module._redis_available = False
    module._redis_client = None
    module.RESEND_API_KEY = None
    return module


@pytest.mark.asyncio
async def test_verify_email_confirm_code_round_trip_uses_normalized_email(tvr, monkeypatch):
    monkeypatch.setattr(tvr.secrets, "randbelow", lambda _: 234567)
    save_lead = MagicMock()
    monkeypatch.setattr(tvr, "_save_lead", save_lead)

    result = await tvr.verify_email(
        payload=tvr.VerifyEmailRequest(email="Lead@Corp.com", tool_name="ftl-checker"),
        request=_stub_request(),
    )

    assert result.status == "code_sent"
    stored = tvr._memory_store["tool_verify:lead@corp.com"]
    assert stored["code"] == "334567"

    confirm = await tvr.confirm_code(
        payload=tvr.ConfirmCodeRequest(email="LEAD@CORP.COM", code="334567", tool_name="ftl-checker"),
        request=_stub_request(),
    )

    assert confirm.status == "verified"
    assert confirm.token
    assert "tool_verify:lead@corp.com" not in tvr._memory_store
    save_lead.assert_called_once_with("lead@corp.com", "corp.com", "ftl-checker", {})


@pytest.mark.asyncio
async def test_verify_utm_is_saved_only_after_successful_confirmation(tvr, monkeypatch):
    monkeypatch.setattr(tvr.secrets, "randbelow", lambda _: 234567)
    save_lead = MagicMock()
    monkeypatch.setattr(tvr, "_save_lead", save_lead)

    await tvr.verify_email(
        payload=tvr.VerifyEmailRequest(
            email="lead@corp.com",
            tool_name="ftl-checker",
            utm_source="  Search  ",
            utm_medium="email",
            utm_campaign="fall-2026",
        ),
        request=_stub_request(),
    )
    assert tvr._memory_store["tool_verify:lead@corp.com"]["utm"] == {
        "utm_source": "Search",
        "utm_medium": "email",
        "utm_campaign": "fall-2026",
    }
    save_lead.assert_not_called()

    with pytest.raises(HTTPException):
        await tvr.confirm_code(
            payload=tvr.ConfirmCodeRequest(email="lead@corp.com", code="000000", tool_name="ftl-checker"),
            request=_stub_request(),
        )
    save_lead.assert_not_called()

    await tvr.confirm_code(
        payload=tvr.ConfirmCodeRequest(email="lead@corp.com", code="334567", tool_name="ftl-checker"),
        request=_stub_request(),
    )
    save_lead.assert_called_once_with(
        "lead@corp.com",
        "corp.com",
        "ftl-checker",
        {"utm_source": "Search", "utm_medium": "email", "utm_campaign": "fall-2026"},
    )


@pytest.mark.asyncio
async def test_lead_save_failure_does_not_log_bound_lead_data(tvr, monkeypatch):
    async def code_accepted(_email, _code):
        return True, "", {"utm_campaign": "private-campaign"}

    def save_fails(*_args):
        raise RuntimeError("bound values: lead@corp.com, private-campaign")

    logger = MagicMock()
    monkeypatch.setattr(tvr, "_check_code", code_accepted)
    monkeypatch.setattr(tvr, "_save_lead", save_fails)
    monkeypatch.setattr(tvr, "logger", logger)

    response = await tvr.confirm_code(
        payload=tvr.ConfirmCodeRequest(email="lead@corp.com", code="123456"),
        request=_stub_request(),
    )

    assert response.status == "verified"
    assert logger.error.call_args.kwargs["error"] == "RuntimeError"
    assert "lead@corp.com" not in repr(logger.mock_calls)
    assert "private-campaign" not in repr(logger.mock_calls)


def test_verify_utm_fields_reject_values_over_100_characters(tvr):
    for field in ("utm_source", "utm_medium", "utm_campaign"):
        with pytest.raises(ValidationError):
            tvr.VerifyEmailRequest(email="lead@corp.com", **{field: "x" * 101})


@pytest.mark.asyncio
async def test_utm_survives_failed_attempt_in_redis_store(tvr, monkeypatch):
    class FakeRedis:
        def __init__(self):
            self.values = {}

        async def setex(self, key, _ttl, value):
            self.values[key] = value

        async def get(self, key):
            return self.values.get(key)

        async def delete(self, key):
            self.values.pop(key, None)

    fake_redis = FakeRedis()

    async def get_fake_redis():
        return fake_redis

    monkeypatch.setattr(tvr, "_get_redis", get_fake_redis)
    monkeypatch.setattr(tvr.secrets, "randbelow", lambda _: 234567)
    save_lead = MagicMock()
    monkeypatch.setattr(tvr, "_save_lead", save_lead)
    tvr._redis_available = True

    await tvr.verify_email(
        payload=tvr.VerifyEmailRequest(email="lead@corp.com", utm_source="search"),
        request=_stub_request(),
    )
    with pytest.raises(HTTPException):
        await tvr.confirm_code(
            payload=tvr.ConfirmCodeRequest(email="lead@corp.com", code="000000"),
            request=_stub_request(),
        )
    save_lead.assert_not_called()

    await tvr.confirm_code(
        payload=tvr.ConfirmCodeRequest(email="lead@corp.com", code="334567"),
        request=_stub_request(),
    )
    save_lead.assert_called_once_with("lead@corp.com", "corp.com", "unknown", {"utm_source": "search"})
    assert "tool_verify:lead@corp.com" not in fake_redis.values


@pytest.mark.asyncio
async def test_legacy_redis_code_remains_valid_during_rollout(tvr, monkeypatch):
    async def get_legacy_code(_key, _operation):
        return True, "123456:3"

    deleted = []

    async def delete_legacy_code(key, _operation):
        deleted.append(key)
        return True

    monkeypatch.setattr(tvr, "_redis_get_code", get_legacy_code)
    monkeypatch.setattr(tvr, "_redis_delete_code", delete_legacy_code)
    tvr._redis_available = True

    assert await tvr._check_code("lead@corp.com", "123456") == (True, "", {})
    assert deleted == ["tool_verify:lead@corp.com"]


def test_save_lead_uses_parameterized_utm_and_keeps_first_attribution(tvr, monkeypatch):
    from app import database

    session = MagicMock()
    monkeypatch.setattr(database, "SessionLocal", lambda: session)

    tvr._save_lead("lead@corp.com", "corp.com", "ftl-checker", {"utm_source": "search"})

    statement, params = session.execute.call_args.args
    assert params == {
        "email": "lead@corp.com",
        "domain": "corp.com",
        "tool": "ftl-checker",
        "utm_source": "search",
        "utm_medium": None,
        "utm_campaign": None,
    }
    assert "COALESCE(tool_leads.utm_source, EXCLUDED.utm_source)" in str(statement)
    session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_verify_email_dev_log_does_not_include_plaintext_code(tvr, monkeypatch):
    calls = []

    class CaptureLogger:
        def warning(self, event, **kwargs):
            calls.append(("warning", event, kwargs))

        def error(self, event, **kwargs):
            calls.append(("error", event, kwargs))

        def info(self, event, **kwargs):
            calls.append(("info", event, kwargs))

    monkeypatch.setattr(tvr.secrets, "randbelow", lambda _: 234567)
    monkeypatch.setattr(tvr, "logger", CaptureLogger())

    await tvr.verify_email(
        payload=tvr.VerifyEmailRequest(email="lead@corp.com", tool_name="ftl-checker"),
        request=_stub_request(),
    )

    assert "334567" not in repr(calls)
    assert "lead@corp.com" not in repr(calls)


@pytest.mark.asyncio
async def test_confirm_code_rejects_wrong_code_and_does_not_save_lead(tvr, monkeypatch):
    save_lead = MagicMock()
    monkeypatch.setattr(tvr, "_save_lead", save_lead)
    await tvr._store_code("lead@corp.com", "123456")

    with pytest.raises(HTTPException) as exc_info:
        await tvr.confirm_code(
            payload=tvr.ConfirmCodeRequest(email="lead@corp.com", code="000000", tool_name="ftl-checker"),
            request=_stub_request(),
        )

    assert exc_info.value.status_code == 400
    assert "Incorrect code" in exc_info.value.detail
    assert tvr._memory_store["tool_verify:lead@corp.com"]["attempts"] == 2
    save_lead.assert_not_called()


@pytest.mark.asyncio
async def test_verify_email_fails_closed_when_redis_unavailable_in_production(tvr, monkeypatch):
    def raise_redis_down(*args, **kwargs):
        raise RuntimeError("redis down")

    monkeypatch.setattr(tvr, "requires_strict_auth_runtime", lambda: True)
    monkeypatch.setattr(tvr.aioredis, "from_url", raise_redis_down)
    tvr._redis_available = None
    tvr._redis_client = None

    with pytest.raises(HTTPException) as exc_info:
        await tvr.verify_email(
            payload=tvr.VerifyEmailRequest(email="lead@corp.com", tool_name="ftl-checker"),
            request=_stub_request(),
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == tvr.CODE_STORE_UNAVAILABLE_DETAIL
    assert "tool_verify:lead@corp.com" not in tvr._memory_store


@pytest.mark.asyncio
async def test_verify_email_fails_closed_when_redis_unavailable_in_cloud_preview(tvr, monkeypatch):
    def raise_redis_down(*args, **kwargs):
        raise RuntimeError("redis down")

    monkeypatch.setenv("REGENGINE_ENV", "staging")
    monkeypatch.setenv("VERCEL_ENV", "preview")
    monkeypatch.setattr(tvr.aioredis, "from_url", raise_redis_down)
    tvr._redis_available = None
    tvr._redis_client = None

    with pytest.raises(HTTPException) as exc_info:
        await tvr.verify_email(
            payload=tvr.VerifyEmailRequest(email="lead@corp.com", tool_name="ftl-checker"),
            request=_stub_request(),
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == tvr.CODE_STORE_UNAVAILABLE_DETAIL
    assert "tool_verify:lead@corp.com" not in tvr._memory_store


@pytest.mark.asyncio
async def test_erasure_email_dev_log_does_not_include_plaintext_code(tvr, monkeypatch):
    calls = []

    class CaptureLogger:
        def warning(self, event, **kwargs):
            calls.append(("warning", event, kwargs))

        def error(self, event, **kwargs):
            calls.append(("error", event, kwargs))

        def info(self, event, **kwargs):
            calls.append(("info", event, kwargs))

    monkeypatch.setattr(tvr, "logger", CaptureLogger())

    await tvr._send_erasure_email("lead@corp.com", "123456")

    assert "123456" not in repr(calls)
    assert "lead@corp.com" not in repr(calls)


@pytest.mark.asyncio
async def test_confirm_code_fails_closed_when_redis_unavailable_in_production(tvr, monkeypatch):
    def raise_redis_down(*args, **kwargs):
        raise RuntimeError("redis down")

    monkeypatch.setattr(tvr, "requires_strict_auth_runtime", lambda: True)
    monkeypatch.setattr(tvr.aioredis, "from_url", raise_redis_down)
    tvr._redis_available = None
    tvr._redis_client = None

    with pytest.raises(HTTPException) as exc_info:
        await tvr.confirm_code(
            payload=tvr.ConfirmCodeRequest(email="lead@corp.com", code="123456", tool_name="ftl-checker"),
            request=_stub_request(),
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == tvr.CODE_STORE_UNAVAILABLE_DETAIL


@pytest.mark.asyncio
async def test_confirm_code_fails_closed_when_redis_unavailable_in_cloud_preview(tvr, monkeypatch):
    def raise_redis_down(*args, **kwargs):
        raise RuntimeError("redis down")

    monkeypatch.setenv("REGENGINE_ENV", "staging")
    monkeypatch.setenv("VERCEL_ENV", "preview")
    monkeypatch.setattr(tvr.aioredis, "from_url", raise_redis_down)
    tvr._redis_available = None
    tvr._redis_client = None

    with pytest.raises(HTTPException) as exc_info:
        await tvr.confirm_code(
            payload=tvr.ConfirmCodeRequest(email="lead@corp.com", code="123456", tool_name="ftl-checker"),
            request=_stub_request(),
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == tvr.CODE_STORE_UNAVAILABLE_DETAIL
