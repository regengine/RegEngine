"""QA5: auth and tenant boundaries for shared/auth.py and tenant_context.py."""

import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import HTTPException

SERVICES_DIR = Path(__file__).resolve().parents[2]
VALIDATE_SCRIPT = (
    "import os, sys; "
    f"sys.path.insert(0, {str(SERVICES_DIR)!r}); "
    "from shared.auth import validate_auth_config; "
    "validate_auth_config(); "
    "print('STARTED_OK')"
)

_STRIPPED_ENV = (
    "RAILWAY_ENVIRONMENT",
    "RAILWAY_ENVIRONMENT_NAME",
    "RAILWAY_ENVIRONMENT_ID",
    "RAILWAY_PROJECT_NAME",
    "RAILWAY_PROJECT_ID",
    "RAILWAY_SERVICE_NAME",
    "RAILWAY_SERVICE_ID",
    "VERCEL_ENV",
    "AUTH_SECRET_KEY",
    "JWT_SECRET",
    "REGENGINE_ENV",
    "AUTH_TEST_BYPASS_TOKEN",
    "REGENGINE_AUTH_STRICT",
    "REGENGINE_API_KEY",
    "API_KEY",
    "GITHUB_ACTIONS",
    "CI",
)


def _run_validate(env_overrides: dict) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in _STRIPPED_ENV}
    env.update(env_overrides)
    return subprocess.run(
        [sys.executable, "-c", VALIDATE_SCRIPT],
        capture_output=True,
        text=True,
        env=env,
    )


def test_falsy_ci_string_does_not_disable_strict_startup_gate() -> None:
    proc = _run_validate({"REGENGINE_ENV": "production", "CI": "false"})
    assert proc.returncode != 0
    assert "STARTED_OK" not in proc.stdout


def test_truthy_ci_string_keeps_existing_bypass_behavior() -> None:
    proc = _run_validate({"REGENGINE_ENV": "production", "CI": "true"})
    assert "STARTED_OK" in proc.stdout


def test_in_memory_store_accepts_naive_future_expiry_as_utc() -> None:
    from shared.auth import APIKeyStore

    store = APIKeyStore()
    naive_future = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)
    raw_key, _meta = store.create_key("qa5", expires_at=naive_future)
    assert store.validate_key(raw_key) is not None


def test_in_memory_store_rejects_naive_past_expiry() -> None:
    from shared.auth import APIKeyStore

    store = APIKeyStore()
    naive_past = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)
    raw_key, _meta = store.create_key("qa5", expires_at=naive_past)
    assert store.validate_key(raw_key) is None


def test_reconcile_tenant_scope_ignores_uuid_case() -> None:
    from shared.auth import reconcile_tenant_scope

    tenant = uuid4()

    class _Key:
        key_id = "k"
        tenant_id = str(tenant).upper()

    assert (
        reconcile_tenant_scope(_Key(), str(tenant).lower(), request_path="/x")
        == str(tenant).upper()
    )


def test_reconcile_tenant_scope_still_rejects_other_tenant() -> None:
    from shared.auth import reconcile_tenant_scope

    class _Key:
        key_id = "k"
        tenant_id = str(uuid4())

    with pytest.raises(HTTPException) as exc_info:
        reconcile_tenant_scope(_Key(), str(uuid4()), request_path="/x")
    assert exc_info.value.status_code == 409


def test_assert_tenant_claim_matches_ignores_uuid_case() -> None:
    from shared.tenant_context import TenantContext, assert_tenant_claim_matches

    tenant = uuid4()
    ctx = TenantContext(
        tenant_id=str(tenant).lower(),
        principal_kind="api_key",
        principal_id="k",
    )
    assert_tenant_claim_matches(ctx, str(tenant).upper(), source="query")


def test_get_tenant_id_rejects_non_string_with_400() -> None:
    from shared.auth import get_tenant_id

    with pytest.raises(HTTPException) as exc_info:
        get_tenant_id(123)
    assert exc_info.value.status_code == 400
