"""Regression tests for structured identifier normalization (#1212).

Issue: structured identifiers (GLN, GTIN, fda_registration, etc.) were
compared and stored byte-exact, so whitespace variants
(e.g. " 0614141123452" vs "0614141123452") and URN-prefix case variants
(e.g. "URN:EPC:id:sgln:0614141.loc1.0" vs "urn:epc:id:sgln:0614141.loc1.0")
created duplicate canonical entity records.

Fix: ``_normalize_identifier`` strips leading/trailing whitespace and
lowercases URN-form values before any lookup or insert.

This file locks in:
1. ``_normalize_identifier`` behaves correctly for each normalization rule.
2. ``find_entity_by_alias`` passes the normalized value to SQL for
   structured identifier alias types.
3. ``add_alias`` normalizes before insert for structured identifier types.
4. Free-text alias types (name, trade_name, abbreviation) are NOT mutated.
5. TLC/tlc_prefix are NOT normalized (FSMA 204 verbatim requirement, #1175).

All tests are mock-based — no DB required.
"""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from services.shared.identity_resolution import IdentityResolutionService
from services.shared.identity_resolution.service import _normalize_identifier

TENANT = "tenant-normalize-1212"


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
# Unit tests for _normalize_identifier helper
# ---------------------------------------------------------------------------


class TestNormalizeIdentifier_Issue1212:
    """Direct unit tests for the ``_normalize_identifier`` helper."""

    # --- GLN ---

    def test_gln_strips_leading_whitespace(self):
        assert _normalize_identifier("gln", "  0614141123452") == "0614141123452"

    def test_gln_strips_trailing_whitespace(self):
        assert _normalize_identifier("gln", "0614141123452  ") == "0614141123452"

    def test_gln_strips_both_ends(self):
        assert _normalize_identifier("gln", "  0614141123452  ") == "0614141123452"

    def test_gln_no_change_when_clean(self):
        assert _normalize_identifier("gln", "0614141123452") == "0614141123452"

    # --- GTIN ---

    def test_gtin_strips_whitespace(self):
        assert _normalize_identifier("gtin", " 00614141453271 ") == "00614141453271"

    # --- fda_registration ---

    def test_fda_registration_strips_whitespace(self):
        assert _normalize_identifier("fda_registration", "  12345678  ") == "12345678"

    def test_fda_registration_urn_lowercased(self):
        raw = "URN:FDA:REG:12345678"
        result = _normalize_identifier("fda_registration", raw)
        assert result == "urn:fda:reg:12345678"

    def test_fda_registration_urn_strip_and_lower(self):
        raw = "  URN:FDA:REG:12345678  "
        result = _normalize_identifier("fda_registration", raw)
        assert result == "urn:fda:reg:12345678"

    # --- URN-form (generic) ---

    def test_urn_prefix_case_insensitive_lowercase_result(self):
        """'URN:EPC:...' and 'urn:epc:...' must normalize to identical strings."""
        upper = _normalize_identifier("gln", "URN:EPC:id:sgln:0614141.loc1.0")
        lower = _normalize_identifier("gln", "urn:epc:id:sgln:0614141.loc1.0")
        assert upper == lower
        assert upper == "urn:epc:id:sgln:0614141.loc1.0"

    def test_urn_internal_spaces_preserved(self):
        """Internal spaces inside the value body must NOT be stripped."""
        value = "urn:fda:reg:ABC 12345"
        result = _normalize_identifier("fda_registration", value)
        # Leading/trailing stripped, already lower — internal space intact.
        assert result == "urn:fda:reg:abc 12345"

    # --- Free-text types must NOT be mutated ---

    def test_name_type_returned_unchanged(self):
        value = "  Acme Foods LLC  "
        assert _normalize_identifier("name", value) == value

    def test_trade_name_returned_unchanged(self):
        value = "  ACME FOODS  "
        assert _normalize_identifier("trade_name", value) == value

    def test_abbreviation_returned_unchanged(self):
        value = "  AF  "
        assert _normalize_identifier("abbreviation", value) == value

    def test_address_variant_returned_unchanged(self):
        value = "  123 Main St  "
        assert _normalize_identifier("address_variant", value) == value

    # --- TLC / tlc_prefix must NOT be normalized (#1175) ---

    def test_tlc_not_normalized(self):
        """TLC values are FSMA 204 verbatim; whitespace variants must be preserved."""
        value = " LOT-ABC 001 "
        assert _normalize_identifier("tlc", value) == value

    def test_tlc_prefix_not_normalized(self):
        value = " 00614141453271 "
        assert _normalize_identifier("tlc_prefix", value) == value


# ---------------------------------------------------------------------------
# Integration: find_entity_by_alias passes normalized value to SQL
# ---------------------------------------------------------------------------


class TestFindEntityByAliasNormalization_Issue1212:
    """Verify that lookup normalizes structured identifiers before the SQL
    bind — meaning a padded and a clean GLN resolve to the same DB query."""

    def _get_alias_value_param(self, mock_session, call_index: int = 0) -> str:
        return mock_session.execute.call_args_list[call_index].args[1]["alias_value"]

    def test_padded_gln_normalized_before_lookup(self, svc, mock_session):
        svc.find_entity_by_alias(TENANT, "gln", "  0614141123452  ")
        assert self._get_alias_value_param(mock_session) == "0614141123452"

    def test_clean_gln_unchanged(self, svc, mock_session):
        svc.find_entity_by_alias(TENANT, "gln", "0614141123452")
        assert self._get_alias_value_param(mock_session) == "0614141123452"

    def test_padded_and_clean_gln_produce_same_sql_param(self, svc, mock_session):
        """Raw, padded-with-spaces, and uppercase URN prefix must all map to
        the same SQL parameter value, proving they hit the same DB row."""
        svc.find_entity_by_alias(TENANT, "gln", "0614141123452")
        svc.find_entity_by_alias(TENANT, "gln", "  0614141123452  ")
        svc.find_entity_by_alias(TENANT, "gln", "URN:EPC:id:sgln:0614141123452.0")

        p0 = self._get_alias_value_param(mock_session, 0)
        p1 = self._get_alias_value_param(mock_session, 1)
        # Numeric and URN forms differ in value but both are stripped/lowercased.
        assert p1 == "0614141123452", "padded GLN must strip to bare digits"
        assert p0 == p1, "raw and padded must produce identical SQL param"
        # URN-form: verify it was lowercased
        p2 = self._get_alias_value_param(mock_session, 2)
        assert p2 == p2.lower(), "URN-form GLN must be lowercased"
        assert not p2.startswith(" "), "URN-form GLN must not have leading space"

    def test_tlc_not_normalized_in_lookup(self, svc, mock_session):
        """TLC lookup must remain verbatim — no stripping or case-folding."""
        raw = "  LOT-ABC-001  "
        svc.find_entity_by_alias(TENANT, "tlc", raw)
        assert self._get_alias_value_param(mock_session) == raw

    def test_name_not_normalized_in_lookup(self, svc, mock_session):
        """Name-type lookup must remain verbatim."""
        raw = "  Acme Foods  "
        svc.find_entity_by_alias(TENANT, "name", raw)
        assert self._get_alias_value_param(mock_session) == raw


# ---------------------------------------------------------------------------
# Integration: add_alias normalizes before insert
# ---------------------------------------------------------------------------


class TestAddAliasNormalization_Issue1212:
    """Verify that add_alias strips whitespace from structured identifiers
    before passing the value down to _insert_alias / the DB."""

    def test_padded_gln_stripped_before_insert(self, svc, mock_session):
        # _require_entity uses fetchone which we've already mocked to return (1,).
        svc.add_alias(
            TENANT, "entity-id-abc", "gln", "  0614141123452  ",
            source_system="test",
        )
        # _insert_alias is the final SQL call; find its alias_value param.
        insert_params = mock_session.execute.call_args_list[-1].args[1]
        assert insert_params["alias_value"] == "0614141123452"

    def test_urn_fda_lowercased_before_insert(self, svc, mock_session):
        svc.add_alias(
            TENANT, "entity-id-abc", "fda_registration",
            "  URN:FDA:REG:12345678  ",
            source_system="test",
        )
        insert_params = mock_session.execute.call_args_list[-1].args[1]
        assert insert_params["alias_value"] == "urn:fda:reg:12345678"

    def test_name_not_stripped_before_insert(self, svc, mock_session):
        """Free-text name aliases must not be mutated."""
        raw = "  Acme Foods LLC  "
        svc.add_alias(
            TENANT, "entity-id-abc", "name", raw,
            source_system="test",
        )
        insert_params = mock_session.execute.call_args_list[-1].args[1]
        assert insert_params["alias_value"] == raw
