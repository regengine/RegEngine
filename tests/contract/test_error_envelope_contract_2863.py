"""The curated public spec must accept actual error producers — #2863.

Shared exception handlers return nested errors. Middleware can return string
errors or a detail-only tenant rejection without reaching those handlers.
Validate real responses and reject malformed lookalikes, rather than claiming
every error has the same shape or accepting arbitrary JSON.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from jsonschema import Draft4Validator

from tests.contract.public_openapi import load_public_openapi


@pytest.fixture(scope="module")
def spec() -> dict:
    return load_public_openapi()


@pytest.fixture(scope="module")
def error_validator(spec):
    return Draft4Validator(
        {
            "$ref": "#/components/schemas/ErrorResponse",
            "components": spec["components"],
        }
    )


@pytest.fixture(scope="module")
def client():
    """A TestClient over the deployed monolith, with handlers installed."""
    from fastapi.testclient import TestClient

    from server.main import app

    return TestClient(app, raise_server_exceptions=False)


def _error_responses(spec: dict) -> list[tuple[str, str, str, dict]]:
    out = []
    for path, item in spec.get("paths", {}).items():
        for method, operation in item.items():
            if not isinstance(operation, dict):
                continue
            for status, response in (operation.get("responses") or {}).items():
                if isinstance(status, str) and status[:1] in {"4", "5"}:
                    out.append((path, method, status, response))
    return out


# --- The document ---------------------------------------------------------


def test_spec_declares_error_responses(spec):
    """Guard the guard: with no 4xx/5xx responses the checks below are vacuous."""
    assert _error_responses(spec), "No 4xx/5xx responses found in the curated public spec."


def test_no_operation_advertises_default_fastapi_validation_errors(spec):
    """The shared validation handler returns nested error.details, not detail[]."""
    offenders = [
        f"{method.upper()} {path} -> {status}"
        for path, method, status, response in _error_responses(spec)
        if "HTTPValidationError" in json.dumps(response)
    ]
    assert not offenders, (
        "These operations document FastAPI's default HTTPValidationError "
        '({"detail": [...]}), which the shared validation handler does not return '
        f"(#2863):\n  " + "\n  ".join(offenders)
    )


def test_every_error_response_uses_the_documented_variants(spec):
    def response_schema(response):
        if "$ref" in response:
            response = spec["components"]["responses"][response["$ref"].split("/")[-1]]
        return response["content"]["application/json"]["schema"]

    missing = [
        f"{method.upper()} {path} -> {status}"
        for path, method, status, response in _error_responses(spec)
        if response_schema(response) != {"$ref": "#/components/schemas/ErrorResponse"}
    ]
    assert not missing, "Error responses not pointing at the supported ErrorResponse variants:\n  " + "\n  ".join(
        missing
    )


def test_envelope_schema_requires_type_and_message(spec):
    schema = spec["components"]["schemas"]["ErrorEnvelope"]
    inner = schema["properties"]["error"]
    assert schema["required"] == ["error"]
    assert set(inner["required"]) == {"type", "message"}
    # Dict-detail call sites keep bespoke fields such as `code`; a schema that
    # forbade them would be a second inaccurate spec.
    assert inner["additionalProperties"] is True


# --- The running server ---------------------------------------------------


@pytest.mark.parametrize(
    ("path", "expected_status", "producer"),
    [
        ("/nope", 404, "HTTPException with a string detail"),
        ("/api/v1/records?limit=abc", 422, "RequestValidationError handler"),
        ("/api/v1/fda/export", 401, "HTTPException with a dict detail"),
    ],
)
def test_live_errors_match_the_published_envelope(client, error_validator, path, expected_status, producer):
    """One case per producer — the three that used to disagree."""
    response = client.get(path)
    assert response.status_code == expected_status, producer

    body = response.json()
    error_validator.validate(body)
    assert "detail" not in body, f"{producer} bypassed the shared handler's nested error envelope."
    assert "error" in body, f"{producer} did not use the shared envelope: {body}"

    error = body["error"]
    assert isinstance(error.get("type"), str) and error["type"], (
        f"{producer} produced an envelope with no usable 'type': {error}. A client cannot classify this error (#2863)."
    )
    assert isinstance(error.get("message"), str) and error["message"], (
        f"{producer} produced an envelope with no 'message': {error}"
    )


def test_dict_detail_keeps_its_original_fields(client):
    """Normalization must add, never replace.

    `/api/v1/fda/export` raises `HTTPException(detail={"code": "E_NO_TENANT", ...})`.
    Callers already reading `code` must keep working, so `code` survives alongside
    the `type` that makes the envelope uniform.
    """
    error = client.get("/api/v1/fda/export").json()["error"]
    assert error.get("code") == "E_NO_TENANT", f"the original 'code' field was lost in normalization: {error}"
    assert error["type"] == "E_NO_TENANT", (
        "'type' should fall back to the dict's own 'code' rather than a generic "
        f"http_<status>, so one field classifies every error: {error}"
    )


def test_validation_errors_still_carry_per_field_details(client):
    """`details` is the payload clients need; uniformity must not cost it."""
    error = client.get("/api/v1/records?limit=abc").json()["error"]
    assert error["type"] == "validation_error"
    assert isinstance(error.get("details"), list) and error["details"], (
        f"per-field validation details were lost: {error}"
    )


@pytest.mark.parametrize("producer", ["size", "rate_limit", "tenant", "idempotency"])
def test_middleware_errors_match_the_published_variants(error_validator, monkeypatch, producer):
    from unittest.mock import AsyncMock

    from starlette.requests import Request

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/webhooks/ingest",
            "headers": [(b"content-length", b"invalid")],
            "client": ("testclient", 1234),
        }
    )
    call_next = AsyncMock(side_effect=AssertionError("rejected request reached the route"))
    if producer == "size":
        from shared.request_safety import RequestSizeLimitMiddleware

        response = asyncio.run(RequestSizeLimitMiddleware(None).dispatch(request, call_next))
        assert response.status_code == 400
    elif producer == "rate_limit":
        from shared import tenant_rate_limiting

        monkeypatch.setattr(tenant_rate_limiting._bucket, "is_allowed", lambda *_: (False, 0))
        response = asyncio.run(tenant_rate_limiting.TenantRateLimitMiddleware(None).dispatch(request, call_next))
        assert response.status_code == 429
    elif producer == "tenant":
        from shared.middleware.tenant_context import TenantContextMiddleware

        middleware = TenantContextMiddleware(None)
        monkeypatch.setattr(middleware, "_extract_tenant_id", AsyncMock(side_effect=ValueError("invalid tenant")))
        response = asyncio.run(middleware.dispatch(request, call_next))
        assert response.status_code == 401
    else:
        from shared.idempotency import IdempotencyMiddleware

        response = IdempotencyMiddleware._error(409, "idempotency_key_conflict")
    error_validator.validate(json.loads(response.body))
    call_next.assert_not_called()


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"error": {}},
        {"error": {"type": "http_401"}},
        {"error": {"type": "http_401", "message": 123}},
        {"error": 123},
        {"error": "rate_limit_exceeded"},
        {"error": "unknown_code"},
        {"detail": []},
        {"detail": "denied", "unexpected": True},
    ],
)
def test_error_schema_rejects_malformed_envelopes(error_validator, body):
    assert not error_validator.is_valid(body)
