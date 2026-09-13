"""Unit tests for ``shared.agent_org.suppression``.

No live DB: uses a stub session recording rendered SQL + params, the same
technique ``test_rules_rejection_audit.py`` uses for a text()-based helper
against SQLite-incompatible Postgres syntax (CAST(... AS uuid) here can't
run against SQLite either, so a full in-memory session is not an option).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from shared.agent_org.suppression import SUPPRESSION_REASONS, is_suppressed, record_suppression


class _FakeSession:
    """Records every ``execute()`` call; ``fetchone()`` returns a queued row."""

    def __init__(self, fetchone_result=None):
        self.calls: list[tuple[str, dict]] = []
        self._fetchone_result = fetchone_result

    def execute(self, stmt, params=None):
        sql = str(getattr(stmt, "text", stmt))
        self.calls.append((sql, dict(params or {})))
        result = MagicMock()
        result.fetchone.return_value = self._fetchone_result
        return result


class TestIsSuppressed:
    def test_returns_true_when_a_row_matches(self):
        session = _FakeSession(fetchone_result=(1,))
        assert is_suppressed(session, tenant_id="tenant-1", email_address="a@example.com") is True

    def test_returns_false_when_no_row_matches(self):
        session = _FakeSession(fetchone_result=None)
        assert is_suppressed(session, tenant_id="tenant-1", email_address="a@example.com") is False

    def test_empty_email_short_circuits_without_a_query(self):
        session = _FakeSession(fetchone_result=(1,))
        assert is_suppressed(session, tenant_id="tenant-1", email_address="") is False
        assert session.calls == []

    def test_none_email_short_circuits_without_a_query(self):
        session = _FakeSession(fetchone_result=(1,))
        assert is_suppressed(session, tenant_id="tenant-1", email_address=None) is False
        assert session.calls == []

    def test_email_is_normalized_before_the_query(self):
        session = _FakeSession(fetchone_result=None)
        is_suppressed(session, tenant_id="tenant-1", email_address="  A@Example.COM  ")
        _, params = session.calls[0]
        assert params["email_address"] == "a@example.com"

    def test_tenant_id_is_passed_as_an_explicit_predicate(self):
        session = _FakeSession(fetchone_result=None)
        is_suppressed(session, tenant_id="tenant-42", email_address="a@example.com")
        sql, params = session.calls[0]
        assert params["tenant_id"] == "tenant-42"
        assert "tenant_id" in sql


class TestRecordSuppression:
    @pytest.mark.parametrize("reason", sorted(SUPPRESSION_REASONS))
    def test_every_allowlisted_reason_is_accepted(self, reason):
        session = _FakeSession()
        record_suppression(session, tenant_id="tenant-1", email_address="a@example.com", reason=reason, source="test")
        assert len(session.calls) == 1

    def test_unknown_reason_raises_value_error_before_any_sql(self):
        session = _FakeSession()
        with pytest.raises(ValueError) as ei:
            record_suppression(
                session, tenant_id="tenant-1", email_address="a@example.com", reason="spam", source="test"
            )
        assert "spam" in str(ei.value)
        assert session.calls == []

    def test_empty_email_raises_value_error_before_any_sql(self):
        session = _FakeSession()
        with pytest.raises(ValueError):
            record_suppression(
                session, tenant_id="tenant-1", email_address="   ", reason="bounce", source="test"
            )
        assert session.calls == []

    def test_email_is_normalized_before_insert(self):
        session = _FakeSession()
        record_suppression(
            session, tenant_id="tenant-1", email_address="  A@Example.COM  ", reason="complaint", source="test"
        )
        _, params = session.calls[0]
        assert params["email_address"] == "a@example.com"

    def test_reason_and_source_are_passed_through_unmodified(self):
        session = _FakeSession()
        record_suppression(
            session, tenant_id="tenant-1", email_address="a@example.com", reason="manual_unsubscribe", source="ops-console"
        )
        _, params = session.calls[0]
        assert params["reason"] == "manual_unsubscribe"
        assert params["source"] == "ops-console"

    def test_no_uniqueness_check_is_performed_before_insert(self):
        # record_suppression never queries for an existing row first —
        # every call is a plain single-statement INSERT (multiple
        # suppression rows for the same address are allowed by design).
        session = _FakeSession()
        record_suppression(session, tenant_id="tenant-1", email_address="a@example.com", reason="bounce", source="s")
        assert len(session.calls) == 1
        assert "INSERT" in session.calls[0][0]
