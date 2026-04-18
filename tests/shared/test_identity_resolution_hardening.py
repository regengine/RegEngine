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


# ---------------------------------------------------------------------------
# #1177 — fuzzy matching must not corrupt identifier paths
# ---------------------------------------------------------------------------


class TestFuzzyDoesNotCorruptIdentifiers:
    def test_case_sensitive_flag_preserves_case(self, svc, mock_session):
        """
        case_sensitive=True must compare raw values without normalization,
        so identifier-shaped fuzzy matching (if callers ever opt in) does
        not silently collide unrelated lot codes.
        """
        mock_session.execute.return_value.fetchall.return_value = [
            ("eid-1", "lot", "LOT-abc", None, None, "unverified", 1.0, "LOT-abc"),
        ]
        # Case-sensitive comparison of "LOT-ABC" vs "LOT-abc" should NOT
        # produce a perfect-score match — they differ in case.
        results = svc.find_potential_matches(
            TENANT, "LOT-ABC", case_sensitive=True, threshold=0.0,
        )
        # A match may still appear (they share most characters) but the
        # score must be strictly less than 1.0 — a perfect score would
        # have meant case was folded.
        assert len(results) == 1
        assert results[0]["confidence"] < 1.0, \
            "case_sensitive=True must not fold case in the similarity score"

    def test_case_insensitive_still_default(self, svc, mock_session):
        """Default fuzzy path (for names) is still case-insensitive."""
        mock_session.execute.return_value.fetchall.return_value = [
            ("eid-1", "facility", "Acme", None, None, "unverified", 1.0, "ACME FOODS"),
        ]
        results = svc.find_potential_matches(TENANT, "acme foods")
        assert len(results) == 1
        assert results[0]["confidence"] == 1.0

    def test_resolve_or_register_skips_fuzzy_for_identifiers(
        self, svc, mock_session
    ):
        """
        _resolve_or_register must NOT invoke find_potential_matches for
        identifier alias_types (tlc, gln, gtin, fda_registration, etc.),
        because fuzzy name matching over identifiers silently collides
        unrelated lot codes (#1177).
        """
        # No exact match found
        mock_session.execute.return_value.fetchall.return_value = []
        fuzzy_calls = []
        real_fuzzy = svc.find_potential_matches

        def _fuzzy_spy(*args, **kwargs):
            fuzzy_calls.append((args, kwargs))
            return []

        svc.find_potential_matches = _fuzzy_spy  # type: ignore[assignment]
        svc._resolve_or_register(
            tenant_id=TENANT,
            reference="00012345678901-Lot-ABC-7",
            entity_type="lot",
            source_system="test",
            alias_type="tlc",
        )

        assert fuzzy_calls == [], \
            "find_potential_matches must not be called for alias_type='tlc' (#1177)"
        svc.find_potential_matches = real_fuzzy  # type: ignore[assignment]

    def test_resolve_or_register_uses_fuzzy_for_names(
        self, svc, mock_session
    ):
        """Name-type refs still use fuzzy matching (that IS the correct path)."""
        mock_session.execute.return_value.fetchall.return_value = []
        fuzzy_calls = []

        def _fuzzy_spy(*args, **kwargs):
            fuzzy_calls.append((args, kwargs))
            return []

        svc.find_potential_matches = _fuzzy_spy  # type: ignore[assignment]
        svc._resolve_or_register(
            tenant_id=TENANT,
            reference="Acme Foods",
            entity_type="firm",
            source_system="test",
            alias_type="name",
        )
        assert len(fuzzy_calls) == 1, \
            "find_potential_matches must still be invoked for alias_type='name'"

    def test_resolve_or_register_persists_identifier_alias(
        self, svc, mock_session
    ):
        """
        After registering a new entity for an identifier reference (e.g. tlc,
        gln), _resolve_or_register must persist the alias under the caller's
        alias_type so subsequent find_entity_by_alias(..., 'tlc', ...) matches
        succeed.
        """
        mock_session.execute.return_value.fetchall.return_value = []
        seen_alias_types = []
        real_insert = svc._insert_alias

        def _insert_tracker(**kwargs):
            seen_alias_types.append(kwargs.get("alias_type"))
            return "alias-id"

        svc._insert_alias = _insert_tracker  # type: ignore[assignment]
        svc._resolve_or_register(
            tenant_id=TENANT,
            reference="00012345678901",
            entity_type="lot",
            source_system="test",
            alias_type="tlc",
        )
        svc._insert_alias = real_insert  # type: ignore[assignment]

        assert "tlc" in seen_alias_types, (
            "Identifier alias_type must be persisted on resolve_or_register (#1177)"
        )


# ---------------------------------------------------------------------------
# #1179 / #1190 — advisory lock + UNIQUE constraint
# ---------------------------------------------------------------------------


class TestAdvisoryLockAndUniqueConstraint:
    @staticmethod
    def _extract_key(mock_session):
        last_call = mock_session.execute.call_args
        if last_call.kwargs.get("key") is not None:
            return last_call.kwargs["key"]
        if len(last_call.args) >= 2 and isinstance(last_call.args[1], dict):
            return last_call.args[1].get("key")
        return None

    def test_resolve_acquires_advisory_lock(self, svc, mock_session):
        """
        _resolve_or_register must issue pg_advisory_xact_lock before the
        exact-match SELECT to serialize the critical section per
        (tenant, alias_type, alias_value).
        """
        mock_session.execute.return_value.fetchall.return_value = []
        svc._resolve_or_register(
            tenant_id=TENANT,
            reference="Acme",
            entity_type="firm",
            source_system="test",
            alias_type="name",
        )
        # Look for the advisory lock SQL string in the executed calls.
        executed_sqls = [
            str(c.args[0]) for c in mock_session.execute.call_args_list
            if c.args
        ]
        lock_calls = [
            s for s in executed_sqls if "pg_advisory_xact_lock" in s
        ]
        assert len(lock_calls) >= 1, (
            "Expected pg_advisory_xact_lock to be issued for race-free "
            "register (#1190)"
        )

    def test_advisory_lock_key_is_deterministic(self, svc, mock_session):
        """The same (tenant, alias_type, alias_value) triple must map to
        the same lock key, so concurrent workers serialize correctly."""
        svc._acquire_resolve_lock(TENANT, "tlc", "TLC-ABC")
        key1 = self._extract_key(mock_session)
        mock_session.reset_mock()
        mock_session.execute.return_value.fetchall.return_value = []
        mock_session.execute.return_value.fetchone.return_value = (1,)

        svc._acquire_resolve_lock(TENANT, "tlc", "TLC-ABC")
        key2 = self._extract_key(mock_session)
        assert key1 is not None and key1 == key2, \
            "Advisory lock key must be deterministic for the same triple"

    def test_advisory_lock_different_triples_different_keys(self, svc, mock_session):
        """Different triples must produce different keys so unrelated
        inserts never block each other."""
        svc._acquire_resolve_lock(TENANT, "tlc", "TLC-A")
        key_a = self._extract_key(mock_session)
        mock_session.reset_mock()
        mock_session.execute.return_value.fetchall.return_value = []
        mock_session.execute.return_value.fetchone.return_value = (1,)

        svc._acquire_resolve_lock(TENANT, "tlc", "TLC-B")
        key_b = self._extract_key(mock_session)
        assert key_a != key_b, \
            "Distinct alias triples must hash to distinct lock keys"

    def test_advisory_lock_fits_bigint_range(self, svc, mock_session):
        """Lock key must be in Postgres BIGINT range (signed 63-bit)."""
        svc._acquire_resolve_lock(TENANT, "tlc", "X" * 200)
        key = self._extract_key(mock_session)
        assert key is not None
        assert 0 <= key < (1 << 63), "Key must fit signed BIGINT"

    def test_advisory_lock_failure_is_non_fatal(self, svc, mock_session):
        """If the advisory lock query raises (e.g. sqlite backend), the
        service degrades to relying on the UNIQUE constraint."""
        mock_session.execute.side_effect = [Exception("sqlite has no pg_advisory")]
        # Must not raise.
        svc._acquire_resolve_lock(TENANT, "tlc", "X")

    def test_insert_alias_uses_on_conflict_do_nothing(self, svc, mock_session):
        """_insert_alias SQL must include ON CONFLICT DO NOTHING so the
        UNIQUE constraint added in migration v059 provides race-free
        dedup without raising IntegrityError (#1179)."""
        svc._insert_alias(
            tenant_id=TENANT,
            entity_id="eid-1",
            alias_type="tlc",
            alias_value="TLC-123",
            source_system="test",
        )
        executed_sqls = [
            str(c.args[0]) for c in mock_session.execute.call_args_list
            if c.args
        ]
        assert any(
            "ON CONFLICT" in sql and "DO NOTHING" in sql
            for sql in executed_sqls
        ), "_insert_alias must use ON CONFLICT DO NOTHING for race-free dedup"
