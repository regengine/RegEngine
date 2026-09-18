"""Unit tests for ``app.email_ingest.tenant_lookup``.

The lookup goes through a SECURITY DEFINER Postgres function, so unit
coverage here mocks the SQLAlchemy session (matching the ``test_stripe_plans``
monkeypatch style) rather than requiring a live database; the RLS/bootstrap
and sender-allowlist behavior itself belongs to the migration's own
integration coverage.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

from services.ingestion.app.email_ingest.tenant_lookup import lookup_tenant_by_inbound_address


def _session_returning(row):
    session = MagicMock()
    session.execute.return_value.fetchone.return_value = row
    return session


class TestLookupTenantByInboundAddress:
    def test_returns_tenant_id_as_string_when_mapped(self):
        tenant_id = uuid.uuid4()
        session = _session_returning(SimpleNamespace(tenant_id=tenant_id))

        result = lookup_tenant_by_inbound_address(session, "Recipient@Tenant.RegEngine.co", "Sender@Example.com")

        assert result == str(tenant_id)
        session.commit.assert_called_once()

    def test_lowercases_and_strips_the_address_and_sender_before_lookup(self):
        session = _session_returning(SimpleNamespace(tenant_id=uuid.uuid4()))

        lookup_tenant_by_inbound_address(session, "  Some.Address@Example.COM  ", "  Sender@Example.COM  ")

        _, params = session.execute.call_args[0]
        assert params == {"addr": "some.address@example.com", "sender": "sender@example.com"}

    def test_missing_sender_is_normalized_to_empty_string(self):
        # A defensively-empty/None sender must never crash the lookup -- it
        # is passed through to the allowlist check, which will simply fail
        # to match anything (fail closed).
        session = _session_returning(None)
        lookup_tenant_by_inbound_address(session, "nobody@example.com", "")
        _, params = session.execute.call_args[0]
        assert params["sender"] == ""

    def test_returns_none_when_no_row(self):
        session = _session_returning(None)
        assert lookup_tenant_by_inbound_address(session, "nobody@example.com", "someone@example.com") is None
        session.commit.assert_called_once()

    def test_returns_none_when_row_has_null_tenant_id(self):
        # fsma.get_tenant_by_inbound_address returns a single (possibly
        # NULL) UUID column rather than no row at all for an unmapped or
        # inactive address, or a sender not on that tenant's allowlist.
        session = _session_returning(SimpleNamespace(tenant_id=None))
        assert lookup_tenant_by_inbound_address(session, "nobody@example.com", "someone@example.com") is None

    def test_commits_even_on_unmapped_lookup(self):
        # The transaction-local GUCs the bootstrap function sets
        # (app.inbound_lookup_address, app.tenant_id) must be released
        # regardless of whether the lookup found a tenant.
        session = _session_returning(None)
        lookup_tenant_by_inbound_address(session, "nobody@example.com", "someone@example.com")
        session.commit.assert_called_once()
