"""Regression tests for RE-SCH-002: raw-string ``session.execute(...)``.

Five sites in ``compliance_integration.py`` were passing raw SQL strings to
``session.execute(...)``. Under SQLAlchemy 2.x that raises
``ObjectNotExecutableError`` immediately, but the broad outer ``except
Exception`` was silently catching the failure — which meant Tier-2/3
supplier-name compliance alerts were not firing in production.

These tests use a real SQLite session so the SQLAlchemy 2.x executable
check actually runs. A pure mock would not catch a regression where someone
removes the ``text(...)`` wrapper, because mocked ``session.execute`` would
accept anything.

We don't exercise the full INSERT path (the schemas reference Postgres-only
features like ``gen_random_uuid()`` and JSONB) — instead we drive
``_find_matching_tenants``, which is the path that was broken in prod, and
assert it executes both Tier-1 and Tier-2/3 queries without raising.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def sqlite_session():
    """Create an in-memory SQLite DB with a stand-in tenant_product_profile."""
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        # SQLite-compatible stand-in. The real Postgres table has array
        # columns; we collapse them to TEXT here since the regression we
        # care about (raw-string -> ObjectNotExecutableError) fires
        # *before* SQLAlchemy ever inspects the column types.
        conn.execute(
            text(
                """
                CREATE TABLE tenant_product_profile (
                    tenant_id TEXT PRIMARY KEY,
                    product_categories TEXT,
                    supply_regions TEXT,
                    supplier_identifiers TEXT
                )
                """
            )
        )
    Session = sessionmaker(bind=engine)
    return Session()


def _make_item():
    """Construct a minimal EnforcementItem-like object."""
    from app.models import EnforcementItem, EnforcementSeverity, SourceType

    return EnforcementItem(
        source_type=SourceType.FDA_RECALL,
        source_id="fda_rec:test-1",
        title="Test Recall",
        summary="lettuce contamination",
        url="https://example.test/recall/1",
        published_date=datetime.now(timezone.utc),
        severity=EnforcementSeverity.HIGH,
        affected_companies=["Acme Foods"],
        raw_data={"code_info": "LOT-A; LOT-B"},
    )


def test_find_matching_tenants_executes_against_real_session(sqlite_session, monkeypatch):
    """The Tier-2/3 SELECT must run end-to-end against a real DBAPI cursor.

    Before the fix, ``session.execute("SELECT ...")`` raised
    ``ObjectNotExecutableError`` and the outer ``except`` ate it. Now it
    must reach the DB and return zero rows (empty fixture table).
    """
    # Avoid touching the singleton — instantiate ComplianceIntegration with
    # a fake settings.database_url and then swap in our SQLite session.
    from app import compliance_integration as ci_module

    fake_settings = MagicMock()
    fake_settings.database_url = "sqlite:///:memory:"
    monkeypatch.setattr(ci_module, "get_settings", lambda: fake_settings)

    integration = ci_module.ComplianceIntegration()
    item = _make_item()

    # Use our pre-seeded SQLite session directly.
    matches = integration._find_matching_tenants(sqlite_session, item)

    # The interesting assertion is that this RETURNED at all (no swallowed
    # ObjectNotExecutableError on the Tier-2/3 query). The empty fixture
    # table means there are no Tier-2/3 matches and no lot codes in the
    # ``traceability_events`` table either.
    assert matches == []


def test_find_matching_tenants_tier1_query_uses_text(sqlite_session, monkeypatch):
    """Tier-1 lot-code query also must not regress to raw-string form.

    SQLite does not have ``fsma.traceability_events``; we expect the Tier-1
    path to swallow a ``SQLAlchemyError`` (which is correct behaviour) but
    NEVER an ``ObjectNotExecutableError``-from-raw-string. We assert that
    by patching ``session.execute`` to verify the first call passes a
    ``TextClause``, not a ``str``.
    """
    from sqlalchemy.sql.elements import TextClause

    from app import compliance_integration as ci_module

    fake_settings = MagicMock()
    fake_settings.database_url = "sqlite:///:memory:"
    monkeypatch.setattr(ci_module, "get_settings", lambda: fake_settings)

    integration = ci_module.ComplianceIntegration()
    item = _make_item()

    captured: list = []
    real_execute = sqlite_session.execute

    def _capturing_execute(stmt, *args, **kwargs):
        captured.append(stmt)
        # Re-raise as if the table were missing so we still hit the Tier-2
        # path; that's fine because the Tier-2 query has its own assertion.
        return real_execute(stmt, *args, **kwargs) if not isinstance(
            stmt, str
        ) else (_ for _ in ()).throw(  # pragma: no cover
            AssertionError("raw string passed to session.execute")
        )

    with patch.object(sqlite_session, "execute", side_effect=_capturing_execute):
        try:
            integration._find_matching_tenants(sqlite_session, item)
        except Exception:  # noqa: BLE001 - SQLite missing-table is fine
            pass

    # Every captured statement must be a TextClause (or a SQLAlchemy
    # construct), never a raw ``str``.
    for stmt in captured:
        assert not isinstance(stmt, str), (
            f"raw-string statement passed to session.execute: {stmt!r}"
        )
        # All five fixed sites use text(); validate at least one did.
    assert any(isinstance(s, TextClause) for s in captured)
