"""Tests for the partner gateway auth dependencies.

Covers ``get_partner_principal`` and ``require_partner_scope`` from
``services/admin/app/partner_gateway/auth.py``. The router itself is
exercised end-to-end through the FastAPI test client so we also catch
wiring regressions (e.g. forgetting to ``include_router``).

Mock pattern: stub ``shared.auth.get_key_store`` to return a fake store
with a controllable ``validate_key`` so we can exercise success / 401 /
403 paths without standing up a real database.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.partner_gateway.auth import (
    PartnerPrincipal,
    get_partner_principal,
    require_partner_scope,
)
from app.partner_gateway.router import router as partner_router


def _build_app() -> FastAPI:
    """Minimal FastAPI app that mounts only the partner router.

    Keeps tests fast and isolates failures to the gateway under test —
    the real admin app pulls in dozens of unrelated routers.
    """
    app = FastAPI()
    app.include_router(partner_router)
    return app


def _fake_validated_key(
    scopes: list[str], partner_id: str = "partner_acme"
) -> MagicMock:
    """Return an object that quacks like ``APIKeyResponse``.

    ``partner_id`` is a real column on ``api_keys`` (v076) — set it
    directly rather than via ``extra_data``. Reading it from extra_data
    would defeat the privilege boundary that promoting it to a column
    establishes.
    """
    k = MagicMock()
    k.key_id = "rge_partner1"
    k.scopes = scopes
    k.tenant_id = "00000000-0000-0000-0000-0000000000aa"
    k.partner_id = partner_id
    k.rate_limit_per_minute = 1000
    k.extra_data = {}  # explicitly NOT used for partner_id resolution
    return k


def _rate_info(allowed: bool = True, retry_after: int | None = None) -> MagicMock:
    info = MagicMock()
    info.allowed = allowed
    info.retry_after = retry_after
    return info


def _fake_db_store(
    validate_return,
    *,
    rate_allowed: bool = True,
    retry_after: int | None = None,
) -> MagicMock:
    fake_store = MagicMock()
    fake_store.validate_key = AsyncMock(return_value=validate_return)
    fake_store.check_rate_limit = AsyncMock(
        return_value=_rate_info(rate_allowed, retry_after)
    )
    return fake_store


# ---------------------------------------------------------------------------
# get_partner_principal
# ---------------------------------------------------------------------------


def test_missing_partner_header_returns_401():
    """No header → 401 with WWW-Authenticate set."""
    app = _build_app()
    client = TestClient(app)
    resp = client.get("/v1/partner/clients")
    assert resp.status_code == 401
    assert resp.headers.get("WWW-Authenticate") == "ApiKey"
    assert "Missing" in resp.json()["detail"]


def test_invalid_partner_key_returns_401():
    """Header present but key store rejects it → 401."""
    app = _build_app()

    fake_store = _fake_db_store(None)

    with patch(
        "app.partner_gateway.auth.get_key_store",
        return_value=fake_store,
    ), patch(
        "app.partner_gateway.auth.DatabaseAPIKeyStore",
        new=type(fake_store),  # isinstance(...) check picks the async branch
    ):
        client = TestClient(app)
        resp = client.get(
            "/v1/partner/clients",
            headers={"X-RegEngine-Partner-Key": "rge_bogus.bogus"},
        )
    assert resp.status_code == 401
    assert "Invalid" in resp.json()["detail"]


def test_valid_key_with_scope_passes_through_to_handler():
    """Happy path: valid key + matching scope → 200."""
    app = _build_app()

    fake_store = _fake_db_store(_fake_validated_key(["partner.clients.read"]))

    with patch(
        "app.partner_gateway.auth.get_key_store",
        return_value=fake_store,
    ), patch(
        "app.partner_gateway.auth.DatabaseAPIKeyStore",
        new=type(fake_store),
    ):
        client = TestClient(app)
        resp = client.get(
            "/v1/partner/clients",
            headers={"X-RegEngine-Partner-Key": "rge_partner1.secret"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["_stub"] is True
    assert body["_principal_key_id"] == "rge_partner1"
    fake_store.check_rate_limit.assert_awaited_once_with("rge_partner1", 1000)


def test_valid_key_over_rate_limit_returns_429():
    """Valid partner key still fails closed when its per-key quota is exhausted."""
    app = _build_app()
    fake_store = _fake_db_store(
        _fake_validated_key(["partner.clients.read"]),
        rate_allowed=False,
        retry_after=37,
    )

    with patch(
        "app.partner_gateway.auth.get_key_store",
        return_value=fake_store,
    ), patch(
        "app.partner_gateway.auth.DatabaseAPIKeyStore",
        new=type(fake_store),
    ):
        client = TestClient(app)
        resp = client.get(
            "/v1/partner/clients",
            headers={"X-RegEngine-Partner-Key": "rge_partner1.secret"},
        )

    assert resp.status_code == 429
    assert resp.headers["Retry-After"] == "37"


def test_valid_key_without_partner_id_returns_403():
    """Partner gateway keys must be bound to a real partner_id column value."""
    app = _build_app()
    fake_store = _fake_db_store(
        _fake_validated_key(["partner.clients.read"], partner_id=None)
    )

    with patch(
        "app.partner_gateway.auth.get_key_store",
        return_value=fake_store,
    ), patch(
        "app.partner_gateway.auth.DatabaseAPIKeyStore",
        new=type(fake_store),
    ):
        client = TestClient(app)
        resp = client.get(
            "/v1/partner/clients",
            headers={"X-RegEngine-Partner-Key": "rge_partner1.secret"},
        )

    assert resp.status_code == 403
    assert "not bound" in resp.json()["detail"]
    fake_store.check_rate_limit.assert_not_awaited()


def test_valid_key_with_namespace_wildcard_passes():
    """``partner.*`` should satisfy ``partner.clients.read``."""
    app = _build_app()

    fake_store = _fake_db_store(_fake_validated_key(["partner.*"]))

    with patch(
        "app.partner_gateway.auth.get_key_store",
        return_value=fake_store,
    ), patch(
        "app.partner_gateway.auth.DatabaseAPIKeyStore",
        new=type(fake_store),
    ):
        client = TestClient(app)
        resp = client.get(
            "/v1/partner/clients",
            headers={"X-RegEngine-Partner-Key": "rge_p.s"},
        )
    assert resp.status_code == 200


def test_valid_key_with_wrong_scope_returns_403():
    """Authentic key but missing the required scope → 403, not 401.

    This is the privilege-escalation guardrail: a partner key with
    ``partner.clients.read`` must NOT be able to hit
    ``getRevenueMetrics`` (which requires ``partner.revenue.read``).
    """
    app = _build_app()

    fake_store = _fake_db_store(_fake_validated_key(["partner.clients.read"]))

    with patch(
        "app.partner_gateway.auth.get_key_store",
        return_value=fake_store,
    ), patch(
        "app.partner_gateway.auth.DatabaseAPIKeyStore",
        new=type(fake_store),
    ):
        client = TestClient(app)
        resp = client.get(
            "/v1/partner/revenue",
            headers={"X-RegEngine-Partner-Key": "rge_p.s"},
        )
    assert resp.status_code == 403
    assert "partner.revenue.read" in resp.json()["detail"]


def test_full_wildcard_scope_passes_every_endpoint():
    """A key with ``*`` should pass any scope check (admin-tier)."""
    app = _build_app()

    fake_store = _fake_db_store(_fake_validated_key(["*"]))

    with patch(
        "app.partner_gateway.auth.get_key_store",
        return_value=fake_store,
    ), patch(
        "app.partner_gateway.auth.DatabaseAPIKeyStore",
        new=type(fake_store),
    ):
        client = TestClient(app)
        for path in ("/v1/partner/clients", "/v1/partner/revenue"):
            resp = client.get(path, headers={"X-RegEngine-Partner-Key": "rge_a.b"})
            assert resp.status_code == 200, path


# ---------------------------------------------------------------------------
# Parametrized scope-coverage matrix — pin EVERY endpoint to its scope
# ---------------------------------------------------------------------------


_DUMMY_UUID = "00000000-0000-0000-0000-0000000000aa"

# (method, path, expected_scope, optional_body)
# Keep this list in sync with regengine-partner-gateway-openapi.yaml's
# x-required-scopes — drift is a security bug.
_ENDPOINT_MATRIX = [
    ("GET", "/v1/partner/clients", "partner.clients.read", None),
    (
        "POST",
        "/v1/partner/clients",
        "partner.clients.write",
        {"name": "Acme", "billing_tier": "growth"},
    ),
    ("GET", f"/v1/partner/clients/{_DUMMY_UUID}", "partner.clients.read", None),
    (
        "PATCH",
        f"/v1/partner/clients/{_DUMMY_UUID}",
        "partner.clients.write",
        {"name": "renamed"},
    ),
    (
        "GET",
        f"/v1/partner/clients/{_DUMMY_UUID}/compliance",
        "partner.compliance.read",
        None,
    ),
    (
        "POST",
        f"/v1/partner/clients/{_DUMMY_UUID}/evidence/export",
        "partner.evidence.export",
        {"format": "zip"},
    ),
    (
        "GET",
        f"/v1/partner/clients/{_DUMMY_UUID}/api-keys",
        "partner.api_keys.read",
        None,
    ),
    (
        "POST",
        f"/v1/partner/clients/{_DUMMY_UUID}/api-keys",
        "partner.api_keys.write",
        {"name": "k", "scopes": ["read"]},
    ),
    ("GET", "/v1/partner/revenue", "partner.revenue.read", None),
    ("GET", "/v1/partner/revenue/payouts", "partner.payouts.read", None),
    ("GET", "/v1/partner/branding", "partner.branding.read", None),
    ("PUT", "/v1/partner/branding", "partner.branding.write", {}),
]


def _call(client: TestClient, method: str, path: str, body, headers):
    fn = {
        "GET": client.get,
        "POST": client.post,
        "PATCH": client.patch,
        "PUT": client.put,
        "DELETE": client.delete,
    }[method]
    if body is None:
        return fn(path, headers=headers)
    return fn(path, json=body, headers=headers)


@pytest.mark.parametrize("method,path,scope,body", _ENDPOINT_MATRIX)
def test_endpoint_passes_with_exact_scope(method, path, scope, body):
    """Each endpoint succeeds when the key carries exactly its scope."""
    app = _build_app()
    fake_store = _fake_db_store(_fake_validated_key([scope]))

    with patch(
        "app.partner_gateway.auth.get_key_store", return_value=fake_store
    ), patch(
        "app.partner_gateway.auth.DatabaseAPIKeyStore", new=type(fake_store)
    ):
        client = TestClient(app)
        resp = _call(
            client, method, path, body, {"X-RegEngine-Partner-Key": "rge_x.y"}
        )
    # Stub handlers return 200/201/202 — any 2xx counts as scope-pass.
    assert 200 <= resp.status_code < 300, (
        f"{method} {path} expected 2xx with scope {scope}, got {resp.status_code}: "
        f"{resp.text[:200]}"
    )


@pytest.mark.parametrize("method,path,scope,body", _ENDPOINT_MATRIX)
def test_endpoint_403s_with_unrelated_scope(method, path, scope, body):
    """Each endpoint returns 403 when the key holds a different scope.

    Uses ``partner.unrelated.read`` — not a wildcard, not the right
    namespace. If any endpoint returns 200 here, scope enforcement is
    not wired up for that route.
    """
    app = _build_app()
    fake_store = _fake_db_store(_fake_validated_key(["partner.unrelated.read"]))

    with patch(
        "app.partner_gateway.auth.get_key_store", return_value=fake_store
    ), patch(
        "app.partner_gateway.auth.DatabaseAPIKeyStore", new=type(fake_store)
    ):
        client = TestClient(app)
        resp = _call(
            client, method, path, body, {"X-RegEngine-Partner-Key": "rge_x.y"}
        )
    assert resp.status_code == 403, (
        f"{method} {path} should 403 without {scope}, got {resp.status_code}"
    )


# ---------------------------------------------------------------------------
# Direct dep tests — exercise the dependency objects without HTTP plumbing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_partner_id_is_not_read_from_extra_data():
    """Privilege-boundary regression: ``extra_data.partner_id`` must be ignored.

    ``extra_data`` is partner-writable through ``update_key(metadata=...)``.
    If the gateway resolved ``partner_id`` from there, a compromised
    partner could reassign themselves to another partner's tenants
    without going through ``change_scopes``. Pin that the dep reads
    only from the real column.
    """
    from app.partner_gateway.auth import get_partner_principal

    # Forge a key whose extra_data CLAIMS to be partner_evil but whose
    # real partner_id column is partner_legit.
    fake_key = MagicMock()
    fake_key.key_id = "rge_x"
    fake_key.scopes = ["partner.clients.read"]
    fake_key.tenant_id = None
    fake_key.partner_id = "partner_legit"
    fake_key.rate_limit_per_minute = 1000
    fake_key.extra_data = {"partner_id": "partner_evil"}

    fake_store = _fake_db_store(fake_key)

    fake_request = MagicMock()
    fake_request.url.path = "/v1/partner/clients"

    with patch(
        "app.partner_gateway.auth.get_key_store",
        return_value=fake_store,
    ), patch(
        "app.partner_gateway.auth.DatabaseAPIKeyStore",
        new=type(fake_store),
    ):
        principal = await get_partner_principal(
            request=fake_request, x_regengine_partner_key="rge_x.s"
        )

    assert principal.partner_id == "partner_legit"
    assert principal.partner_id != "partner_evil"


def test_list_clients_empty_returns_200_not_404():
    """Contract: a partner with zero clients must get 200 + empty list, not 404.

    REST hygiene — an empty collection is still a successful collection.
    Returning 404 here would force partner SDKs to special-case
    "first-time onboarding" against "missing endpoint", which is the
    exact ambiguity that triggers retry storms. This test pins the
    contract against the current stub shape ``{"data": [], ...}``; once
    Agent 2's real-data wiring lands the assertion still holds because
    the contract is "empty list, not 404", not "stub payload".
    """
    app = _build_app()

    fake_store = _fake_db_store(_fake_validated_key(["partner.clients.read"]))

    with patch(
        "app.partner_gateway.auth.get_key_store",
        return_value=fake_store,
    ), patch(
        "app.partner_gateway.auth.DatabaseAPIKeyStore",
        new=type(fake_store),
    ):
        client = TestClient(app)
        resp = client.get(
            "/v1/partner/clients",
            headers={"X-RegEngine-Partner-Key": "rge_partner1.secret"},
        )

    assert resp.status_code == 200, (
        f"empty client list must be 200, got {resp.status_code}: {resp.text[:200]}"
    )
    body = resp.json()
    assert "data" in body, f"response missing 'data' key: {body}"
    assert body["data"] == [], f"expected empty list, got {body['data']}"
    assert isinstance(body["data"], list)


@pytest.mark.asyncio
async def test_require_partner_scope_returns_principal_on_success():
    """When the scope passes, the dep returns the principal unchanged."""
    dep = require_partner_scope("partner.clients.read")
    principal = PartnerPrincipal(
        key_id="rge_x",
        scopes=["partner.clients.read"],
        partner_id="p1",
    )
    result = await dep(principal=principal)
    assert result is principal


@pytest.mark.asyncio
async def test_require_partner_scope_raises_403_when_scope_missing():
    """Missing scope must raise HTTPException(403) with the scope name."""
    dep = require_partner_scope("partner.revenue.read")
    principal = PartnerPrincipal(
        key_id="rge_x",
        scopes=["partner.clients.read"],
    )
    with pytest.raises(HTTPException) as exc:
        await dep(principal=principal)
    assert exc.value.status_code == 403
    assert "partner.revenue.read" in exc.value.detail
