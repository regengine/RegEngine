"""
Regression coverage for the ``GUID`` and ``JSONType`` type-decorators
in ``app/sqlalchemy_models.py``.

The admin service is dev-tested against SQLite but deployed on Postgres.
The Postgres-only branches of the two ``TypeDecorator`` subclasses
(``GUID.load_dialect_impl``, ``GUID.process_bind_param``,
``GUID.process_result_value``, and ``JSONType.load_dialect_impl``) are
therefore never hit by the default test harness — which means any
regression in the Postgres serialization path lands in production
without a local test failure.

These tests mock the SQLAlchemy dialect object so both SQLite and
Postgres branches fire regardless of what driver the test harness is
using. Pinned branches:

* Lines 22-24 — ``GUID.load_dialect_impl`` returns ``PG_UUID(as_uuid=True)``
  for the ``postgresql`` dialect (no string conversion at the driver
  boundary).
* Line 31 — ``GUID.process_bind_param`` passes UUID values through
  unchanged on Postgres (no stringification).
* Line 39 — ``GUID.process_result_value`` skips the string-to-UUID
  conversion when the driver already returns a ``uuid.UUID`` (Postgres
  UUID column).
* Lines 50-51 — ``JSONType.load_dialect_impl`` returns ``JSONB`` on
  Postgres so we get indexed JSON rather than the generic ``JSON``.

Tracks GitHub issue #1342.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

service_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("sqlalchemy")

from app.sqlalchemy_models import GUID, JSONType  # noqa: E402


def _mk_dialect(name: str):
    """Build a mock SQLAlchemy dialect that echoes its type_descriptor arg."""
    dialect = MagicMock()
    dialect.name = name
    # type_descriptor returns the impl instance passed in — let tests see it
    dialect.type_descriptor.side_effect = lambda impl: ("dispatched", impl)
    return dialect


# ---------------------------------------------------------------------------
# GUID.load_dialect_impl — lines 22-24 (postgres) vs line 25 (other)
# ---------------------------------------------------------------------------


class TestGuidLoadDialectImpl:

    def test_postgres_dialect_returns_pg_uuid(self):
        """Lines 22-24: on Postgres, GUID maps to the native UUID type
        (``PG_UUID(as_uuid=True)``) instead of CHAR(36). This is the
        production production code path — never hit by the SQLite
        test harness."""
        guid = GUID()
        dialect = _mk_dialect("postgresql")

        result = guid.load_dialect_impl(dialect)

        # type_descriptor was called with a PG_UUID instance
        assert dialect.type_descriptor.called
        arg = dialect.type_descriptor.call_args[0][0]
        # PG_UUID is imported inside the function — confirm the class name
        assert arg.__class__.__name__ == "UUID"
        # as_uuid=True is the critical flag — keeps UUID round-trip intact
        assert getattr(arg, "as_uuid", None) is True
        # Result is whatever type_descriptor returned
        assert result[0] == "dispatched"

    def test_sqlite_dialect_returns_char36(self):
        """Line 25: non-Postgres dialects fall back to CHAR(36). This is
        the existing dev harness path — keep it pinned so the migration
        branch can't silently flip it."""
        guid = GUID()
        dialect = _mk_dialect("sqlite")

        result = guid.load_dialect_impl(dialect)

        arg = dialect.type_descriptor.call_args[0][0]
        assert arg.__class__.__name__ == "CHAR"
        assert result[0] == "dispatched"


# ---------------------------------------------------------------------------
# GUID.process_bind_param — line 31 (postgres passthrough)
# ---------------------------------------------------------------------------


class TestGuidProcessBindParam:

    def test_none_returns_none_regardless_of_dialect(self):
        guid = GUID()
        assert guid.process_bind_param(None, _mk_dialect("postgresql")) is None
        assert guid.process_bind_param(None, _mk_dialect("sqlite")) is None

    def test_postgres_passes_uuid_through_unchanged(self):
        """Line 31: Postgres driver accepts UUID objects natively, so
        we must NOT stringify — that would round-trip through the
        char-based column on the wrong dialect."""
        guid = GUID()
        u = uuid.uuid4()

        result = guid.process_bind_param(u, _mk_dialect("postgresql"))

        assert result is u  # identity — no conversion
        assert isinstance(result, uuid.UUID)

    def test_sqlite_stringifies_uuid(self):
        """Line 32: non-Postgres writes as CHAR(36), so we stringify."""
        guid = GUID()
        u = uuid.uuid4()

        result = guid.process_bind_param(u, _mk_dialect("sqlite"))

        assert result == str(u)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# GUID.process_result_value — line 39 (already-UUID short-circuit)
# ---------------------------------------------------------------------------


class TestGuidProcessResultValue:

    def test_none_returns_none(self):
        guid = GUID()
        assert guid.process_result_value(None, _mk_dialect("postgresql")) is None

    def test_already_uuid_returned_unchanged(self):
        """Line 39: Postgres with as_uuid=True already returns uuid.UUID.
        The check ``if not isinstance(value, uuid.UUID)`` prevents a
        double-conversion through ``uuid.UUID(uuid.UUID(...))`` which
        would TypeError."""
        guid = GUID()
        u = uuid.uuid4()

        result = guid.process_result_value(u, _mk_dialect("postgresql"))

        assert result is u  # identity
        assert isinstance(result, uuid.UUID)

    def test_string_converted_to_uuid(self):
        """Line 38: CHAR(36) comes back as str — convert to UUID."""
        guid = GUID()
        s = "12345678-1234-5678-1234-567812345678"

        result = guid.process_result_value(s, _mk_dialect("sqlite"))

        assert isinstance(result, uuid.UUID)
        assert str(result) == s


# ---------------------------------------------------------------------------
# JSONType.load_dialect_impl — lines 50-51 (postgres -> JSONB)
# ---------------------------------------------------------------------------


class TestJsonTypeLoadDialectImpl:

    def test_postgres_dialect_returns_jsonb(self):
        """Lines 50-51: on Postgres we want JSONB for index support —
        the generic JSON type doesn't get GIN indexing."""
        jt = JSONType()
        dialect = _mk_dialect("postgresql")

        result = jt.load_dialect_impl(dialect)

        arg = dialect.type_descriptor.call_args[0][0]
        assert arg.__class__.__name__ == "JSONB"
        assert result[0] == "dispatched"

    def test_sqlite_dialect_returns_generic_json(self):
        """Line 52: non-Postgres falls back to the generic JSON type
        (stored as TEXT on SQLite). Kept pinned."""
        jt = JSONType()
        dialect = _mk_dialect("sqlite")

        result = jt.load_dialect_impl(dialect)

        arg = dialect.type_descriptor.call_args[0][0]
        assert arg.__class__.__name__ == "JSON"
        assert result[0] == "dispatched"
