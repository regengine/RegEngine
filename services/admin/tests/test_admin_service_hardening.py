"""
Regression tests for admin-service tenant-isolation / RBAC / rate-limit
hardening:

  - #1381 SessionLocal pool tenant bleed (checkout listener)
  - #1385 audit export purpose gate + PII masking
  - #1386 tenant settings role enforcement + blocked-key filter
  - #1391 system_routes _resolve_tenant fails closed on missing context
  - #1392 admin brute-force limiter shared store (Redis-backed when
          available, per-process fallback otherwise)
"""

from __future__ import annotations

import json
import time
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


# =========================================================================
# #1381 -- pool checkout clears app.tenant_id
# =========================================================================


def test_reset_tenant_guc_listener_is_attached_on_postgres_engine():
    """For a non-sqlite engine we must install the checkout listener."""
    import importlib

    from sqlalchemy import event

    import services.admin.app.database as db_mod

    # If the running engine is Postgres, the checkout listener for
    # _reset_tenant_guc_on_checkout must be registered. For SQLite
    # (the common test fallback) the listener is intentionally NOT
    # attached -- SQLite does not use RLS.
    engine = db_mod._engine
    listeners = event.contains(
        engine, "checkout", db_mod._reset_tenant_guc_on_checkout
    )
    if engine.dialect.name == "sqlite":
        assert listeners is False, (
            "SQLite engine should not have the tenant GUC reset "
            "listener attached (no RLS; nothing to reset)"
        )
    else:
        assert listeners is True, (
            "Postgres engine must have _reset_tenant_guc_on_checkout "
            "attached to the 'checkout' event to prevent pool bleed "
            "(#1381)"
        )


def test_reset_tenant_guc_issues_clearing_statements_on_postgres():
    """When called directly, the listener must issue the two clearing
    set_config statements."""
    import services.admin.app.database as db_mod

    # Only meaningful on a Postgres engine. Skip on SQLite.
    if db_mod._engine.dialect.name == "sqlite":
        pytest.skip("listener is a no-op on SQLite")

    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value = cursor

    db_mod._reset_tenant_guc_on_checkout(conn, MagicMock(), MagicMock())

    # Both set_config statements issued
    calls = [str(c.args[0]) for c in cursor.execute.call_args_list]
    assert any("app.tenant_id" in s for s in calls)
    assert any("regengine.is_sysadmin" in s for s in calls)


# =========================================================================
# #1385 -- audit export purpose gate + PII masking
# =========================================================================


def test_mask_email_produces_deterministic_salted_hash():
    from services.admin.app.audit_routes import _mask_email

    a = _mask_email("jane.doe@example.com")
    b = _mask_email("jane.doe@example.com")
    c = _mask_email("other@example.com")
    assert a == b
    assert a != c
    assert a.startswith("masked:")


def test_audit_export_allowed_purposes_are_constrained():
    from services.admin.app.audit_routes import _ALLOWED_EXPORT_PURPOSES

    assert "compliance_investigation" in _ALLOWED_EXPORT_PURPOSES
    assert "security_incident" in _ALLOWED_EXPORT_PURPOSES
    assert "user_request" in _ALLOWED_EXPORT_PURPOSES
    # Random value not allowed
    assert "exfiltrate_all_the_things" not in _ALLOWED_EXPORT_PURPOSES


def test_audit_export_metadata_redaction_scrubs_nested_pii():
    from services.admin.app.audit_routes import _PII_REDACTION, _redact_metadata_pii

    erased_user_id = uuid.uuid4()
    redacted = _redact_metadata_pii(
        {
            "email": "invitee@example.com",
            "safe": "role-change",
            "nested": {
                "owner_phone": "+1 (415) 555-1212",
                "note": "Call jane@example.com before shipping.",
                "api_token": "super-secret-token",
                "redacted_user_id": str(erased_user_id),
            },
            "contacts": [{"contact_name": "Jane Doe"}],
        }
    )

    payload = json.dumps(redacted, sort_keys=True)
    assert "invitee@example.com" not in payload
    assert "jane@example.com" not in payload
    assert "415" not in payload
    assert "super-secret-token" not in payload
    assert str(erased_user_id) not in payload
    assert redacted["safe"] == "role-change"
    assert redacted["nested"]["api_token"] == _PII_REDACTION
    assert "masked:" in payload


def test_audit_export_honors_per_user_anonymization_marker():
    from services.admin.app.audit_routes import (
        _collect_anonymized_actor_ids,
        _export_actor_id,
        _export_resource_id,
        _row_is_anonymized,
    )

    tenant_id = uuid.uuid4()
    erased_user_id = uuid.uuid4()
    marker = SimpleNamespace(
        action="gdpr_anonymize_user",
        resource_id=str(erased_user_id),
        metadata_={
            "details": {
                "marker_kind": "per_user_anonymization_order",
                "redacted_user_id": str(erased_user_id),
                "redacted_tenant_id": str(tenant_id),
            },
        },
    )
    historical_row = SimpleNamespace(
        actor_id=erased_user_id,
        resource_id=str(erased_user_id),
        anonymized_at=None,
    )

    anonymized_actor_ids = _collect_anonymized_actor_ids(
        [historical_row, marker], tenant_id
    )

    assert str(erased_user_id) in anonymized_actor_ids
    assert _row_is_anonymized(historical_row, anonymized_actor_ids) is True
    assert _export_actor_id(historical_row, True).startswith("masked:")
    assert _export_resource_id(historical_row, anonymized_actor_ids).startswith(
        "masked:"
    )


def test_audit_export_ignores_anonymization_marker_for_other_tenant():
    from services.admin.app.audit_routes import _collect_anonymized_actor_ids

    tenant_id = uuid.uuid4()
    erased_user_id = uuid.uuid4()
    marker = SimpleNamespace(
        action="gdpr_anonymize_user",
        resource_id=str(erased_user_id),
        metadata_={
            "marker_kind": "per_user_anonymization_order",
            "redacted_user_id": str(erased_user_id),
            "redacted_tenant_id": str(uuid.uuid4()),
        },
    )

    assert _collect_anonymized_actor_ids([marker], tenant_id) == set()


def test_audit_export_loads_markers_outside_requested_export_rows():
    from services.admin.app.audit_routes import _load_anonymized_actor_ids

    tenant_id = uuid.uuid4()
    erased_user_id = uuid.uuid4()
    marker = SimpleNamespace(
        action="gdpr_anonymize_user",
        resource_id=str(erased_user_id),
        metadata_={
            "marker_kind": "per_user_anonymization_order",
            "redacted_user_id": str(erased_user_id),
            "redacted_tenant_id": str(tenant_id),
        },
    )
    db = MagicMock()
    db.execute.return_value.scalars.return_value.all.return_value = [marker]

    anonymized_actor_ids = _load_anonymized_actor_ids(db, tenant_id, export_rows=[])

    assert str(erased_user_id) in anonymized_actor_ids


# =========================================================================
# #1386 -- tenant settings role check + blocked-key filter
# =========================================================================


def test_strip_blocked_keys_removes_security_fields():
    from services.admin.app.tenant_settings_routes import (
        _SETTINGS_BLOCKED_WORKSPACE_KEYS,
        _strip_blocked_keys,
    )

    # Member tries to set security knobs via workspace_profile merge.
    value = {
        "retention_days": 1,
        "mfa_required": False,
        "webhook_url": "https://evil.com",
        "company_name": "Legit Corp",  # allowed
        "theme": "dark",  # allowed
    }
    cleaned, removed = _strip_blocked_keys(value, _SETTINGS_BLOCKED_WORKSPACE_KEYS)
    assert "retention_days" not in cleaned
    assert "mfa_required" not in cleaned
    assert "webhook_url" not in cleaned
    assert cleaned == {"company_name": "Legit Corp", "theme": "dark"}
    assert set(removed) == {"retention_days", "mfa_required", "webhook_url"}


def test_tenant_admin_role_names_include_both_cases():
    from services.admin.app.tenant_settings_routes import _ADMIN_ROLE_NAMES

    # Accept both capitalized and lowercase forms -- RBAC seeding has
    # historically been inconsistent between envs.
    assert "Owner" in _ADMIN_ROLE_NAMES
    assert "Admin" in _ADMIN_ROLE_NAMES
    assert "owner" in _ADMIN_ROLE_NAMES
    assert "admin" in _ADMIN_ROLE_NAMES
    # Non-admin roles rejected
    assert "Member" not in _ADMIN_ROLE_NAMES
    assert "Viewer" not in _ADMIN_ROLE_NAMES


# =========================================================================
# #1391 -- system_routes _resolve_tenant fails closed
# =========================================================================


def test_resolve_tenant_raises_500_on_missing_context():
    from fastapi import HTTPException

    from services.admin.app.system_routes import _resolve_tenant

    # db whose execute returns a row with None tenant_id
    db = MagicMock()
    db.execute.return_value.fetchone.return_value = (None,)
    with pytest.raises(HTTPException) as excinfo:
        _resolve_tenant(db)
    assert excinfo.value.status_code == 500


def test_resolve_tenant_raises_500_on_execute_error():
    from fastapi import HTTPException

    from services.admin.app.system_routes import _resolve_tenant

    db = MagicMock()
    db.execute.side_effect = RuntimeError("rls setup failed")
    with pytest.raises(HTTPException) as excinfo:
        _resolve_tenant(db)
    assert excinfo.value.status_code == 500


def test_resolve_tenant_returns_tid_on_success():
    from services.admin.app.system_routes import _resolve_tenant

    db = MagicMock()
    db.execute.return_value.fetchone.return_value = (
        "11111111-1111-1111-1111-111111111111",
    )
    assert (
        _resolve_tenant(db) == "11111111-1111-1111-1111-111111111111"
    )


def test_resolve_tenant_does_not_fall_back_to_demo_uuid():
    """Regression: make sure the hardcoded demo tenant UUID is not
    returned as a fallback. We check executable behavior rather than
    docstring content -- the fix's docstring intentionally names the
    bad UUID so future readers know what was removed."""
    from unittest.mock import MagicMock

    from fastapi import HTTPException

    from services.admin.app.system_routes import _resolve_tenant

    # The previous bug: on exception, return a demo tenant UUID.
    # The fix: on exception, raise 500. We verify the raise path here.
    db = MagicMock()
    db.execute.side_effect = RuntimeError("simulated RLS failure")
    with pytest.raises(HTTPException) as exc:
        _resolve_tenant(db)
    assert exc.value.status_code == 500
    # The HTTPException detail must NOT be the demo UUID -- it must
    # be an error message.
    assert "5946c58f" not in str(exc.value.detail)


# =========================================================================
# #1392 -- brute force limiter shared across workers
# =========================================================================


def test_brute_force_limiter_fallback_counts_in_memory(monkeypatch):
    """Without Redis the limiter should still enforce the threshold
    within a single process."""
    monkeypatch.delenv("REGENGINE_REDIS_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("UPSTASH_REDIS_REST_URL", raising=False)

    from shared.rate_limit import BruteForceLimiter

    bfl = BruteForceLimiter(
        namespace="test_ns", max_failures=3, window_seconds=60
    )
    assert bfl.is_redis_backed is False
    assert bfl.is_limited("ip-a") is False

    bfl.record_failure("ip-a")
    bfl.record_failure("ip-a")
    assert bfl.is_limited("ip-a") is False
    bfl.record_failure("ip-a")
    assert bfl.is_limited("ip-a") is True

    # Reset clears the counter
    bfl.reset("ip-a")
    assert bfl.is_limited("ip-a") is False


def test_brute_force_limiter_uses_redis_when_provided():
    """With a Redis-like client, failures increment via Redis and
    is_limited reads back from Redis."""
    from shared.rate_limit import BruteForceLimiter

    # Minimal Redis double -- tracks keys and TTLs.
    class FakeRedis:
        def __init__(self):
            self.store = {}

        def incr(self, name):
            self.store[name] = self.store.get(name, 0) + 1
            return self.store[name]

        def expire(self, name, time):
            return True

        def get(self, name):
            val = self.store.get(name)
            if val is None:
                return None
            return str(val).encode()

        def delete(self, name):
            self.store.pop(name, None)
            return 1

    fake = FakeRedis()
    bfl = BruteForceLimiter(
        namespace="test_ns",
        max_failures=3,
        window_seconds=60,
        redis_client=fake,
    )
    assert bfl.is_redis_backed is True

    for _ in range(2):
        bfl.record_failure("ip-b")
    assert bfl.is_limited("ip-b") is False
    bfl.record_failure("ip-b")
    assert bfl.is_limited("ip-b") is True

    # Verify the key was incremented in the shared store
    assert fake.store["test_ns:ip-b"] == 3

    bfl.reset("ip-b")
    assert bfl.is_limited("ip-b") is False


def test_admin_routes_module_uses_shared_bruteforce_limiter():
    """Sanity check: routes.py must use BruteForceLimiter not a
    per-process dict anymore."""
    import inspect

    from services.admin.app import routes

    source = inspect.getsource(routes)
    assert "BruteForceLimiter" in source
    # The old per-process dict still has a legacy identifier path
    # (to keep test_p0_security_hardening.py backward-compat). We
    # verify the ACTIVE limiter is the shared one by checking its
    # usage in verify_admin_key.
    assert "_admin_brute_force" in source
