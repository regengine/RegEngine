"""Logout must reject undecodable bearer tokens with 401, not 500.

The ``get_current_user`` dependency can authenticate a request without a
local JWT decode (opaque session cookie, or a foreign IdP token accepted
upstream in non-strict runtimes). ``logout`` then decodes the presented
bearer value itself; a value that is not a valid local session token used
to raise a raw PyJWT error out of the endpoint (HTTP 500). It must be a
generic 401 with the failure detail kept in the server log.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import jwt
import pytest
from fastapi import HTTPException

_repo_root = Path(__file__).resolve().parents[3]
_service_dir = Path(__file__).resolve().parents[2]
for _p in (_repo_root, _service_dir):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

os.environ.setdefault("ADMIN_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("AUTH_SECRET_KEY", "logout-bad-token-test-secret")
os.environ.setdefault("SESSION_STORE_BACKEND", "memory")


def _request(headers: dict[str, str] | None = None):
    return SimpleNamespace(
        headers=headers or {},
        client=SimpleNamespace(host="127.0.0.1"),
        state=SimpleNamespace(),
    )


def _user():
    return SimpleNamespace(
        id=uuid.uuid4(),
        email="alice@example.com",
        status="active",
        is_sysadmin=False,
        token_version=0,
        last_login_at=None,
    )


@pytest.mark.asyncio
async def test_logout_rejects_foreign_signed_token_with_401():
    """A well-formed JWT signed by an unknown key is a 401, not a 500."""
    from services.admin.app.auth.sessions_router import logout
    from services.admin.app.session_store import InMemorySessionStore

    # nosemgrep: python.jwt.security.jwt-hardcode.jwt-python-hardcoded-secret -- test-only foreign signing key
    foreign = jwt.encode({"sub": "someone-else"}, "foreign-key", algorithm="HS256")
    with pytest.raises(HTTPException) as exc:
        await logout(
            request=_request({"Authorization": f"Bearer {foreign}"}),
            current_user=_user(),
            session_store=InMemorySessionStore(),
        )
    assert exc.value.status_code == 401
    assert exc.value.headers.get("WWW-Authenticate") == "Bearer"


@pytest.mark.asyncio
async def test_logout_rejects_malformed_token_with_401():
    """A non-JWT bearer value is a 401, not a 500."""
    from services.admin.app.auth.sessions_router import logout
    from services.admin.app.session_store import InMemorySessionStore

    with pytest.raises(HTTPException) as exc:
        await logout(
            request=_request({"Authorization": "Bearer not-a-token"}),
            current_user=_user(),
            session_store=InMemorySessionStore(),
        )
    assert exc.value.status_code == 401
