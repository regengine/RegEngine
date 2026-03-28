"""
Unit tests for the Identity Resolution Service — business logic only, no database.

Tests cover:
    - Entity registration with validation
    - Alias creation and type validation
    - Exact alias matching (find_entity_by_alias)
    - Confidence scoring via fuzzy matching (find_potential_matches)
    - Merge operations (alias re-pointing, source deactivation)
    - Split operations (merge reversal)
    - Ambiguity detection and review queue
    - Auto-register from event
"""

from __future__ import annotations

from datetime import datetime, timezone
from difflib import SequenceMatcher
from unittest.mock import MagicMock, call, patch

import pytest

from services.shared.identity_resolution import (
    AMBIGUOUS_THRESHOLD_HIGH,
    AMBIGUOUS_THRESHOLD_LOW,
    VALID_ALIAS_TYPES,
    VALID_ENTITY_TYPES,
    VALID_REVIEW_STATUSES,
    IdentityResolutionService,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TENANT = "tenant-001"


@pytest.fixture
def mock_session():
    return MagicMock()


@pytest.fixture
def svc(mock_session):
    return IdentityResolutionService(mock_session)


# ---------------------------------------------------------------------------
# 1. Entity Registration
# ---------------------------------------------------------------------------

class TestRegisterEntity:
    def test_valid_entity_type_succeeds(self, svc, mock_session):
        mock_session.execute.return_value = MagicMock()
        result = svc.register_entity(
            TENANT, "facility", "Acme Cold Storage",
            gln="0012345000015",
        )
        assert result["entity_type"] == "facility"
        assert result["canonical_name"] == "Acme Cold Storage"
        assert result["gln"] == "0012345000015"
        assert result["verification_status"] == "unverified"
        assert result["is_active"] is True
        assert "entity_id" in result

    def test_invalid_entity_type_raises(self, svc):
        with pytest.raises(ValueError, match="Invalid entity_type"):
            svc.register_entity(TENANT, "vehicle", "Truck #5")

    def test_all_valid_entity_types(self, svc, mock_session):
        mock_session.execute.return_value = MagicMock()
        for etype in VALID_ENTITY_TYPES:
            result = svc.register_entity(TENANT, etype, f"Test {etype}")
            assert result["entity_type"] == etype

    def test_registers_gln_as_alias(self, svc, mock_session):
        """When gln is provided, it should be registered as an alias."""
        mock_session.execute.return_value = MagicMock()
        svc.register_entity(
            TENANT, "facility", "Acme", gln="123", gtin="456",
        )
        # Should have: 1 entity INSERT + 1 name alias + 1 gln alias + 1 gtin alias = 4 executes
        assert mock_session.execute.call_count >= 4

    def test_confidence_score_default(self, svc, mock_session):
        mock_session.execute.return_value = MagicMock()
        result = svc.register_entity(TENANT, "facility", "Test")
        assert result["confidence_score"] == 1.0

    def test_custom_confidence_score(self, svc, mock_session):
        mock_session.execute.return_value = MagicMock()
        result = svc.register_entity(
            TENANT, "facility", "Test", confidence_score=0.75,
        )
        assert result["confidence_score"] == 0.75


# ---------------------------------------------------------------------------
# 2. Add Alias — validation
# ---------------------------------------------------------------------------

class TestAddAlias:
    def test_invalid_alias_type_raises(self, svc):
        with pytest.raises(ValueError, match="Invalid alias_type"):
            svc.add_alias(TENANT, "ent-1", "twitter_handle", "acme", "csv")

    def test_valid_alias_types(self):
        expected_types = {
            "name", "gln", "gtin", "fda_registration", "internal_code",
            "duns", "tlc_prefix", "address_variant", "abbreviation", "trade_name",
        }
        assert VALID_ALIAS_TYPES == expected_types

    def test_add_alias_verifies_entity_exists(self, svc, mock_session):
        # _require_entity raises if entity not found
        mock_session.execute.return_value.fetchone.return_value = None
        with pytest.raises(ValueError, match="not found"):
            svc.add_alias(TENANT, "nonexistent", "name", "Foo", "csv")

    def test_add_alias_returns_metadata(self, svc, mock_session):
        # _require_entity succeeds
        mock_session.execute.return_value.fetchone.return_value = (1,)
        result = svc.add_alias(
            TENANT, "ent-1", "name", "Acme LLC", "csv_upload",
            confidence=0.9,
        )
        assert result["alias_type"] == "name"
        assert result["alias_value"] == "Acme LLC"
        assert result["confidence"] == 0.9
        assert "alias_id" in result


# ---------------------------------------------------------------------------
# 3. Find Entity by Alias (exact match)
# ---------------------------------------------------------------------------

class TestFindEntityByAlias:
    def test_returns_matching_entities(self, svc, mock_session):
        mock_session.execute.return_value.fetchall.return_value = [
            # Simulating a row tuple
            ("eid-1", "facility", "Acme Cold Storage", "GLN1", None, None, None,
             "unverified", 1.0, True, "aid-1", "name", "Acme Cold Storage", "csv", 1.0),
        ]
        results = svc.find_entity_by_alias(TENANT, "name", "Acme Cold Storage")
        assert len(results) == 1
        assert results[0]["entity_id"] == "eid-1"
        assert results[0]["canonical_name"] == "Acme Cold Storage"
        assert results[0]["matched_alias"]["alias_type"] == "name"

    def test_returns_empty_list_for_no_match(self, svc, mock_session):
        mock_session.execute.return_value.fetchall.return_value = []
        results = svc.find_entity_by_alias(TENANT, "name", "Nonexistent Corp")
        assert results == []


# ---------------------------------------------------------------------------
# 4. Confidence Scoring — Fuzzy Matching
# ---------------------------------------------------------------------------

class TestFindPotentialMatches:
    def test_high_similarity_returned(self, svc, mock_session):
        mock_session.execute.return_value.fetchall.return_value = [
            # (entity_id, entity_type, canonical_name, gln, gtin,
            #  verification_status, confidence_score, alias_value)
            ("eid-1", "facility", "Acme Cold Storage", None, None,
             "unverified", 1.0, "Acme Cold Storage"),
        ]
        results = svc.find_potential_matches(TENANT, "Acme Cold Storag")
        assert len(results) == 1
        assert results[0]["confidence"] > 0.9

    def test_low_similarity_filtered_out(self, svc, mock_session):
        mock_session.execute.return_value.fetchall.return_value = [
            ("eid-1", "facility", "Zebra Inc", None, None,
             "unverified", 1.0, "Zebra Inc"),
        ]
        results = svc.find_potential_matches(TENANT, "Acme Cold Storage")
        assert len(results) == 0

    def test_results_sorted_by_confidence_descending(self, svc, mock_session):
        mock_session.execute.return_value.fetchall.return_value = [
            ("eid-1", "facility", "Acme Warehouse", None, None,
             "unverified", 1.0, "Acme Warehouse"),
            ("eid-2", "facility", "Acme Cold Storage", None, None,
             "unverified", 1.0, "Acme Cold Storage"),
        ]
        results = svc.find_potential_matches(TENANT, "Acme Cold Storage")
        if len(results) > 1:
            assert results[0]["confidence"] >= results[1]["confidence"]

    def test_custom_threshold(self, svc, mock_session):
        mock_session.execute.return_value.fetchall.return_value = [
            ("eid-1", "facility", "Acme Storage", None, None,
             "unverified", 1.0, "Acme Storage"),
        ]
        # With very high threshold, should filter out moderate matches
        results = svc.find_potential_matches(TENANT, "Acme Storag", threshold=0.99)
        assert len(results) == 0

    def test_limit_respected(self, svc, mock_session):
        rows = [
            (f"eid-{i}", "facility", f"Acme Branch {i}", None, None,
             "unverified", 1.0, f"Acme Branch {i}")
            for i in range(10)
        ]
        mock_session.execute.return_value.fetchall.return_value = rows
        results = svc.find_potential_matches(
            TENANT, "Acme Branch", threshold=0.5, limit=3,
        )
        assert len(results) <= 3

    def test_invalid_entity_type_raises(self, svc):
        with pytest.raises(ValueError, match="Invalid entity_type"):
            svc.find_potential_matches(TENANT, "test", entity_type="spaceship")

    def test_deduplicates_by_entity_keeping_best_score(self, svc, mock_session):
        """If the same entity has multiple aliases, only the best score is kept."""
        mock_session.execute.return_value.fetchall.return_value = [
            ("eid-1", "facility", "Acme", None, None, "unverified", 1.0, "Acme Corp"),
            ("eid-1", "facility", "Acme", None, None, "unverified", 1.0, "Acme Corporation"),
        ]
        results = svc.find_potential_matches(TENANT, "Acme Corp", threshold=0.5)
        # Should have only one entry for eid-1
        entity_ids = [r["entity_id"] for r in results]
        assert entity_ids.count("eid-1") == 1


# ---------------------------------------------------------------------------
# 5. Confidence Score Calculation (SequenceMatcher)
# ---------------------------------------------------------------------------

class TestConfidenceScoring:
    """Verify the SequenceMatcher-based confidence scoring behavior."""

    def test_identical_strings_score_1(self):
        ratio = SequenceMatcher(None, "acme cold storage", "acme cold storage").ratio()
        assert ratio == 1.0

    def test_completely_different_strings_score_low(self):
        ratio = SequenceMatcher(None, "abc", "xyz").ratio()
        assert ratio < 0.2

    def test_slight_typo_scores_high(self):
        ratio = SequenceMatcher(None, "acme cold storag", "acme cold storage").ratio()
        assert ratio > 0.9

    def test_case_insensitive_comparison_in_service(self, svc, mock_session):
        """The service lowercases search_name and alias_value."""
        mock_session.execute.return_value.fetchall.return_value = [
            ("eid-1", "facility", "ACME", None, None, "unverified", 1.0, "ACME COLD STORAGE"),
        ]
        results = svc.find_potential_matches(TENANT, "acme cold storage")
        assert len(results) == 1
        assert results[0]["confidence"] == 1.0


# ---------------------------------------------------------------------------
# 6. Merge Operations
# ---------------------------------------------------------------------------

class TestMergeEntities:
    def test_merge_self_raises(self, svc):
        with pytest.raises(ValueError, match="Cannot merge an entity with itself"):
            svc.merge_entities(TENANT, "eid-1", "eid-1")

    def test_merge_nonexistent_source_raises(self, svc, mock_session):
        # _require_entity will raise for missing source
        mock_session.execute.return_value.fetchone.return_value = None
        with pytest.raises(ValueError, match="not found"):
            svc.merge_entities(TENANT, "nonexistent", "eid-2")

    def test_merge_returns_audit_record(self, svc, mock_session):
        # All _require_entity calls succeed
        mock_session.execute.return_value.fetchone.return_value = (1,)
        result = svc.merge_entities(
            TENANT, "eid-1", "eid-2",
            reason="Duplicate entry",
            performed_by="admin",
        )
        assert result["action"] == "merge"
        assert result["source_entity_ids"] == ["eid-1"]
        assert result["target_entity_id"] == "eid-2"
        assert result["reason"] == "Duplicate entry"
        assert result["performed_by"] == "admin"
        assert "merge_id" in result
        assert "performed_at" in result

    def test_merge_executes_alias_repointing(self, svc, mock_session):
        mock_session.execute.return_value.fetchone.return_value = (1,)
        svc.merge_entities(TENANT, "eid-1", "eid-2")
        # Should execute multiple SQL statements:
        # _require_entity x2, UPDATE aliases, DELETE remaining aliases,
        # UPDATE deactivate source, INSERT merge_history, UPDATE review_queue
        assert mock_session.execute.call_count >= 5


# ---------------------------------------------------------------------------
# 7. Split Operations (merge reversal)
# ---------------------------------------------------------------------------

class TestSplitEntity:
    def test_split_nonexistent_merge_raises(self, svc, mock_session):
        mock_session.execute.return_value.fetchone.return_value = None
        with pytest.raises(ValueError, match="not found"):
            svc.split_entity(TENANT, "bad-merge-id")

    def test_split_already_reversed_raises(self, svc, mock_session):
        # (merge_id, source_entity_ids, target_entity_id, action, is_reversed)
        mock_session.execute.return_value.fetchone.return_value = (
            "m1", ["eid-1"], "eid-2", "merge", True,
        )
        with pytest.raises(ValueError, match="already been reversed"):
            svc.split_entity(TENANT, "m1")

    def test_split_non_merge_action_raises(self, svc, mock_session):
        mock_session.execute.return_value.fetchone.return_value = (
            "m1", ["eid-1"], "eid-2", "split", False,
        )
        with pytest.raises(ValueError, match="not a merge action"):
            svc.split_entity(TENANT, "m1")

    def test_split_returns_record(self, svc, mock_session):
        # First call: fetch merge record
        fetch_merge = MagicMock()
        fetch_merge.fetchone.return_value = (
            "m1", ["eid-source"], "eid-target", "merge", False,
        )
        # Subsequent calls: various updates and lookups
        update_mock = MagicMock()
        # For the canonical_name lookup
        name_mock = MagicMock()
        name_mock.fetchone.return_value = ("Source Entity Name",)

        call_idx = [0]
        def side_effect(*args, **kwargs):
            call_idx[0] += 1
            if call_idx[0] == 1:
                return fetch_merge
            if call_idx[0] == 3:
                # canonical_name lookup
                return name_mock
            return update_mock

        mock_session.execute.side_effect = side_effect

        result = svc.split_entity(TENANT, "m1", performed_by="admin")
        assert result["original_merge_id"] == "m1"
        assert "eid-source" in [str(s) for s in result["source_entity_ids"]]
        assert result["target_entity_id"] == "eid-target"
        assert "split_id" in result


# ---------------------------------------------------------------------------
# 8. Ambiguity Detection — Review Queue
# ---------------------------------------------------------------------------

class TestQueueForReview:
    def test_invalid_match_type_raises(self, svc):
        with pytest.raises(ValueError, match="Invalid match_type"):
            svc.queue_for_review(TENANT, "a", "b", "magic", 0.8)

    def test_valid_match_types(self, svc, mock_session):
        # No existing record
        mock_session.execute.return_value.fetchone.return_value = None
        for mt in ("exact", "likely", "ambiguous", "unresolved"):
            result = svc.queue_for_review(TENANT, "a", "b", mt, 0.85)
            assert result["status"] == "pending"

    def test_idempotent_on_existing(self, svc, mock_session):
        # Existing record found
        mock_session.execute.return_value.fetchone.return_value = (
            "review-existing", "pending", 0.85,
        )
        result = svc.queue_for_review(TENANT, "a", "b", "ambiguous", 0.85)
        assert result["idempotent"] is True
        assert result["review_id"] == "review-existing"

    def test_normalizes_entity_order(self, svc, mock_session):
        """(A,B) and (B,A) should produce the same normalized pair."""
        mock_session.execute.return_value.fetchone.return_value = None
        result1 = svc.queue_for_review(TENANT, "eid-2", "eid-1", "ambiguous", 0.85)
        # The entity_a_id should be the smaller of the two
        assert result1["entity_a_id"] == "eid-1"
        assert result1["entity_b_id"] == "eid-2"

    def test_new_review_not_idempotent(self, svc, mock_session):
        mock_session.execute.return_value.fetchone.return_value = None
        result = svc.queue_for_review(TENANT, "a", "b", "ambiguous", 0.85)
        assert result["idempotent"] is False


# ---------------------------------------------------------------------------
# 9. Resolve Review
# ---------------------------------------------------------------------------

class TestResolveReview:
    def test_invalid_resolution_raises(self, svc):
        with pytest.raises(ValueError, match="Invalid resolution"):
            svc.resolve_review(TENANT, "r1", "reject")

    def test_valid_resolutions(self):
        assert "confirmed_match" in VALID_REVIEW_STATUSES
        assert "confirmed_distinct" in VALID_REVIEW_STATUSES
        assert "deferred" in VALID_REVIEW_STATUSES

    def test_review_not_found_raises(self, svc, mock_session):
        mock_session.execute.return_value.fetchone.return_value = None
        with pytest.raises(ValueError, match="not found"):
            svc.resolve_review(TENANT, "bad-id", "confirmed_match")

    def test_already_resolved_raises(self, svc, mock_session):
        mock_session.execute.return_value.fetchone.return_value = (
            "r1", "eid-a", "eid-b", "confirmed_match",
        )
        with pytest.raises(ValueError, match="already resolved"):
            svc.resolve_review(TENANT, "r1", "confirmed_distinct")


# ---------------------------------------------------------------------------
# 10. Ambiguity Thresholds
# ---------------------------------------------------------------------------

class TestAmbiguityThresholds:
    def test_threshold_constants(self):
        assert AMBIGUOUS_THRESHOLD_LOW == 0.60
        assert AMBIGUOUS_THRESHOLD_HIGH == 0.90

    def test_high_similarity_should_flag_for_review(self):
        """>=85% similarity should block submission per check_blocking_defects."""
        similarity = SequenceMatcher(
            None, "acme cold storage", "acme cold storag"
        ).ratio()
        # This pair is >85% similar
        assert similarity >= 0.85

    def test_moderate_similarity_below_review_threshold(self):
        """Sufficiently different names should NOT trigger review."""
        similarity = SequenceMatcher(
            None, "acme cold storage", "beta warehousing"
        ).ratio()
        assert similarity < 0.60


# ---------------------------------------------------------------------------
# 11. Entity Type Validation
# ---------------------------------------------------------------------------

class TestEntityTypeValidation:
    def test_valid_types_are_frozenset(self):
        assert isinstance(VALID_ENTITY_TYPES, frozenset)

    def test_expected_types_present(self):
        for t in ("firm", "facility", "product", "lot", "trading_relationship"):
            assert t in VALID_ENTITY_TYPES
