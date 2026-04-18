"""
Hardening tests for services.shared.identity_resolution.

Covers:
  - #1175: TLC stored verbatim as alias_type='tlc', not 'tlc_prefix'
  - #1177: fuzzy find_potential_matches does not corrupt identifier paths
  - #1179: UNIQUE(tenant_id, alias_type, alias_value) dedup
  - #1190: _resolve_or_register advisory lock + UNIQUE-constraint-backed
           race-free register

Mock-based unit tests only; DB-level integration is exercised separately
by the alembic migration and by tests/test_e2e_identity_ambiguity.py.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from services.shared.identity_resolution import (
    VALID_ALIAS_TYPES,
    IdentityResolutionService,
)

TENANT = "tenant-hardening"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session():
    session = MagicMock()
    # Default: no fuzzy-match rows, _require_entity succeeds
    session.execute.return_value.fetchall.return_value = []
    session.execute.return_value.fetchone.return_value = (1,)
    return session


@pytest.fixture
def svc(mock_session):
    return IdentityResolutionService(mock_session)


# ---------------------------------------------------------------------------
# #1175 — TLC stored verbatim under alias_type='tlc'
# ---------------------------------------------------------------------------


class TestTLCVerbatimStorage:
    def test_tlc_is_a_valid_alias_type(self):
        """Issue #1175: 'tlc' must be accepted as a canonical alias type."""
        assert "tlc" in VALID_ALIAS_TYPES
        assert "tlc_prefix" in VALID_ALIAS_TYPES  # still valid for secondary

    def test_auto_register_uses_tlc_not_tlc_prefix(self, svc, mock_session):
        """
        When auto_register_from_event sees a traceability_lot_code, it must
        call _resolve_or_register with alias_type='tlc' (verbatim), not
        'tlc_prefix' (lossy GTIN prefix).
        """
        tlc_value = "00012345678901-Lot-ABC-7"
        event = {"traceability_lot_code": tlc_value}
        calls_seen = []
        real_resolve = svc._resolve_or_register

        def _capture(**kwargs):
            calls_seen.append(kwargs)
            # Short-circuit so we don't actually execute SQL for the rest
            # of the register flow.
            return {
                "entity_id": "lot-entity-001",
                "canonical_name": kwargs["reference"],
                "resolution": "new",
            }

        svc._resolve_or_register = _capture  # type: ignore[assignment]
        try:
            svc.auto_register_from_event(TENANT, event)
        finally:
            svc._resolve_or_register = real_resolve  # type: ignore[assignment]

        lot_calls = [c for c in calls_seen if c.get("entity_type") == "lot"]
        assert len(lot_calls) == 1, "Exactly one lot _resolve_or_register call expected"
        assert lot_calls[0]["reference"] == tlc_value, \
            "TLC reference must be passed verbatim — no normalization or truncation"
        assert lot_calls[0]["alias_type"] == "tlc", \
            "Canonical alias_type for a TLC must be 'tlc', not 'tlc_prefix'"

    def test_auto_register_short_tlc_skips_prefix_alias(self, svc, mock_session):
        """A non-GTIN-14-prefixed TLC must not emit a spurious tlc_prefix alias."""
        short_tlc = "LOT-ABC-123"  # no 14-digit leading GTIN
        event = {"traceability_lot_code": short_tlc}

        def _capture(**kwargs):
            return {
                "entity_id": "lot-entity-002",
                "canonical_name": kwargs["reference"],
                "resolution": "new",
            }

        svc._resolve_or_register = _capture  # type: ignore[assignment]
        inserted_aliases = []

        def _insert_tracker(*args, **kwargs):
            inserted_aliases.append(kwargs.get("alias_type"))
            return "alias-id"

        svc._insert_alias = _insert_tracker  # type: ignore[assignment]
        svc.auto_register_from_event(TENANT, event)

        assert "tlc_prefix" not in inserted_aliases, \
            "Short TLCs without a GTIN-14 prefix must not produce a tlc_prefix alias"

    def test_auto_register_long_tlc_emits_prefix_alias(self, svc, mock_session):
        """A GTIN-14 + lot-suffix TLC also emits a secondary tlc_prefix alias."""
        long_tlc = "00012345678901-Lot-ABC-7"
        event = {"traceability_lot_code": long_tlc}

        def _capture(**kwargs):
            return {
                "entity_id": "lot-entity-003",
                "canonical_name": kwargs["reference"],
                "resolution": "new",
            }

        svc._resolve_or_register = _capture  # type: ignore[assignment]

        inserted_aliases = []

        def _insert_tracker(*args, **kwargs):
            inserted_aliases.append({
                "alias_type": kwargs.get("alias_type"),
                "alias_value": kwargs.get("alias_value"),
            })
            return "alias-id"

        svc._insert_alias = _insert_tracker  # type: ignore[assignment]
        svc.auto_register_from_event(TENANT, event)

        prefix_aliases = [a for a in inserted_aliases if a["alias_type"] == "tlc_prefix"]
        assert len(prefix_aliases) == 1, \
            "GTIN-14 prefixed TLC should emit exactly one tlc_prefix alias"
        assert prefix_aliases[0]["alias_value"] == "00012345678901", \
            "tlc_prefix alias value must be the verbatim first-14-digit GTIN-14"
