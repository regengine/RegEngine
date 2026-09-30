"""The published error envelope must be the one the server actually returns — #2863.

FastAPI auto-documents 422 as ``HTTPValidationError`` → ``{"detail": [...]}``.
This application installs its own handlers (``install_exception_handlers`` in
``services/shared/error_handling.py``), so **nothing ever returns a top-level
``detail``**. 44 of the 45 public operations advertised a field that is never
present, and any SDK generated from the spec degraded to "unknown error" on the
most common 4xx.

Three distinct producers reach a client, and before #2863 they disagreed:

======================================  ==========================================
producer                                envelope
======================================  ==========================================
``RequestValidationError`` handler      ``{"error": {"type": "validation_error",
                                        "message", "details"}}``
``HTTPException(422, "text")``          ``{"error": {"type": "http_422",
(12 call sites)                         "message"}}``
``HTTPException(422, {...})``           the dict **verbatim** — commonly
(17 call sites)                         ``{"code", "message"}``, no ``type``
======================================  ==========================================

So a client could not read one field to classify an error. ``_safe_http_error_content``
now normalizes the dict case: ``type`` and ``message`` are always present, and
**every original key is preserved** so callers already reading ``code`` are
unaffected. That single shape is what the spec now publishes.

These tests are deliberately paired. Asserting the spec alone would re-create the
original defect in a new place — a document that agrees with nothing. Asserting
runtime alone would let the spec drift again. Each test that checks the document
has a partner that checks a live response.
"""

from __future__ import annotations

import json

import pytest


@pytest.fixture(scope="module")
def spec(published_spec) -> dict:
    return published_spec()


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
                    if "$ref" in response:
                        prefix = "#/components/responses/"
                        assert response["$ref"].startswith(prefix)
                        response = spec["components"]["responses"][response["$ref"][len(prefix) :]]
                    out.append((path, method, status, response))
    return out


# --- The document ---------------------------------------------------------


def test_spec_declares_error_responses(spec):
    """Guard the guard: with no 4xx/5xx responses the checks below are vacuous."""
    assert _error_responses(spec), (
        "No 4xx/5xx responses found in the published spec. Either the generator "
        "stopped emitting them or this test's traversal has drifted."
    )


def test_no_operation_advertises_a_top_level_detail(spec):
    """`{"detail": [...]}` is FastAPI's default and this app never returns it."""
    offenders = [
        f"{method.upper()} {path} -> {status}"
        for path, method, status, response in _error_responses(spec)
        if "HTTPValidationError" in json.dumps(response)
    ]
    assert not offenders, (
        "These operations document FastAPI's default HTTPValidationError "
        '({"detail": [...]}), which this application never returns — '
        'install_exception_handlers wraps every error in {"error": {...}} '
        f"(#2863):\n  " + "\n  ".join(offenders)
    )


def test_every_error_response_uses_the_shared_envelope(spec):
    missing = [
        f"{method.upper()} {path} -> {status}"
        for path, method, status, response in _error_responses(spec)
        if "ErrorResponse" not in json.dumps(response)
    ]
    assert not missing, "Error responses not pointing at the shared ErrorEnvelope schema:\n  " + "\n  ".join(missing)


def test_envelope_schema_requires_type_and_message(spec):
    schema = spec["components"]["schemas"]["ErrorResponse"]
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
def test_live_errors_match_the_published_envelope(client, path, expected_status, producer):
    """One case per producer — the three that used to disagree."""
    response = client.get(path)
    assert response.status_code == expected_status, producer

    body = response.json()
    assert "detail" not in body, f"{producer} returned a top-level 'detail'; the spec no longer documents one."
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
