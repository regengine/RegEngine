"""Regression coverage for CodeQL py/clear-text-logging-sensitive-data.

``resolve_tenant_id`` rejects a request whose body/header tenant conflicts
with the tenant bound to the presented API key. The rejection warning must
stay useful (it names the request-supplied tenant that was rejected) while
never logging the api-key-derived tenant value, which flows from the raw
API key material.

Alert: services/ingestion/app/shared/tenant_resolution.py:93
"""

from __future__ import annotations

import logging
import secrets
import uuid

import pytest
from app.shared import tenant_resolution
from app.shared.tenant_resolution import resolve_tenant_id
from fastapi import HTTPException

_API_KEY_TENANT = str(uuid.uuid4())
_REQUESTED_TENANT = str(uuid.uuid4())


def test_tenant_override_rejected_logs_request_without_api_key_tenant(monkeypatch, caplog):
    monkeypatch.setattr(
        tenant_resolution,
        "_lookup_api_key_tenant_id",
        lambda _key: _API_KEY_TENANT,
    )

    with caplog.at_level(logging.WARNING, logger=tenant_resolution.logger.name):
        with pytest.raises(HTTPException) as exc_info:
            resolve_tenant_id(
                explicit_tenant_id=_REQUESTED_TENANT,
                x_tenant_id=None,
                x_regengine_api_key=secrets.token_urlsafe(),  # pragma: allowlist secret
            )

    assert exc_info.value.status_code == 403

    records = [r for r in caplog.records if "tenant_override_rejected" in r.getMessage()]
    assert len(records) == 1
    message = records[0].getMessage()
    # Useful: identifies which requested tenant was rejected.
    assert _REQUESTED_TENANT in message
    # Safe: the api-key-derived tenant value is never emitted.
    assert _API_KEY_TENANT not in message
    assert _API_KEY_TENANT not in str(records[0].args)
