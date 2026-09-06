"""The retired master-key mechanism cannot replace high-assurance admin auth.

The previous comparison tests predated retirement of X-Admin-Key. Keep every
candidate class covered as a denied credential rather than restoring that
privileged bypass to make an old happy-path test pass.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from services.admin.app import privileged_auth, routes


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "candidate",
    [
        None,
        "",
        "x",
        "synthetic-admin-master-key",
        "synthetic-admin-master-ke",
        "synthetic-admin-master-keyx",
        "SYNTHETIC-ADMIN-MASTER-KEY",
        "x" * 26,
        "sünthetic-key",
    ],
)
async def test_legacy_header_never_authenticates(candidate):
    headers = [] if candidate is None else [(b"x-admin-key", candidate.encode())]
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/admin/keys",
            "headers": headers,
            "client": ("203.0.113.7", 1234),
            "query_string": b"",
            "state": {},
        }
    )
    throttle = SimpleNamespace(is_limited=AsyncMock(return_value=False), record_failure=AsyncMock(), reset=AsyncMock())
    with pytest.raises(HTTPException) as exc:
        await privileged_auth.require_sysadmin_high_assurance(
            request=request, db=MagicMock(), crypto_service=MagicMock(), throttle=throttle
        )
    assert exc.value.status_code == 401


def test_legacy_verifier_is_absent():
    assert not hasattr(routes, "verify_admin_key")
