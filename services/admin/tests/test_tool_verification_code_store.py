"""Regression coverage for public tool email verification codes."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
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
    save_lead.assert_called_once_with("lead@corp.com", "corp.com", "ftl-checker")


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
