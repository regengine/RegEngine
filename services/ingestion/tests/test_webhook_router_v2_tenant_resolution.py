"""Unit tests for ``_resolve_ingest_tenant_id`` (webhook_router_v2/tenant.py, #2069).

Covers every branch of tenant resolution without a database:
scoped-key callers must not be overridden by body/header tenant values (403),
and legacy callers fall back payload -> API-key lookup -> X-Tenant-ID -> 400.

Collaborators are resolved through the package namespace (``_pkg``) at call
time, so tests monkeypatch attributes on ``services.ingestion.app.webhook_router_v2``.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from services.ingestion.app import webhook_router_v2 as wrv2
from services.ingestion.app.authz import IngestionPrincipal
from services.ingestion.app.webhook_router_v2.tenant import _resolve_ingest_tenant_id


def _make_principal(tenant_id: str | None = None) -> IngestionPrincipal:
    return IngestionPrincipal(
        key_id="test-key-id",
        scopes=[],
        tenant_id=tenant_id,
        auth_mode="scoped_key",
    )


@pytest.fixture
def validate_calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Replace ``validate_tenant_id`` with a recorder; returns the call list."""
    calls: list[str] = []
    monkeypatch.setattr(wrv2, "validate_tenant_id", calls.append)
    return calls


@pytest.fixture
def lookup(monkeypatch: pytest.MonkeyPatch):
    """Replace the API-key -> tenant lookup with a controllable stub."""

    class _Lookup:
        def __init__(self) -> None:
            self.return_value: str | None = None
            self.calls: list[str] = []

        def __call__(self, raw_api_key: str) -> str | None:
            self.calls.append(raw_api_key)
            return self.return_value

    stub = _Lookup()
    monkeypatch.setattr(wrv2, "_lookup_tenant_id_for_api_key", stub)
    return stub


# --- scoped-key principal --------------------------------------------------


def test_scoped_principal_with_matching_payload_returns_principal_tenant(validate_calls):
    result = _resolve_ingest_tenant_id(
        payload_tenant_id="tenant123",
        principal=_make_principal("tenant123"),
        x_regengine_api_key=None,
        x_tenant_id=None,
    )
    assert result == "tenant123"
    assert validate_calls == ["tenant123"]


def test_scoped_principal_with_divergent_payload_raises_403(validate_calls):
    with pytest.raises(HTTPException) as exc_info:
        _resolve_ingest_tenant_id(
            payload_tenant_id="tenant456",
            principal=_make_principal("tenant123"),
            x_regengine_api_key=None,
            x_tenant_id=None,
        )
    assert exc_info.value.status_code == 403
    assert "payload tenant_id" in str(exc_info.value.detail)
    assert validate_calls == []


def test_scoped_principal_with_divergent_header_raises_403(validate_calls):
    with pytest.raises(HTTPException) as exc_info:
        _resolve_ingest_tenant_id(
            payload_tenant_id=None,
            principal=_make_principal("tenant123"),
            x_regengine_api_key=None,
            x_tenant_id="tenant456",
        )
    assert exc_info.value.status_code == 403
    assert "X-Tenant-ID" in str(exc_info.value.detail)
    assert validate_calls == []


# --- legacy callers (no principal tenant) ----------------------------------


def test_legacy_uses_payload_tenant(validate_calls, lookup):
    result = _resolve_ingest_tenant_id(
        payload_tenant_id="tenant789",
        principal=_make_principal(None),
        x_regengine_api_key="raw-key-123",
        x_tenant_id="other",
    )
    assert result == "tenant789"
    assert lookup.calls == []  # payload wins; lookup never consulted
    assert validate_calls == ["tenant789"]


def test_legacy_uses_api_key_lookup_when_no_payload(validate_calls, lookup):
    lookup.return_value = "tenant456"
    result = _resolve_ingest_tenant_id(
        payload_tenant_id=None,
        principal=_make_principal(None),
        x_regengine_api_key="raw-key-123",
        x_tenant_id="other",
    )
    assert result == "tenant456"
    assert lookup.calls == ["raw-key-123"]
    assert validate_calls == ["tenant456"]


def test_legacy_falls_back_to_header_when_lookup_returns_none(validate_calls, lookup):
    lookup.return_value = None
    result = _resolve_ingest_tenant_id(
        payload_tenant_id=None,
        principal=_make_principal(None),
        x_regengine_api_key="raw-key-123",
        x_tenant_id="tenant789",
    )
    assert result == "tenant789"
    assert lookup.calls == ["raw-key-123"]
    assert validate_calls == ["tenant789"]


def test_legacy_with_nothing_resolvable_raises_400(validate_calls, lookup, monkeypatch):
    errors: list[str] = []
    monkeypatch.setattr(wrv2, "logger", type("L", (), {"error": staticmethod(errors.append)})())
    lookup.return_value = None
    with pytest.raises(HTTPException) as exc_info:
        _resolve_ingest_tenant_id(
            payload_tenant_id=None,
            principal=_make_principal(None),
            x_regengine_api_key="raw-key-123",
            x_tenant_id=None,
        )
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Tenant context required"
    assert validate_calls == []
    assert errors == ["Webhook rejected: no tenant_id resolved"]


@pytest.mark.parametrize(
    ("payload", "api_key", "lookup_result", "header", "expected"),
    [
        ("p-tenant", None, None, None, "p-tenant"),
        (None, "key", "k-tenant", None, "k-tenant"),
        (None, "key", None, "h-tenant", "h-tenant"),
    ],
)
def test_validate_tenant_id_called_on_every_legacy_success_path(
    validate_calls, lookup, payload, api_key, lookup_result, header, expected
):
    lookup.return_value = lookup_result
    result = _resolve_ingest_tenant_id(
        payload_tenant_id=payload,
        principal=_make_principal(None),
        x_regengine_api_key=api_key,
        x_tenant_id=header,
    )
    assert result == expected
    assert validate_calls == [expected]
