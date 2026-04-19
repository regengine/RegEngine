"""Regression tests for admin tenant_settings_routes (#1341).

Before this suite, ``services/admin/app/tenant_settings_routes.py``
(326 LOC, 3 endpoints) had no dedicated test file. The module carries
two high-impact security invariants:

1. **#1386 role gate**: Only Owner / Admin / Sysadmin may mutate
   ``tenant.settings``. Before the fix, any Member or Viewer with a
   membership row could overwrite billing/retention/mfa/sso/webhook
   keys via the generic PATCH endpoint. The helper
   ``_require_tenant_admin`` is the guard; a regression that swaps it
   back to ``_get_tenant_for_user`` would silently reopen the hole.

2. **Settings key allowlist**: Even privileged roles must NOT be able
   to overwrite security/billing knobs (``retention_days``,
   ``mfa_required``, ``sso_config``, ``webhook_url(s)``,
   ``custom_domain``, ``partner_tier``, ``billing_tier``,
   ``billing_email``) through the generic merge endpoint. Those keys
   have dedicated endpoints with additional controls. The merge
   endpoint strips them from the payload and logs a warning.

The ``update_partner_status`` endpoint is sysadmin-gated (a tenant's
own Owner cannot upgrade themselves to "founding partner" tier — the
tier is set by Anthropic staff only).

Pattern: direct async-function invocation with MagicMock sessions
(see ``test_compliance_routes_idor.py`` and the module docstring of
``test_user_routes.py`` for context on #1435).
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

# sys.path bootstrap (same as other admin tests — see #1435).
_SERVICE_DIR = Path(__file__).resolve().parent.parent
_SERVICES_DIR = _SERVICE_DIR.parent
for _p in (_SERVICE_DIR, _SERVICES_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


TENANT_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
USER_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
OTHER_USER_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
OWNER_ROLE_ID = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
MEMBER_ROLE_ID = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000002")
ADMIN_ROLE_ID = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000003")
VIEWER_ROLE_ID = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000004")


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------


def _fake_user(user_id=USER_ID, is_sysadmin=False):
    return SimpleNamespace(id=user_id, is_sysadmin=is_sysadmin)


def _fake_tenant(settings=None):
    return SimpleNamespace(id=TENANT_ID, settings=settings if settings is not None else {})


def _fake_membership(user_id=USER_ID, role_id=OWNER_ROLE_ID, is_active=True):
    return SimpleNamespace(
        user_id=user_id, tenant_id=TENANT_ID,
        role_id=role_id, is_active=is_active,
    )


def _install_db(tenant, membership=None, role_name=None):
    """Build a MagicMock db that responds to the route's read pattern.

    The admin routes run two queries in order:
    1. select(MembershipModel).where(...) → scalar_one_or_none()
    2. db.get(TenantModel, tenant_id) → tenant
    3. db.get(RoleModel, membership.role_id) → role with name=role_name
    """
    db = MagicMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = membership
    db.execute.return_value = execute_result

    def _get(model_cls, ident):
        model_name = getattr(model_cls, "__name__", str(model_cls))
        if "Tenant" in model_name:
            return tenant
        if "Role" in model_name:
            if role_name is None:
                return None
            return SimpleNamespace(id=ident, name=role_name)
        return None

    db.get.side_effect = _get
    return db


def _load_routes(monkeypatch):
    """Import the settings route module with SQLAlchemy's ``flag_modified``
    neutralized so SimpleNamespace stand-ins can be used as ``tenant``.

    The real ``flag_modified`` demands an ``_sa_instance_state`` attribute
    (present only on actual SQLAlchemy-mapped instances). All these tests
    care about is that the route copies values onto ``tenant.settings``
    and calls ``db.commit``; whether the JSON column is flagged dirty is
    SQLAlchemy's concern, not this suite's.
    """
    from services.admin.app import tenant_settings_routes as mod

    monkeypatch.setattr(mod, "flag_modified", lambda *a, **kw: None)
    return mod


# ---------------------------------------------------------------------------
# _require_tenant_admin (#1386)
# ---------------------------------------------------------------------------


class TestRoleGate_Issue1386:
    def test_member_cannot_update_settings(self, monkeypatch) -> None:
        """#1386: a regular Member with a valid membership row must NOT
        be able to PATCH tenant settings. Before the fix, any member
        could rewrite billing/mfa/sso keys through this endpoint."""
        mod = _load_routes(monkeypatch)
        tenant = _fake_tenant()
        membership = _fake_membership(role_id=MEMBER_ROLE_ID)
        db = _install_db(tenant, membership=membership, role_name="Member")

        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                mod.update_tenant_settings(
                    tenant_id=TENANT_ID,
                    payload=mod.SettingsUpdate(workspace_profile={"company": "Acme"}),
                    user=_fake_user(),
                    db=db,
                )
            )
        assert exc.value.status_code == 403
        assert "Owner or Admin" in exc.value.detail or "admin" in exc.value.detail.lower()

    def test_viewer_cannot_update_settings(self, monkeypatch) -> None:
        """Viewer role is even more restricted than Member — also 403."""
        mod = _load_routes(monkeypatch)
        tenant = _fake_tenant()
        membership = _fake_membership(role_id=VIEWER_ROLE_ID)
        db = _install_db(tenant, membership=membership, role_name="Viewer")

        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                mod.update_tenant_settings(
                    tenant_id=TENANT_ID,
                    payload=mod.SettingsUpdate(workspace_profile={"x": 1}),
                    user=_fake_user(),
                    db=db,
                )
            )
        assert exc.value.status_code == 403

    def test_non_member_blocked(self, monkeypatch) -> None:
        """Caller with no membership row at all gets 403 'not a member'."""
        mod = _load_routes(monkeypatch)
        tenant = _fake_tenant()
        db = _install_db(tenant, membership=None)

        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                mod.update_tenant_settings(
                    tenant_id=TENANT_ID,
                    payload=mod.SettingsUpdate(workspace_profile={"x": 1}),
                    user=_fake_user(),
                    db=db,
                )
            )
        assert exc.value.status_code == 403
        assert "member" in exc.value.detail.lower()

    def test_owner_can_update_settings(self, monkeypatch) -> None:
        mod = _load_routes(monkeypatch)
        tenant = _fake_tenant()
        membership = _fake_membership(role_id=OWNER_ROLE_ID)
        db = _install_db(tenant, membership=membership, role_name="Owner")

        response = asyncio.run(
            mod.update_tenant_settings(
                tenant_id=TENANT_ID,
                payload=mod.SettingsUpdate(
                    workspace_profile={"company_name": "Acme Farms"}
                ),
                user=_fake_user(),
                db=db,
            )
        )
        assert response["status"] == "ok"
        assert response["settings"]["workspace_profile"]["company_name"] == "Acme Farms"
        db.commit.assert_called_once()

    def test_admin_can_update_settings(self, monkeypatch) -> None:
        mod = _load_routes(monkeypatch)
        tenant = _fake_tenant()
        membership = _fake_membership(role_id=ADMIN_ROLE_ID)
        db = _install_db(tenant, membership=membership, role_name="Admin")

        response = asyncio.run(
            mod.update_tenant_settings(
                tenant_id=TENANT_ID,
                payload=mod.SettingsUpdate(onboarding={"facility_created": True}),
                user=_fake_user(),
                db=db,
            )
        )
        assert response["status"] == "ok"
        assert response["settings"]["onboarding"]["facility_created"] is True

    def test_sysadmin_bypasses_role_check(self, monkeypatch) -> None:
        """Sysadmin should be allowed even without a matching membership
        row — they manage all tenants."""
        mod = _load_routes(monkeypatch)
        tenant = _fake_tenant()
        # No membership — sysadmin branch returns "Sysadmin" directly.
        db = _install_db(tenant, membership=None)

        response = asyncio.run(
            mod.update_tenant_settings(
                tenant_id=TENANT_ID,
                payload=mod.SettingsUpdate(workspace_profile={"x": 1}),
                user=_fake_user(is_sysadmin=True),
                db=db,
            )
        )
        assert response["status"] == "ok"


# ---------------------------------------------------------------------------
# Blocked-key stripping
# ---------------------------------------------------------------------------


class TestBlockedKeyStripping_Issue1386:
    """Even privileged callers MUST NOT be able to overwrite billing /
    security keys through this endpoint. These tests lock the
    allowlist in."""

    @pytest.mark.parametrize(
        "blocked_key, malicious_value",
        [
            ("retention_days", 1),  # shorten retention to evade audit
            ("mfa_required", False),  # disable MFA
            ("sso_config", {"idp": "attacker.example"}),
            ("webhook_url", "https://attacker.example/exfil"),
            ("webhook_urls", ["https://attacker.example"]),
            ("custom_domain", "attacker.example"),
            ("partner_tier", "founding"),  # privilege escalation
            ("billing_tier", "enterprise"),  # free tier bypass
            ("billing_email", "attacker@evil.example"),
        ],
    )
    def test_blocked_key_is_stripped_from_workspace_profile(
        self, monkeypatch, blocked_key, malicious_value,
    ) -> None:
        mod = _load_routes(monkeypatch)
        tenant = _fake_tenant(settings={})
        membership = _fake_membership(role_id=OWNER_ROLE_ID)
        db = _install_db(tenant, membership=membership, role_name="Owner")

        response = asyncio.run(
            mod.update_tenant_settings(
                tenant_id=TENANT_ID,
                payload=mod.SettingsUpdate(
                    workspace_profile={
                        "company_name": "Acme",  # legitimate key
                        blocked_key: malicious_value,
                    }
                ),
                user=_fake_user(),
                db=db,
            )
        )

        # The legit key survives.
        assert response["settings"]["workspace_profile"]["company_name"] == "Acme"
        # The blocked key MUST NOT be in settings.
        assert blocked_key not in response["settings"]["workspace_profile"], (
            f"Blocked key '{blocked_key}' leaked into settings — this is "
            f"a #1386 regression; the merge endpoint must strip all keys "
            f"in _SETTINGS_BLOCKED_WORKSPACE_KEYS"
        )
        # And it must not be at the top level either.
        assert blocked_key not in response["settings"]

    def test_blocked_key_in_onboarding_also_stripped(self, monkeypatch) -> None:
        """Blocked-key stripping runs against ``onboarding`` too, not
        just ``workspace_profile``. A caller who figured out the
        allowlist might try to smuggle security keys in via
        onboarding."""
        mod = _load_routes(monkeypatch)
        tenant = _fake_tenant()
        membership = _fake_membership(role_id=OWNER_ROLE_ID)
        db = _install_db(tenant, membership=membership, role_name="Owner")

        response = asyncio.run(
            mod.update_tenant_settings(
                tenant_id=TENANT_ID,
                payload=mod.SettingsUpdate(
                    onboarding={
                        "workspace_setup_completed": True,
                        "retention_days": 1,  # must be stripped
                        "mfa_required": False,  # must be stripped
                    }
                ),
                user=_fake_user(),
                db=db,
            )
        )
        assert response["settings"]["onboarding"]["workspace_setup_completed"] is True
        assert "retention_days" not in response["settings"]["onboarding"]
        assert "mfa_required" not in response["settings"]["onboarding"]

    def test_merge_preserves_existing_settings(self, monkeypatch) -> None:
        """PATCH semantics: values not mentioned in the payload must
        survive the merge. A regression to PUT-semantics would blow
        away operator-set fields every time a UI form submitted."""
        mod = _load_routes(monkeypatch)
        tenant = _fake_tenant(
            settings={
                "workspace_profile": {
                    "company_name": "Existing Co",
                    "industry": "produce",
                },
                "onboarding": {"workspace_setup_completed": True},
                # Security keys set out-of-band by another endpoint.
                "retention_days": 2555,
                "mfa_required": True,
            }
        )
        membership = _fake_membership(role_id=OWNER_ROLE_ID)
        db = _install_db(tenant, membership=membership, role_name="Owner")

        asyncio.run(
            mod.update_tenant_settings(
                tenant_id=TENANT_ID,
                payload=mod.SettingsUpdate(
                    workspace_profile={"industry": "dairy"},
                ),
                user=_fake_user(),
                db=db,
            )
        )
        # Merged: industry updated, company_name preserved.
        assert tenant.settings["workspace_profile"]["company_name"] == "Existing Co"
        assert tenant.settings["workspace_profile"]["industry"] == "dairy"
        # Top-level security keys untouched by the merge.
        assert tenant.settings["retention_days"] == 2555
        assert tenant.settings["mfa_required"] is True
        # Onboarding key untouched since it wasn't in the payload.
        assert tenant.settings["onboarding"]["workspace_setup_completed"] is True


# ---------------------------------------------------------------------------
# get_onboarding_status
# ---------------------------------------------------------------------------


class TestOnboardingStatus_Issue1341:
    def test_non_member_gets_403(self, monkeypatch) -> None:
        mod = _load_routes(monkeypatch)
        tenant = _fake_tenant()
        db = _install_db(tenant, membership=None)

        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                mod.get_onboarding_status(
                    tenant_id=TENANT_ID,
                    user=_fake_user(),
                    db=db,
                )
            )
        assert exc.value.status_code == 403

    def test_is_complete_true_when_all_three_flags_set(
        self, monkeypatch,
    ) -> None:
        """``is_complete`` requires ALL THREE of workspace_setup_completed,
        facility_created, ftl_check_completed. A regression that uses
        ``any`` instead of ``all`` would mark incomplete tenants done."""
        mod = _load_routes(monkeypatch)
        tenant = _fake_tenant(
            settings={
                "workspace_profile": {"company_name": "Acme"},
                "onboarding": {
                    "workspace_setup_completed": True,
                    "facility_created": True,
                    "ftl_check_completed": True,
                },
            }
        )
        membership = _fake_membership(role_id=MEMBER_ROLE_ID)
        db = _install_db(tenant, membership=membership)

        response = asyncio.run(
            mod.get_onboarding_status(
                tenant_id=TENANT_ID, user=_fake_user(), db=db,
            )
        )
        assert response.is_complete is True

    def test_is_complete_false_when_any_flag_missing(self, monkeypatch) -> None:
        mod = _load_routes(monkeypatch)
        tenant = _fake_tenant(
            settings={
                "onboarding": {
                    "workspace_setup_completed": True,
                    "facility_created": True,
                    # ftl_check_completed missing.
                },
            }
        )
        membership = _fake_membership(role_id=MEMBER_ROLE_ID)
        db = _install_db(tenant, membership=membership)

        response = asyncio.run(
            mod.get_onboarding_status(
                tenant_id=TENANT_ID, user=_fake_user(), db=db,
            )
        )
        assert response.is_complete is False

    def test_returns_partner_tier_from_settings(self, monkeypatch) -> None:
        mod = _load_routes(monkeypatch)
        tenant = _fake_tenant(
            settings={
                "workspace_profile": {},
                "onboarding": {},
                "partner_tier": "founding",
            }
        )
        membership = _fake_membership(role_id=MEMBER_ROLE_ID)
        db = _install_db(tenant, membership=membership)

        response = asyncio.run(
            mod.get_onboarding_status(
                tenant_id=TENANT_ID, user=_fake_user(), db=db,
            )
        )
        assert response.partner_tier == "founding"


# ---------------------------------------------------------------------------
# update_partner_status
# ---------------------------------------------------------------------------


class TestUpdatePartnerStatus_Issue1341:
    def test_non_sysadmin_owner_is_blocked(self, monkeypatch) -> None:
        """Partner tier assignment is a privilege Anthropic staff
        controls — even a tenant's Owner must not be able to upgrade
        themselves to "founding partner" via this endpoint."""
        mod = _load_routes(monkeypatch)
        db = MagicMock()
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                mod.update_partner_status(
                    tenant_id=TENANT_ID,
                    payload=mod.PartnerStatusUpdate(tier="founding"),
                    user=_fake_user(is_sysadmin=False),
                    db=db,
                )
            )
        assert exc.value.status_code == 403
        assert "sysadmin" in exc.value.detail.lower()

    def test_invalid_tier_rejected(self, monkeypatch) -> None:
        mod = _load_routes(monkeypatch)
        db = MagicMock()
        db.get.return_value = _fake_tenant()
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                mod.update_partner_status(
                    tenant_id=TENANT_ID,
                    payload=mod.PartnerStatusUpdate(tier="enterprise_gold"),
                    user=_fake_user(is_sysadmin=True),
                    db=db,
                )
            )
        assert exc.value.status_code == 400
        assert "Invalid tier" in exc.value.detail

    def test_sysadmin_can_set_founding_tier(self, monkeypatch) -> None:
        mod = _load_routes(monkeypatch)
        tenant = _fake_tenant(settings={"unrelated": "value"})
        db = MagicMock()
        db.get.return_value = tenant

        response = asyncio.run(
            mod.update_partner_status(
                tenant_id=TENANT_ID,
                payload=mod.PartnerStatusUpdate(tier="founding"),
                user=_fake_user(is_sysadmin=True),
                db=db,
            )
        )
        assert response["status"] == "ok"
        assert response["partner_tier"] == "founding"
        assert tenant.settings["partner_tier"] == "founding"
        # Unrelated settings survive.
        assert tenant.settings["unrelated"] == "value"

    def test_sysadmin_can_clear_tier_with_none(self, monkeypatch) -> None:
        """Passing ``tier=None`` clears the partner_tier key
        entirely (doesn't just set it to None)."""
        mod = _load_routes(monkeypatch)
        tenant = _fake_tenant(settings={"partner_tier": "founding"})
        db = MagicMock()
        db.get.return_value = tenant

        response = asyncio.run(
            mod.update_partner_status(
                tenant_id=TENANT_ID,
                payload=mod.PartnerStatusUpdate(tier=None),
                user=_fake_user(is_sysadmin=True),
                db=db,
            )
        )
        assert response["partner_tier"] is None
        assert "partner_tier" not in tenant.settings, (
            "Clearing tier should REMOVE the key, not leave it as None "
            "— otherwise a downstream check of 'if settings.get(...)' "
            "would still observe a truthy value depending on the check"
        )

    def test_404_when_tenant_not_found(self, monkeypatch) -> None:
        mod = _load_routes(monkeypatch)
        db = MagicMock()
        db.get.return_value = None
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                mod.update_partner_status(
                    tenant_id=uuid.uuid4(),
                    payload=mod.PartnerStatusUpdate(tier="standard"),
                    user=_fake_user(is_sysadmin=True),
                    db=db,
                )
            )
        assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# Unit: _strip_blocked_keys
# ---------------------------------------------------------------------------


class TestStripBlockedKeysUnit_Issue1341:
    def test_keeps_allowed_keys_drops_blocked(self, monkeypatch) -> None:
        mod = _load_routes(monkeypatch)
        cleaned, removed = mod._strip_blocked_keys(
            {"a": 1, "retention_days": 2, "b": 3},
            {"retention_days"},
        )
        assert cleaned == {"a": 1, "b": 3}
        assert removed == ["retention_days"]

    def test_empty_input_is_safe(self, monkeypatch) -> None:
        mod = _load_routes(monkeypatch)
        cleaned, removed = mod._strip_blocked_keys({}, {"retention_days"})
        assert cleaned == {}
        assert removed == []

    def test_none_input_is_safe(self, monkeypatch) -> None:
        """Defensive: caller may pass None when ``workspace_profile`` is
        absent. The helper must not crash with TypeError."""
        mod = _load_routes(monkeypatch)
        cleaned, removed = mod._strip_blocked_keys(None, {"retention_days"})
        assert cleaned == {}
        assert removed == []
