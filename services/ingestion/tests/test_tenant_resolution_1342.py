"""
Regression coverage for ``app/shared/tenant_resolution.py``.

This module is the single source of truth for resolving tenant context
on every ingestion request. Misresolution is a direct tenant-isolation
escape vector (issues #1081, #1102, #1184). The function has three
inputs and a strict authority order:

    API-key tenant > matching explicit/header tenant > legacy explicit/header tenant

Tests lock in:

* scoped API-key tenant authority and legacy fallback semantics
* explicit/header conflict rejection
* falsy-value passthrough (None, "")
* API-key happy path (row returned, tenant coerced to str)
* API-key miss path (row is None or empty tuple)
* DB-exception path (warning logged, None returned, session still closed)
* session close is always attempted (finally clause)

Tracks GitHub issue #1342.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.shared import tenant_resolution
from app.shared.tenant_resolution import resolve_principal_tenant_id, resolve_tenant_id


# ===========================================================================
# Test fixtures
# ===========================================================================


class _FakeRow:
    """Minimal stand-in for a SQLAlchemy Row — supports ``row[0]``."""

    def __init__(self, *cols):
        self._cols = cols

    def __getitem__(self, idx):
        return self._cols[idx]


class _FakeDb:
    """Captures execute() invocations and allows simulating close failures."""

    def __init__(self, fetch_row=None, raise_on_execute=None):
        self._fetch_row = fetch_row
        self._raise_on_execute = raise_on_execute
        self.executed = []
        self.closed = False

    def execute(self, statement, params=None):
        self.executed.append({"statement": str(statement), "params": params})
        if self._raise_on_execute is not None:
            raise self._raise_on_execute
        result = MagicMock()
        result.fetchone = MagicMock(return_value=self._fetch_row)
        return result

    def close(self):
        self.closed = True


def _install_db(monkeypatch, db):
    """Swap out ``get_db_safe`` on the tenant_resolution module."""
    monkeypatch.setattr(tenant_resolution, "get_db_safe", lambda: db)


# ===========================================================================
# Priority: explicit_tenant_id wins
# ===========================================================================


class TestExplicitTenantIdWins:

    def test_explicit_used_when_only_explicit_given(self, monkeypatch):
        """Legacy/master callers can still pass an explicit tenant."""
        db = _FakeDb(fetch_row=_FakeRow("from-api-key"))
        _install_db(monkeypatch, db)
        out = resolve_tenant_id(
            explicit_tenant_id="explicit-tenant",
            x_tenant_id=None,
            x_regengine_api_key=None,
        )
        assert out == "explicit-tenant"
        # No API key was supplied, so DB was never consulted.
        assert db.executed == []
        assert db.closed is False

    def test_explicit_wins_when_only_explicit_given(self, monkeypatch):
        out = resolve_tenant_id(
            explicit_tenant_id="t-1",
            x_tenant_id=None,
            x_regengine_api_key=None,
        )
        assert out == "t-1"

    def test_explicit_uuid_string_returned_verbatim(self):
        """No transformation — returns exactly what was passed in."""
        out = resolve_tenant_id(
            explicit_tenant_id="00000000-0000-0000-0000-000000000001",
            x_tenant_id=None,
            x_regengine_api_key=None,
        )
        assert out == "00000000-0000-0000-0000-000000000001"


# ===========================================================================
# Priority: x_tenant_id header (when explicit is None)
# ===========================================================================


class TestXTenantHeaderFallback:

    def test_header_used_when_explicit_is_none(self, monkeypatch):
        db = _FakeDb(fetch_row=_FakeRow("from-api-key"))
        _install_db(monkeypatch, db)
        out = resolve_tenant_id(
            explicit_tenant_id=None,
            x_tenant_id="header-tenant",
            x_regengine_api_key=None,
        )
        assert out == "header-tenant"
        assert db.executed == []

    def test_header_used_when_explicit_is_empty_string(self, monkeypatch):
        """Empty string is falsy — must fall through to header."""
        db = _FakeDb(fetch_row=_FakeRow("from-api-key"))
        _install_db(monkeypatch, db)
        out = resolve_tenant_id(
            explicit_tenant_id="",
            x_tenant_id="header-tenant",
            x_regengine_api_key=None,
        )
        assert out == "header-tenant"
        assert db.executed == []

    def test_header_only_no_api_key(self):
        out = resolve_tenant_id(
            explicit_tenant_id=None,
            x_tenant_id="header-only",
            x_regengine_api_key=None,
        )
        assert out == "header-only"


# ===========================================================================
# Priority: API-key DB lookup (when neither explicit nor header set)
# ===========================================================================


class TestApiKeyLookupHappyPath:

    def test_api_key_resolves_via_db(self, monkeypatch):
        db = _FakeDb(fetch_row=_FakeRow("tenant-xyz"))
        _install_db(monkeypatch, db)
        out = resolve_tenant_id(
            explicit_tenant_id=None,
            x_tenant_id=None,
            x_regengine_api_key="secret-key",
        )
        assert out == "tenant-xyz"
        assert db.closed is True
        # The query was parameterized — the raw key goes in params, never
        # interpolated into the SQL string (SQLi defense).
        assert db.executed[0]["params"] == {"raw": "secret-key"}
        sql = db.executed[0]["statement"]
        assert "api_keys" in sql
        assert "sha256" in sql
        assert "secret-key" not in sql  # never in the SQL text

    def test_api_key_row_coerced_to_string(self, monkeypatch):
        """UUIDs, ints, etc. get str()-coerced so callers always see str."""

        class _Uuidish:
            def __str__(self) -> str:
                return "coerced-tenant"

        db = _FakeDb(fetch_row=_FakeRow(_Uuidish()))
        _install_db(monkeypatch, db)
        out = resolve_tenant_id(None, None, "some-key")
        assert out == "coerced-tenant"
        assert isinstance(out, str)

    def test_api_key_numeric_row_coerced_to_string(self, monkeypatch):
        db = _FakeDb(fetch_row=_FakeRow(12345))
        _install_db(monkeypatch, db)
        out = resolve_tenant_id(None, None, "key")
        assert out == "12345"

    def test_api_key_tenant_matches_requested_tenant(self, monkeypatch):
        db = _FakeDb(fetch_row=_FakeRow("tenant-xyz"))
        _install_db(monkeypatch, db)
        out = resolve_tenant_id("tenant-xyz", None, "secret-key")
        assert out == "tenant-xyz"

    def test_api_key_tenant_rejects_requested_mismatch(self, monkeypatch):
        db = _FakeDb(fetch_row=_FakeRow("tenant-xyz"))
        _install_db(monkeypatch, db)
        with pytest.raises(HTTPException) as exc:
            resolve_tenant_id("other-tenant", None, "secret-key")
        assert exc.value.status_code == 403
        assert "Tenant mismatch" in exc.value.detail


class TestRequestedTenantConflicts:
    def test_explicit_and_header_conflict_rejected(self):
        with pytest.raises(HTTPException) as exc:
            resolve_tenant_id("explicit-tenant", "header-tenant", None)
        assert exc.value.status_code == 400
        assert "Conflicting tenant context" in exc.value.detail

    def test_matching_explicit_and_header_allowed(self):
        assert resolve_tenant_id("same-tenant", "same-tenant", None) == "same-tenant"


# ===========================================================================
# API-key lookup miss scenarios
# ===========================================================================


class TestApiKeyLookupMisses:

    def test_api_key_no_row_returns_none(self, monkeypatch):
        db = _FakeDb(fetch_row=None)
        _install_db(monkeypatch, db)
        out = resolve_tenant_id(None, None, "bogus-key")
        assert out is None
        assert db.closed is True

    def test_api_key_row_with_falsy_value_returns_none(self, monkeypatch):
        """``row[0]`` could be None (defensive — unusual but allowed)."""
        db = _FakeDb(fetch_row=_FakeRow(None))
        _install_db(monkeypatch, db)
        out = resolve_tenant_id(None, None, "key")
        assert out is None
        assert db.closed is True

    def test_api_key_row_with_empty_string_returns_none(self, monkeypatch):
        db = _FakeDb(fetch_row=_FakeRow(""))
        _install_db(monkeypatch, db)
        out = resolve_tenant_id(None, None, "key")
        assert out is None
        assert db.closed is True


# ===========================================================================
# No identifiers at all
# ===========================================================================


class TestNoIdentifiersAtAll:

    def test_all_none_returns_none(self):
        assert resolve_tenant_id(None, None, None) is None

    def test_all_empty_strings_returns_none(self):
        """Every input falsy → None, without a DB hit."""
        assert resolve_tenant_id("", "", "") is None

    def test_no_api_key_skips_db_lookup(self, monkeypatch):
        """Short-circuits before ``get_db_safe`` is even called."""
        called = {"flag": False}

        def _sentinel():
            called["flag"] = True
            return _FakeDb()

        monkeypatch.setattr(tenant_resolution, "get_db_safe", _sentinel)
        out = resolve_tenant_id(None, None, None)
        assert out is None
        assert called["flag"] is False


class TestResolvePrincipalTenantId:
    def test_principal_tenant_is_authoritative(self):
        assert (
            resolve_principal_tenant_id(None, None, "principal-tenant")
            == "principal-tenant"
        )

    def test_principal_tenant_allows_matching_request(self):
        assert (
            resolve_principal_tenant_id("principal-tenant", None, "principal-tenant")
            == "principal-tenant"
        )

    def test_principal_tenant_rejects_mismatched_request(self):
        with pytest.raises(HTTPException) as exc:
            resolve_principal_tenant_id("other-tenant", None, "principal-tenant")
        assert exc.value.status_code == 403
        assert "Tenant mismatch" in exc.value.detail

    def test_legacy_principal_uses_requested_tenant(self):
        assert resolve_principal_tenant_id(None, "header-tenant", None) == "header-tenant"

    def test_missing_legacy_tenant_rejected(self):
        with pytest.raises(HTTPException) as exc:
            resolve_principal_tenant_id(None, None, None)
        assert exc.value.status_code == 400
        assert "Tenant context required" in exc.value.detail

    def test_explicit_header_conflict_rejected(self):
        with pytest.raises(HTTPException) as exc:
            resolve_principal_tenant_id("explicit-tenant", "header-tenant", None)
        assert exc.value.status_code == 400
        assert "Conflicting tenant context" in exc.value.detail


# ===========================================================================
# DB-failure path — exception raised during execute()
# ===========================================================================


class TestDbFailurePath:

    def test_db_execute_exception_logged_and_returns_none(
        self, monkeypatch, caplog
    ):
        db = _FakeDb(raise_on_execute=RuntimeError("connection refused"))
        _install_db(monkeypatch, db)

        import logging

        with caplog.at_level(logging.WARNING, logger=tenant_resolution.__name__):
            out = resolve_tenant_id(None, None, "key")

        assert out is None
        # Session MUST be closed even when execute() raised.
        assert db.closed is True
        # Warning logged with the exception message.
        assert any("tenant_lookup_failed" in rec.message for rec in caplog.records)
        assert any("connection refused" in rec.message for rec in caplog.records)

    def test_db_execute_integrity_error_swallowed(self, monkeypatch):
        from sqlalchemy.exc import OperationalError

        db = _FakeDb(
            raise_on_execute=OperationalError(
                "SELECT", {}, Exception("db gone")
            )
        )
        _install_db(monkeypatch, db)
        out = resolve_tenant_id(None, None, "key")
        assert out is None
        assert db.closed is True

    def test_db_execute_value_error_swallowed(self, monkeypatch):
        db = _FakeDb(raise_on_execute=ValueError("boom"))
        _install_db(monkeypatch, db)
        out = resolve_tenant_id(None, None, "key")
        assert out is None
        assert db.closed is True

    def test_db_close_always_called_even_on_success(self, monkeypatch):
        db = _FakeDb(fetch_row=_FakeRow("tenant"))
        _install_db(monkeypatch, db)
        resolve_tenant_id(None, None, "key")
        assert db.closed is True


# ===========================================================================
# Priority is ORDER-SENSITIVE — cover each pair
# ===========================================================================


class TestPriorityOrderPairs:

    @pytest.mark.parametrize(
        "explicit,header,api_key,expected",
        [
            ("A", "A", None, "A"),        # matching explicit/header
            ("A", None, None, "A"),       # explicit alone
            (None, "B", None, "B"),       # header alone
            (None, None, None, None),     # nothing
            ("", "B", None, "B"),         # explicit falsy → header
            ("", "", "C", None),          # both falsy + api_key miss
            ("", None, None, None),       # explicit falsy alone
        ],
    )
    def test_priority_pairs(self, monkeypatch, explicit, header, api_key, expected):
        # API-key path → return None (no tenant in DB) for ("", "", "C") case.
        db = _FakeDb(fetch_row=None)
        _install_db(monkeypatch, db)
        out = resolve_tenant_id(explicit, header, api_key)
        assert out == expected


# ===========================================================================
# Module surface
# ===========================================================================


class TestModuleSurface:

    def test_resolve_tenant_id_is_exported(self):
        import app.shared.tenant_resolution as m
        assert callable(m.resolve_tenant_id)

    def test_logger_is_module_level(self):
        import logging
        import app.shared.tenant_resolution as m
        assert isinstance(m.logger, logging.Logger)
        assert m.logger.name == "app.shared.tenant_resolution"
