"""Audit-trail coverage for billing/security-setting mutations.

Finding: ``update_partner_status`` (billing tier) and
``update_organization_sso_policy`` (SSO enforcement) mutated
security-sensitive state with only structlog lines (or nothing),
leaving no tamper-evident ``audit_logs`` row. Both routes must now
write via ``AuditLogger.log_event`` in the same transaction.

Pattern: direct async-function invocation with MagicMock sessions and
the REAL ``AuditLogger`` (see ``test_tenant_settings_routes.py`` for
the #1435 context). The mock db answers the audit chain-head read
with ``None`` (first entry for that scope) so the real logger
proceeds to ``db.add``; the tests then assert exactly one audit row
was staged with the expected event type, actor, resource and
previous/new values. On the pre-fix code neither route called
``db.add`` at all, so these tests fail there.
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

# sys.path bootstrap (same as other admin tests — see #1435).
_SERVICE_DIR = Path(__file__).resolve().parent.parent
_SERVICES_DIR = _SERVICE_DIR.parent
for _p in (_SERVICE_DIR, _SERVICES_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


TENANT_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
USER_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
ORG_ID = uuid.UUID("55555555-5555-4555-8555-555555555555")
ADMIN_ID = uuid.UUID("33333333-3333-4333-8333-333333333333")


def _audit_capable_db(get_result=None):
    """MagicMock session on which the real AuditLogger can stage a row.

    The chain-head lookup returns no rows (fresh scope), so the logger
    computes a genesis-chained entry and calls ``db.add`` exactly once
    per ``log_event`` call.
    """
    db = MagicMock()
    db.get.return_value = get_result
    db.execute.return_value.one_or_none.return_value = None
    return db


def _added_entries(db):
    return [call.args[0] for call in db.add.call_args_list]


class TestPartnerStatusAuditTrail:
    def test_sets_founding_tier_writes_audit_entry(self, monkeypatch) -> None:
        from services.admin.app import tenant_settings_routes as mod

        monkeypatch.setattr(mod, "flag_modified", lambda *a, **kw: None)
        tenant = SimpleNamespace(id=TENANT_ID, settings={"unrelated": "value"})
        db = _audit_capable_db(get_result=tenant)

        response = asyncio.run(
            mod.update_partner_status(
                tenant_id=TENANT_ID,
                payload=mod.PartnerStatusUpdate(tier="founding"),
                user=SimpleNamespace(id=USER_ID, is_sysadmin=True),
                db=db,
            )
        )

        assert response["status"] == "ok"
        entries = _added_entries(db)
        assert len(entries) == 1, (
            "partner-tier change staged no audit row: billing changes must go through AuditLogger, not structlog alone"
        )
        entry = entries[0]
        assert entry.tenant_id == TENANT_ID
        assert entry.event_type == "tenant.partner_tier_change"
        assert entry.action == "tenant.partner_tier_change"
        assert entry.actor_id == USER_ID
        assert entry.resource_type == "tenant"
        assert entry.resource_id == str(TENANT_ID)
        assert entry.metadata_ == {"previous_tier": None, "new_tier": "founding"}

    def test_clear_tier_records_previous_value(self, monkeypatch) -> None:
        from services.admin.app import tenant_settings_routes as mod

        monkeypatch.setattr(mod, "flag_modified", lambda *a, **kw: None)
        tenant = SimpleNamespace(id=TENANT_ID, settings={"partner_tier": "founding"})
        db = _audit_capable_db(get_result=tenant)

        response = asyncio.run(
            mod.update_partner_status(
                tenant_id=TENANT_ID,
                payload=mod.PartnerStatusUpdate(tier=None),
                user=SimpleNamespace(id=USER_ID, is_sysadmin=True),
                db=db,
            )
        )

        assert response["partner_tier"] is None
        entries = _added_entries(db)
        assert len(entries) == 1
        assert entries[0].metadata_ == {"previous_tier": "founding", "new_tier": None}


class TestOrganizationSsoPolicyAuditTrail:
    def test_sso_policy_change_writes_audit_entry(self) -> None:
        from services.admin.app.admin import organizations_router as mod
        from services.admin.app.sqlalchemy_models import OrganizationModel

        organization = OrganizationModel(
            id=ORG_ID,
            name="Enterprise Foods",
            domain_name=None,
            domain_verified=False,
            enforced_auth_policy="standard",
        )
        db = _audit_capable_db(get_result=organization)

        response = asyncio.run(
            mod.update_organization_sso_policy(
                ORG_ID,
                mod.OrganizationSsoPolicyUpdate(
                    domain_name="secure.example",
                    domain_verified=True,
                    enforced_auth_policy="sso_only",
                ),
                SimpleNamespace(id=ADMIN_ID, is_sysadmin=True),
                db,
            )
        )

        assert response.enforced_auth_policy == "sso_only"
        entries = _added_entries(db)
        assert len(entries) == 1, (
            "SSO-policy change staged no audit row: security-setting changes must go through AuditLogger"
        )
        entry = entries[0]
        assert entry.event_type == "organization.sso_policy_change"
        assert entry.action == "organization.sso_policy_change"
        assert entry.actor_id == ADMIN_ID
        assert entry.resource_type == "organization"
        assert entry.resource_id == str(ORG_ID)
        assert entry.metadata_["previous_policy"] == {
            "domain_name": None,
            "domain_verified": False,
            "enforced_auth_policy": "standard",
        }
        assert entry.metadata_["new_policy"] == {
            "domain_name": "secure.example",
            "domain_verified": True,
            "enforced_auth_policy": "sso_only",
        }
        db.commit.assert_called_once()
