"""Regression tests for the webhook header-presence gate.

The gate never reads a generic environment key. A presented credential is
validated by the database-backed principal dependency later in the chain.
"""

import app.webhook_router_v2 as wr
import pytest
from fastapi import HTTPException


def test_header_required() -> None:
    with pytest.raises(HTTPException) as exc:
        wr._verify_api_key(x_regengine_api_key=None)
    assert exc.value.status_code == 401


@pytest.mark.parametrize("environment", ["development", "test", "staging", "production"])
def test_present_header_defers_validation_without_generic_env_key(
    monkeypatch: pytest.MonkeyPatch,
    environment: str,
) -> None:
    monkeypatch.setenv("REGENGINE_ENV", environment)
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("REGENGINE_API_KEY", raising=False)

    wr._verify_api_key(x_regengine_api_key="rge_tenant.candidate")  # pragma: allowlist secret
