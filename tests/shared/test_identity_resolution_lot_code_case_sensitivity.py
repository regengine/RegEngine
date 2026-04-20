"""Lot-code case-sensitivity tests for identity_resolution (issue #1235).

#1235 calls out three test gaps. This file covers gap #2:

    "Lot codes `ABC-001` and `abc-001` must NOT merge -- lot codes
     are case-sensitive per FSMA 204."

FSMA 204 traceability treats the Traceability Lot Code (TLC) as an
opaque identifier. A downstream recall that matches `ABC-001` against
`abc-001` would either over-recall (wrong product pulled) or under-recall
(affected product missed). Either is a regulatory and safety failure.

This file locks in:

1. `find_entity_by_alias` uses ``=`` equality (SQL collation default)
   NOT ``LOWER()`` / ``ILIKE`` on alias_value.
2. `_resolve_or_register` forwards the reference VERBATIM (no case
   folding, trimming, or normalization prior to SQL parameters).
3. `auto_register_from_event` with a TLC passes it verbatim to the
   resolver.
4. The fuzzy path (find_potential_matches) with ``case_sensitive=True``
   never returns a 1.0 score for inputs that differ in case only
   (would otherwise mis-cluster LOT-abc and LOT-ABC).

Mock-based -- no DB required.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from services.shared.identity_resolution import IdentityResolutionService

TENANT = "tenant-lot-case-1235"


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
# find_entity_by_alias compares alias_value case-sensitively
# ---------------------------------------------------------------------------


class TestFindByAliasIsCaseSensitive_Issue1235:
    def test_sql_uses_equality_not_case_folding(self, svc, mock_session):
        """The SQL must compare alias_value with ``=``, not ``LOWER()``
        or ``ILIKE``. A regression that folds case would fail this."""
        svc.find_entity_by_alias(TENANT, "tlc", "LOT-ABC-001")
        sql_text = str(mock_session.execute.call_args_list[0].args[0])
        normalized = sql_text.replace("\n", " ").lower()

        # Positive: the authoritative equality match is present.
        assert "alias_value = :alias_value" in normalized, (
            "find_entity_by_alias must use '=' for alias_value equality"
        )
        # Negative: the case-folding forms must NOT be present.
        assert "lower(ea.alias_value)" not in normalized, (
            "LOWER() on alias_value silently collides ABC-001 with abc-001"
        )
        assert "ilike" not in normalized, (
            "ILIKE on alias_value silently collides ABC-001 with abc-001"
        )

    def test_uppercase_and_lowercase_flow_through_as_distinct_params(
        self, svc, mock_session,
    ):
        """Call once with ABC-001 and once with abc-001. The params
        dict each execute receives must preserve the caller's casing --
        no call site may lowercase the value before binding."""
        svc.find_entity_by_alias(TENANT, "tlc", "LOT-ABC-001")
        svc.find_entity_by_alias(TENANT, "tlc", "lot-abc-001")

        # Two calls.
        assert len(mock_session.execute.call_args_list) == 2
        first_params = mock_session.execute.call_args_list[0].args[1]
        second_params = mock_session.execute.call_args_list[1].args[1]

        assert first_params["alias_value"] == "LOT-ABC-001"
        assert second_params["alias_value"] == "lot-abc-001"
        # Most important: they are NOT equal after the call passes through.
        assert first_params["alias_value"] != second_params["alias_value"]

    def test_mock_isolation_abc_and_lower_abc_are_different_keys(
        self, mock_session,
    ):
        """End-to-end simulation: if the DB has an entity registered for
        'LOT-ABC-001' and a caller asks for 'lot-abc-001', find returns
        []. Locks in that the service's SQL preserves casing end-to-end."""
        svc = IdentityResolutionService(mock_session)

        registered_rows = [(
            "eid-upper", "lot", "LOT-ABC-001", None, None, None, None,
            "unverified", 1.0, True,
            "alias-upper", "tlc", "LOT-ABC-001", "sys", 1.0,
        )]

        def _case_aware(sql, params):
            result = MagicMock()
            # Simulate Postgres text equality: only exact-case match returns.
            if params.get("alias_value") == "LOT-ABC-001":
                result.fetchall.return_value = registered_rows
            else:
                result.fetchall.return_value = []
            result.fetchone.return_value = (1,)
            return result

        mock_session.execute.side_effect = _case_aware

        upper_hit = svc.find_entity_by_alias(TENANT, "tlc", "LOT-ABC-001")
        lower_hit = svc.find_entity_by_alias(TENANT, "tlc", "lot-abc-001")

        assert len(upper_hit) == 1 and upper_hit[0]["entity_id"] == "eid-upper"
        # The lower-case lookup gets nothing -- we never claim LOT-ABC-001
        # and lot-abc-001 are the same lot.
        assert lower_hit == []


# ---------------------------------------------------------------------------
# _resolve_or_register must forward the reference verbatim
# ---------------------------------------------------------------------------


class TestResolveOrRegisterForwardsVerbatim_Issue1235:
    def test_reference_is_not_case_folded_before_lookup(self, svc, mock_session):
        """When _resolve_or_register takes a mixed-case lot code, the
        exact alias lookup must see the caller's value unchanged."""
        captured = []
        original_find = svc.find_entity_by_alias

        def _spy(tenant_id, alias_type, alias_value):
            captured.append({
                "tenant_id": tenant_id,
                "alias_type": alias_type,
                "alias_value": alias_value,
            })
            return []

        svc.find_entity_by_alias = _spy  # type: ignore[assignment]
        # Short-circuit the register leg so we don't need a full DB.
        svc.register_entity = lambda **kw: {  # type: ignore[assignment]
            "entity_id": "new-eid", "canonical_name": kw["canonical_name"],
            "resolution": "new",
        }
        svc._insert_alias = lambda **kw: "alias-id"  # type: ignore[assignment]

        svc._resolve_or_register(
            tenant_id=TENANT,
            reference="LOT-ABC-001",
            entity_type="lot",
            source_system="test",
            alias_type="tlc",
        )

        # The exact-match lookup must have seen the verbatim reference
        # (no lowercasing, no stripping of surrounding whitespace, no
        # normalization of internal dashes).
        assert any(c["alias_value"] == "LOT-ABC-001" for c in captured), (
            f"Expected verbatim LOT-ABC-001 in alias lookups, saw: {captured}"
        )
        # Also verify it was NOT lower-cased.
        assert not any(c["alias_value"] == "lot-abc-001" for c in captured), (
            "Lot code must not be lower-cased before the alias lookup"
        )

    def test_auto_register_from_event_preserves_tlc_case(
        self, svc, mock_session,
    ):
        """auto_register_from_event must pass traceability_lot_code into
        _resolve_or_register verbatim."""
        captured = []

        def _capture(**kwargs):
            captured.append(kwargs)
            return {
                "entity_id": "lot-eid",
                "canonical_name": kwargs["reference"],
                "resolution": "new",
            }

        svc._resolve_or_register = _capture  # type: ignore[assignment]
        svc._insert_alias = lambda **kw: "alias-id"  # type: ignore[assignment]
        event = {"traceability_lot_code": "LOT-ABC-001"}
        svc.auto_register_from_event(TENANT, event)

        lot_calls = [c for c in captured if c.get("entity_type") == "lot"]
        assert len(lot_calls) == 1
        assert lot_calls[0]["reference"] == "LOT-ABC-001", (
            "TLC must be forwarded verbatim (no case folding)"
        )


# ---------------------------------------------------------------------------
# Fuzzy matcher on case_sensitive=True does not fold case
# ---------------------------------------------------------------------------


class TestFuzzyCaseSensitiveFlag_Issue1235:
    def test_case_sensitive_differs_between_upper_and_lower(
        self, svc, mock_session,
    ):
        """When case_sensitive=True, comparing 'LOT-ABC' to 'LOT-abc' must
        produce a score strictly less than 1.0. A regression that
        silently lower-cases both would score 1.0 and collapse them."""
        mock_session.execute.return_value.fetchall.return_value = [
            ("eid-1", "lot", "LOT-abc", None, None, "unverified", 1.0, "LOT-abc"),
        ]
        results = svc.find_potential_matches(
            TENANT, "LOT-ABC", case_sensitive=True, threshold=0.0,
        )
        assert len(results) == 1
        assert results[0]["confidence"] < 1.0, (
            "case_sensitive=True must not fold case when comparing identifiers"
        )

    def test_case_sensitive_exact_match_scores_perfect(
        self, svc, mock_session,
    ):
        """Sanity check: same casing still scores 1.0 when case_sensitive=True."""
        mock_session.execute.return_value.fetchall.return_value = [
            ("eid-1", "lot", "LOT-ABC", None, None, "unverified", 1.0, "LOT-ABC"),
        ]
        results = svc.find_potential_matches(
            TENANT, "LOT-ABC", case_sensitive=True, threshold=0.0,
        )
        assert len(results) == 1
        assert results[0]["confidence"] == 1.0
