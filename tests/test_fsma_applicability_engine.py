"""
Unit tests for FSMAApplicabilityEngine.

Tests the expanded 23-category FTL list and 6-exemption evaluation logic.
Runs locally without the full Docker stack by stubbing the `shared` modules
that are only needed by other classes in fsma_engine.py (not by
FSMAApplicabilityEngine itself).
"""

import importlib.util
import sys
import types
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Stub `shared.*` before loading fsma_engine.py so the import succeeds
# locally without the full Docker/services stack.
# FSMAApplicabilityEngine itself has zero dependency on these modules.
# ---------------------------------------------------------------------------
def _make_stub(name: str, **attrs):
    mod = types.ModuleType(name)
    mod.__dict__.update(attrs)
    return mod

_shared = _make_stub("shared")
_validators = _make_stub(
    "shared.validators",
    validate_gln=lambda *a, **kw: None,
    validate_fda_reg=lambda *a, **kw: None,
    validate_location_identifiers=lambda *a, **kw: None,
    ValidationSeverity=object,
    BatchValidationResult=object,
)
_fsma_rules = _make_stub(
    "shared.fsma_rules",
    TimeArrowRule=object,
    TraceEvent=object,
)
sys.modules.setdefault("shared", _shared)
sys.modules.setdefault("shared.validators", _validators)
sys.modules.setdefault("shared.fsma_rules", _fsma_rules)

# Now load the engine module directly (bypasses kernel/__init__.py → langchain)
_engine_path = Path(__file__).resolve().parents[1] / "kernel" / "reporting" / "fsma_engine.py"
_spec = importlib.util.spec_from_file_location("fsma_engine_module", _engine_path)
_mod = importlib.util.module_from_spec(_spec)
# Must register in sys.modules BEFORE exec_module so Python 3.9 dataclasses
# can resolve the module's __name__ during class creation.
sys.modules["fsma_engine_module"] = _mod
_spec.loader.exec_module(_mod)
FSMAApplicabilityEngine = _mod.FSMAApplicabilityEngine





@pytest.fixture
def engine():
    return FSMAApplicabilityEngine()


# ============================================================================
# FTL CATEGORY TESTS
# ============================================================================


class TestGetFTLCategories:
    """Tests for get_ftl_categories()."""

    def test_returns_23_categories(self, engine):
        """Engine must expose exactly 23 FTL categories."""
        categories = engine.get_ftl_categories()
        assert len(categories) == 23

    def test_all_categories_have_required_fields(self, engine):
        """Every category must have the required fields."""
        required = {"id", "name", "examples", "covered", "outbreak_frequency", "ctes", "cfr_sections", "kdes"}
        for cat in engine.get_ftl_categories():
            missing = required - set(cat.keys())
            assert not missing, f"Category '{cat.get('id')}' missing fields: {missing}"

    def test_all_categories_are_covered(self, engine):
        """All 23 FTL categories should have covered=True."""
        for cat in engine.get_ftl_categories():
            assert cat["covered"] is True, f"Category '{cat['id']}' should be covered"

    def test_outbreak_frequency_values(self, engine):
        """outbreak_frequency must be HIGH or MODERATE."""
        valid = {"HIGH", "MODERATE"}
        for cat in engine.get_ftl_categories():
            assert cat["outbreak_frequency"] in valid, (
                f"Category '{cat['id']}' has invalid outbreak_frequency: {cat['outbreak_frequency']}"
            )

    def test_high_outbreak_categories(self, engine):
        """Verify known HIGH-outbreak categories are correctly tagged."""
        high_ids = {c["id"] for c in engine.get_ftl_categories() if c["outbreak_frequency"] == "HIGH"}
        assert "leafy-greens-fresh" in high_ids
        assert "leafy-greens-fresh-cut" in high_ids
        assert "tomatoes" in high_ids
        assert "sprouts" in high_ids
        assert "finfish-histamine" in high_ids
        assert "crustaceans" in high_ids
        assert "molluscan-shellfish" in high_ids
        assert "cheese-fresh-soft" in high_ids
        assert "cheese-unpasteurized" in high_ids

    def test_legacy_alias(self, engine):
        """get_applicability_checklist() should return same data as get_ftl_categories()."""
        assert engine.get_applicability_checklist() == engine.get_ftl_categories()

    def test_category_ids_are_unique(self, engine):
        """All category IDs must be unique."""
        ids = [c["id"] for c in engine.get_ftl_categories()]
        assert len(ids) == len(set(ids)), "Duplicate category IDs found"

    def test_eggs_category_present(self, engine):
        """Shell eggs must be present (was in the original minimal engine)."""
        ids = {c["id"] for c in engine.get_ftl_categories()}
        assert "eggs" in ids

    def test_all_seafood_categories_present(self, engine):
        """All 5 seafood categories must be present."""
        ids = {c["id"] for c in engine.get_ftl_categories()}
        assert "finfish-histamine" in ids
        assert "finfish-ciguatoxin" in ids
        assert "finfish-other" in ids
        assert "finfish-smoked" in ids
        assert "crustaceans" in ids
        assert "molluscan-shellfish" in ids

    def test_all_cheese_categories_present(self, engine):
        """All 3 cheese categories must be present."""
        ids = {c["id"] for c in engine.get_ftl_categories()}
        assert "cheese-fresh-soft" in ids
        assert "cheese-soft-ripened" in ids
        assert "cheese-unpasteurized" in ids


# ============================================================================
# APPLICABILITY EVALUATION TESTS
# ============================================================================


class TestEvaluateApplicability:
    """Tests for evaluate_applicability()."""

    def test_empty_selections_not_applicable(self, engine):
        """Empty selection list → not applicable."""
        result = engine.evaluate_applicability([])
        assert result["is_applicable"] is False
        assert result["covered_categories"] == []
        assert result["high_outbreak_count"] == 0

    def test_single_covered_category(self, engine):
        """Selecting one FTL category → applicable."""
        result = engine.evaluate_applicability(["leafy-greens-fresh"])
        assert result["is_applicable"] is True
        assert len(result["covered_categories"]) == 1
        assert result["covered_categories"][0]["id"] == "leafy-greens-fresh"

    def test_multiple_covered_categories(self, engine):
        """Multiple FTL categories → applicable, all returned."""
        result = engine.evaluate_applicability(["eggs", "tomatoes", "crustaceans"])
        assert result["is_applicable"] is True
        assert len(result["covered_categories"]) == 3

    def test_unknown_category_id_not_covered(self, engine):
        """Unknown IDs are returned in not_covered_categories."""
        result = engine.evaluate_applicability(["canned-goods", "bakery"])
        assert result["is_applicable"] is False
        assert set(result["not_covered_categories"]) == {"canned-goods", "bakery"}

    def test_mixed_known_and_unknown(self, engine):
        """Mix of known FTL and unknown IDs → applicable, unknown in not_covered."""
        result = engine.evaluate_applicability(["leafy-greens-fresh", "bakery"])
        assert result["is_applicable"] is True
        assert len(result["covered_categories"]) == 1
        assert "bakery" in result["not_covered_categories"]

    def test_high_outbreak_count(self, engine):
        """high_outbreak_count reflects number of HIGH-frequency categories."""
        result = engine.evaluate_applicability(["leafy-greens-fresh", "eggs", "tomatoes"])
        # leafy-greens-fresh = HIGH, tomatoes = HIGH, eggs = MODERATE
        assert result["high_outbreak_count"] == 2

    def test_reason_when_applicable(self, engine):
        """reason field is set when applicable."""
        result = engine.evaluate_applicability(["eggs"])
        assert "FDA Food Traceability List" in result["reason"]

    def test_reason_when_not_applicable(self, engine):
        """reason field is set when not applicable."""
        result = engine.evaluate_applicability([])
        assert result["reason"] == "No categories selected"

    def test_all_23_categories_applicable(self, engine):
        """Selecting all 23 FTL categories → all covered, none in not_covered."""
        all_ids = [c["id"] for c in engine.get_ftl_categories()]
        result = engine.evaluate_applicability(all_ids)
        assert result["is_applicable"] is True
        assert len(result["covered_categories"]) == 23
        assert result["not_covered_categories"] == []


# ============================================================================
# EXEMPTION EVALUATION TESTS
# ============================================================================


class TestGetExemptionDefinitions:
    """Tests for get_exemption_definitions()."""

    def test_returns_6_exemptions(self, engine):
        """Engine must expose exactly 6 exemption definitions."""
        exemptions = engine.get_exemption_definitions()
        assert len(exemptions) == 6

    def test_all_exemptions_have_required_fields(self, engine):
        """Every exemption must have the required fields."""
        required = {"id", "name", "citation", "exemption_type", "description"}
        for ex in engine.get_exemption_definitions():
            missing = required - set(ex.keys())
            assert not missing, f"Exemption '{ex.get('id')}' missing fields: {missing}"

    def test_all_exemption_ids_present(self, engine):
        """All 6 exemption IDs must be present."""
        ids = {e["id"] for e in engine.get_exemption_definitions()}
        assert "small-producer" in ids
        assert "kill-step" in ids
        assert "direct-to-consumer" in ids
        assert "small-retail" in ids
        assert "rarely-consumed-raw" in ids
        assert "usda-jurisdiction" in ids


class TestEvaluateExemptions:
    """Tests for evaluate_exemptions()."""

    def test_no_answers_not_exempt(self, engine):
        """No answers → NOT_EXEMPT with 6 unanswered."""
        result = engine.evaluate_exemptions({})
        assert result["status"] == "NOT_EXEMPT"
        assert result["is_exempt"] is False
        assert result["active_exemptions"] == []
        assert result["unanswered_count"] == 6

    def test_small_producer_yes_exempt(self, engine):
        """Answering Yes to small-producer → EXEMPT."""
        result = engine.evaluate_exemptions({"small-producer": True})
        assert result["status"] == "EXEMPT"
        assert result["is_exempt"] is True
        assert any(e["id"] == "small-producer" for e in result["active_exemptions"])

    def test_kill_step_yes_exempt(self, engine):
        """Answering Yes to kill-step → EXEMPT."""
        result = engine.evaluate_exemptions({"kill-step": True})
        assert result["status"] == "EXEMPT"
        assert result["is_exempt"] is True

    def test_direct_to_consumer_yes_exempt(self, engine):
        """Answering Yes to direct-to-consumer → EXEMPT."""
        result = engine.evaluate_exemptions({"direct-to-consumer": True})
        assert result["status"] == "EXEMPT"

    def test_small_retail_yes_exempt(self, engine):
        """Answering Yes to small-retail → EXEMPT."""
        result = engine.evaluate_exemptions({"small-retail": True})
        assert result["status"] == "EXEMPT"

    def test_rarely_consumed_raw_yes_exempt(self, engine):
        """Answering Yes to rarely-consumed-raw → EXEMPT."""
        result = engine.evaluate_exemptions({"rarely-consumed-raw": True})
        assert result["status"] == "EXEMPT"

    def test_usda_jurisdiction_yes_exempt(self, engine):
        """Answering Yes to usda-jurisdiction → EXEMPT."""
        result = engine.evaluate_exemptions({"usda-jurisdiction": True})
        assert result["status"] == "EXEMPT"

    def test_all_no_not_exempt(self, engine):
        """All answers No → NOT_EXEMPT, 0 unanswered."""
        answers = {
            "small-producer": False,
            "kill-step": False,
            "direct-to-consumer": False,
            "small-retail": False,
            "rarely-consumed-raw": False,
            "usda-jurisdiction": False,
        }
        result = engine.evaluate_exemptions(answers)
        assert result["status"] == "NOT_EXEMPT"
        assert result["is_exempt"] is False
        assert result["unanswered_count"] == 0

    def test_multiple_exemptions_all_qualify(self, engine):
        """Multiple Yes answers → all qualifying exemptions returned."""
        answers = {"small-producer": True, "kill-step": True}
        result = engine.evaluate_exemptions(answers)
        assert result["status"] == "EXEMPT"
        assert len(result["active_exemptions"]) == 2

    def test_partial_answers_unanswered_count(self, engine):
        """Partial answers → correct unanswered_count."""
        answers = {"small-producer": False, "kill-step": False}
        result = engine.evaluate_exemptions(answers)
        assert result["unanswered_count"] == 4  # 6 total - 2 answered

    def test_unknown_exemption_id_ignored(self, engine):
        """Unknown exemption IDs in answers are silently ignored."""
        result = engine.evaluate_exemptions({"unknown-exemption": True})
        assert result["status"] == "NOT_EXEMPT"
        assert result["active_exemptions"] == []
