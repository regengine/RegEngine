"""Tests for the reusable partner-tier auth primitives.

Covers ``get_partner_principal`` and ``require_partner_scope`` from
``services/shared/partner_auth.py``. Exercises the dependency callables
directly without mounting a FastAPI app — the gateway router these
primitives originally served has been retired (Path B, W8.F).

Mock pattern: stub ``shared.auth.get_key_store`` to return a fake store
with a controllable ``validate_key`` so we can exercise success / 401 /
403 / 429 paths without standing up a real database.
"""
from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

import shared.partner_auth as partner_auth


@contextmanager
def _patched_partner_store(fake_store):
    """Patch the auth module's resolver to return the fake store."""
    with patch.object(
        partner_auth,
        "get_key_store",
        return_value=fake_store,
    ), patch.object(
        partner_auth,
        "DatabaseAPIKeyStore",
        new=type(fake_store),
    ):
        yield


def _fake_validated_key(
    scopes: list[str], partner_id: str | None = "partner_acme"
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


def _fake_request(path: str = "/partner/anything") -> MagicMock:
    req = MagicMock()
    req.url.path = path
    return req


# ---------------------------------------------------------------------------
# get_partner_principal
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_partner_header_returns_401():
    """No header → 401 with WWW-Authenticate set."""
    with pytest.raises(HTTPException) as exc:
        await partner_auth.get_partner_principal(
            request=_fake_request(), x_regengine_partner_key=None
        )
    assert exc.value.status_code == 401
    assert exc.value.headers.get("WWW-Authenticate") == "ApiKey"
    assert "Missing" in exc.value.detail


@pytest.mark.asyncio
async def test_invalid_partner_key_returns_401():
    """Header present but key store rejects it → 401."""
    fake_store = _fake_db_store(None)
    with _patched_partner_store(fake_store):
        with pytest.raises(HTTPException) as exc:
            await partner_auth.get_partner_principal(
                request=_fake_request(),
                x_regengine_partner_key="rge_bogus.bogus",
            )
    assert exc.value.status_code == 401
    assert "Invalid" in exc.value.detail


@pytest.mark.asyncio
async def test_valid_key_returns_principal_and_checks_rate_limit():
    """Happy path: valid key + bound partner_id → typed principal."""
    fake_store = _fake_db_store(_fake_validated_key(["partner.clients.read"]))
    with _patched_partner_store(fake_store):
        principal = await partner_auth.get_partner_principal(
            request=_fake_request(),
            x_regengine_partner_key="rge_partner1.secret",
        )
    assert principal.key_id == "rge_partner1"
    assert principal.partner_id == "partner_acme"
    assert principal.scopes == ["partner.clients.read"]
    assert principal.auth_mode == "partner_key"
    fake_store.check_rate_limit.assert_awaited_once_with("rge_partner1", 1000)


@pytest.mark.asyncio
async def test_valid_key_without_partner_id_returns_403():
    """Partner-tier keys must be bound to a real partner_id column value."""
    fake_store = _fake_db_store(
        _fake_validated_key(["partner.clients.read"], partner_id=None)
    )
    with _patched_partner_store(fake_store):
        with pytest.raises(HTTPException) as exc:
            await partner_auth.get_partner_principal(
                request=_fake_request(),
                x_regengine_partner_key="rge_partner1.secret",
            )
    assert exc.value.status_code == 403
    assert "not bound" in exc.value.detail
    fake_store.check_rate_limit.assert_not_awaited()


@pytest.mark.asyncio
async def test_valid_key_over_rate_limit_returns_429():
    """Valid key still fails closed when its per-key quota is exhausted."""
    fake_store = _fake_db_store(
        _fake_validated_key(["partner.clients.read"]),
        rate_allowed=False,
        retry_after=37,
    )
    with _patched_partner_store(fake_store):
        with pytest.raises(HTTPException) as exc:
            await partner_auth.get_partner_principal(
                request=_fake_request(),
                x_regengine_partner_key="rge_partner1.secret",
            )
    assert exc.value.status_code == 429
    assert exc.value.headers["Retry-After"] == "37"


@pytest.mark.asyncio
async def test_partner_id_is_not_read_from_extra_data():
    """Privilege-boundary regression: ``extra_data.partner_id`` must be ignored.

    ``extra_data`` is partner-writable through ``update_key(metadata=...)``.
    If the dep resolved ``partner_id`` from there, a compromised partner
    could reassign themselves to another partner's tenants without going
    through ``change_scopes``. Pin that the dep reads only from the real
    column.
    """
    fake_key = MagicMock()
    fake_key.key_id = "rge_x"
    fake_key.scopes = ["partner.clients.read"]
    fake_key.tenant_id = None
    fake_key.partner_id = "partner_legit"
    fake_key.rate_limit_per_minute = 1000
    fake_key.extra_data = {"partner_id": "partner_evil"}

    fake_store = _fake_db_store(fake_key)

    with _patched_partner_store(fake_store):
        principal = await partner_auth.get_partner_principal(
            request=_fake_request(), x_regengine_partner_key="rge_x.s"
        )

    assert principal.partner_id == "partner_legit"
    assert principal.partner_id != "partner_evil"


# ---------------------------------------------------------------------------
# require_partner_scope
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_require_partner_scope_returns_principal_on_success():
    """When the scope check passes, the dep returns the principal unchanged."""
    dep = partner_auth.require_partner_scope("partner.clients.read")
    principal = partner_auth.PartnerPrincipal(
        key_id="rge_x",
        scopes=["partner.clients.read"],
        partner_id="p1",
    )
    result = await dep(principal=principal)
    assert result is principal


@pytest.mark.asyncio
async def test_require_partner_scope_raises_403_when_scope_missing():
    """Missing scope must raise HTTPException(403) with the scope name."""
    dep = partner_auth.require_partner_scope("partner.revenue.read")
    principal = partner_auth.PartnerPrincipal(
        key_id="rge_x",
        scopes=["partner.clients.read"],
    )
    with pytest.raises(HTTPException) as exc:
        await dep(principal=principal)
    assert exc.value.status_code == 403
    assert "partner.revenue.read" in exc.value.detail
