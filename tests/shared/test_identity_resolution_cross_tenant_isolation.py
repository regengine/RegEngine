"""Cross-tenant isolation tests for identity_resolution (issue #1235).

#1235 calls out three test gaps. This file covers gap #1:

    "find_entity_by_alias(tenant_A, ...) must never return tenant_B
     rows (negative cross-tenant test)."

We exercise the contract mock-first -- SQLAlchemy with a MagicMock
session -- so the tests lock in the SQL shape ("WHERE ea.tenant_id =
:tenant_id") and the parameter passing rather than requiring a running
Postgres. A future integration test can layer on top.

Regression modes caught here:

    * find_entity_by_alias drops the tenant_id filter or uses a
      different parameter name.
    * auto_register_from_event forgets to verify the caller-supplied
      tenant_id against _principal_tenant_id (#1230 tenant lock).
    * register_entity accepts an off-principal tenant_id without a
      platform-admin grant.

Mock-based -- no DB required. DB-level integration still needs to be
wired in when a postgres fixture is available.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from services.shared.identity_resolution import IdentityResolutionService

TENANT_A = "tenant-aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
TENANT_B = "tenant-bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session():
    session = MagicMock()
    session.execute.return_value.fetchall.return_value = []
    session.execute.return_value.fetchone.return_value = (1,)
    return session


@pytest.fixture
def svc(mock_session):
    return IdentityResolutionService(mock_session)


# ---------------------------------------------------------------------------
# find_entity_by_alias must pass the caller-supplied tenant_id through
# ---------------------------------------------------------------------------


class TestFindByAliasTenantScope_Issue1235:
    def test_tenant_id_is_passed_as_query_param(self, svc, mock_session):
        """The SQL the service emits must filter on ea.tenant_id. The
        MagicMock captures the params dict; we assert our tenant_id
        flowed through verbatim."""
        svc.find_entity_by_alias(TENANT_A, "gln", "0614141000012")

        # find_entity_by_alias issues exactly one SELECT.
        assert mock_session.execute.called
        sql, params = mock_session.execute.call_args_list[0].args
        sql_text = str(sql)

        # Lock in the tenant-scoped WHERE clause -- if this regresses to
        # e.g. "WHERE ea.alias_type" with no tenant filter, a cross-tenant
        # read becomes possible.
        assert "tenant_id = :tenant_id" in sql_text.replace("\n", " "), (
            "find_entity_by_alias SQL must filter on ea.tenant_id = :tenant_id"
        )
        assert params["tenant_id"] == TENANT_A, (
            f"Expected tenant_id={TENANT_A!r} but got {params.get('tenant_id')!r}"
        )

    def test_different_tenants_get_different_rowsets(self, mock_session):
        """Simulates Postgres-level isolation: the mock returns different
        rows depending on which tenant_id is in the params. Asserts the
        service forwards the tenant into the query so this isolation
        pattern works."""
        svc = IdentityResolutionService(mock_session)

        def _fetchall_by_tenant(sql, params):
            """Mimic row-level security: only return rows for TENANT_A."""
            result = MagicMock()
            if params.get("tenant_id") == TENANT_A:
                result.fetchall.return_value = [(
                    "entity-A", "facility", "Acme A", None, None, None, None,
                    "unverified", 1.0, True,
                    "alias-1", "gln", "0614141000012", "sys", 1.0,
                )]
            else:
                result.fetchall.return_value = []
            result.fetchone.return_value = (1,)
            return result

        mock_session.execute.side_effect = _fetchall_by_tenant

        rows_a = svc.find_entity_by_alias(TENANT_A, "gln", "0614141000012")
        rows_b = svc.find_entity_by_alias(TENANT_B, "gln", "0614141000012")

        assert len(rows_a) == 1
        assert rows_a[0]["entity_id"] == "entity-A"
        # Tenant B -- with identical alias -- must see an empty result
        # because the query scoped on tenant_id.
        assert rows_b == []

    def test_find_by_alias_does_not_query_all_tenants(self, svc, mock_session):
        """Guard against a refactor that swaps to a bare `WHERE alias_type=...`
        query -- that would return every tenant's data. Verify no all-tenants
        shape in the SQL (no OR, no IS NULL fallback on tenant_id)."""
        svc.find_entity_by_alias(TENANT_A, "tlc", "00012345678901-LOT-A")
        sql_text = str(mock_session.execute.call_args_list[0].args[0])

        # Defensive substring checks -- these are what a cross-tenant
        # regression would look like.
        assert "tenant_id IS NULL" not in sql_text
        assert "OR ea.tenant_id" not in sql_text


# ---------------------------------------------------------------------------
# register_entity / auto_register must honor the #1230 tenant lock
# ---------------------------------------------------------------------------


class TestRegisterEntityTenantLock_Issue1235:
    def test_register_entity_rejects_off_principal_tenant(self, mock_session):
        """With principal_tenant_id = TENANT_A, a register_entity call
        for TENANT_B must raise PermissionError before any INSERT runs."""
        svc = IdentityResolutionService(
            mock_session, principal_tenant_id=TENANT_A,
        )
        with pytest.raises(PermissionError):
            svc.register_entity(TENANT_B, "facility", "Bogus Co")
        # The execute must not have run -- the guard raises before any
        # side effect.
        assert not mock_session.execute.called

    def test_register_entity_allows_matched_principal(self, mock_session):
        """Principal TENANT_A registering under TENANT_A -- writes proceed."""
        svc = IdentityResolutionService(
            mock_session, principal_tenant_id=TENANT_A,
        )
        result = svc.register_entity(TENANT_A, "facility", "Good Co")
        assert result["tenant_id"] == TENANT_A
        assert mock_session.execute.called

    def test_auto_register_rejects_off_principal_tenant(self, mock_session):
        """auto_register_from_event is the hot ingest path -- it MUST
        verify tenant before touching any facility / product / firm /
        lot reference in the event."""
        svc = IdentityResolutionService(
            mock_session, principal_tenant_id=TENANT_A,
        )
        event = {"from_facility_reference": "0614141000012"}

        with pytest.raises(PermissionError):
            svc.auto_register_from_event(TENANT_B, event)
        # No side effect: the mock session's execute was never called
        # because the guard fired first.
        assert not mock_session.execute.called


# ---------------------------------------------------------------------------
# The cross-tenant admin escape hatch is opt-in only
# ---------------------------------------------------------------------------


class TestCrossTenantEscapeHatchIsOptIn_Issue1235:
    def test_default_service_is_tenant_locked(self, mock_session):
        """A service constructed with a principal_tenant_id and no
        explicit allow_cross_tenant opt-in must refuse any mismatched
        tenant_id."""
        svc = IdentityResolutionService(
            mock_session, principal_tenant_id=TENANT_A,
        )
        with pytest.raises(PermissionError):
            svc.register_entity(TENANT_B, "facility", "Cross-tenant Co")

    def test_explicit_allow_cross_tenant_bypasses_lock(self, mock_session):
        """Only with ``allow_cross_tenant=True`` -- the platform-admin
        grant -- may the caller write under a tenant that differs from
        the principal. This locks in the #1230 opt-in semantics."""
        svc = IdentityResolutionService(
            mock_session,
            principal_tenant_id=TENANT_A,
            allow_cross_tenant=True,
        )
        # Must NOT raise -- the opt-in disables the guard.
        result = svc.register_entity(TENANT_B, "facility", "Platform-admin Co")
        assert result["tenant_id"] == TENANT_B
