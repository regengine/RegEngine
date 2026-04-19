"""
Regression coverage for ``app/sandbox/rule_loader.py``.

Target: 100% line coverage of rule_loader.py across:

* ``_build_rules_from_seeds(include_custom=...)`` — builds
  ``RuleDefinition`` objects from ``FSMA_RULE_SEEDS`` and optionally
  appends the four demo custom-business-rule seeds.
* ``_get_applicable_rules(event_type, include_custom=...)`` — filters
  the pre-built rule set by ``applicability_conditions.cte_types``.

These helpers back the sandbox's "try-it-yourself" endpoint, so the
contract is load-bearing for the marketing surface: every demo rule
must attach to the advertised CTE types, every id must be unique, and
the "all" / empty list semantics must keep matching everything.

Tracks GitHub issue #1342 (ingestion test coverage).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.sandbox import rule_loader
from app.sandbox.rule_loader import (
    _DEMO_CUSTOM_RULES,
    _build_rules_from_seeds,
    _get_applicable_rules,
    _SANDBOX_RULES,
    _SANDBOX_RULES_WITH_CUSTOM,
)
from shared.rules_engine import FSMA_RULE_SEEDS, RuleDefinition


# ===========================================================================
# _build_rules_from_seeds — default (no custom)
# ===========================================================================

class TestBuildRulesDefault:
    """Default path: ``include_custom=False`` builds only FSMA seeds."""

    def test_returns_list_of_rule_definitions(self):
        rules = _build_rules_from_seeds()
        assert isinstance(rules, list)
        assert all(isinstance(r, RuleDefinition) for r in rules)

    def test_count_matches_fsma_seeds(self):
        rules = _build_rules_from_seeds()
        assert len(rules) == len(FSMA_RULE_SEEDS)

    def test_rule_ids_are_sequential_and_zero_padded(self):
        """``sandbox-rule-000``, ``sandbox-rule-001``, ... in order."""
        rules = _build_rules_from_seeds()
        for i, rule in enumerate(rules):
            assert rule.rule_id == f"sandbox-rule-{i:03d}"

    def test_rule_ids_are_unique(self):
        rules = _build_rules_from_seeds()
        ids = [r.rule_id for r in rules]
        assert len(set(ids)) == len(ids)

    def test_all_rules_have_version_1(self):
        rules = _build_rules_from_seeds()
        assert all(r.rule_version == 1 for r in rules)

    def test_effective_date_is_today_utc(self):
        """``effective_date`` is computed at build time from UTC clock."""
        rules = _build_rules_from_seeds()
        today_utc = datetime.now(timezone.utc).date()
        assert all(r.effective_date == today_utc for r in rules)

    def test_retired_date_is_none(self):
        rules = _build_rules_from_seeds()
        assert all(r.retired_date is None for r in rules)

    def test_required_fields_copied_from_seeds(self):
        """Mandatory seed fields appear verbatim on the built rule."""
        rules = _build_rules_from_seeds()
        for seed, rule in zip(FSMA_RULE_SEEDS, rules):
            assert rule.title == seed["title"]
            assert rule.severity == seed["severity"]
            assert rule.category == seed["category"]
            assert rule.evaluation_logic == seed["evaluation_logic"]
            assert rule.failure_reason_template == seed["failure_reason_template"]

    def test_optional_fields_use_get_with_safe_defaults(self):
        """Optional fields must use ``.get()`` so missing keys don't throw."""
        rules = _build_rules_from_seeds()
        for seed, rule in zip(FSMA_RULE_SEEDS, rules):
            assert rule.description == seed.get("description")
            assert rule.citation_reference == seed.get("citation_reference")
            assert rule.remediation_suggestion == seed.get("remediation_suggestion")
            assert rule.applicability_conditions == seed.get(
                "applicability_conditions", {}
            )

    def test_include_custom_false_excludes_demo_rules(self):
        """The demo custom rules are only appended when asked for."""
        rules = _build_rules_from_seeds(include_custom=False)
        titles = {r.title for r in rules}
        for demo in _DEMO_CUSTOM_RULES:
            assert demo["title"] not in titles


# ===========================================================================
# _build_rules_from_seeds — with custom rules
# ===========================================================================

class TestBuildRulesWithCustom:
    """``include_custom=True`` appends the four demo business rules."""

    def test_count_is_seeds_plus_four_demos(self):
        rules = _build_rules_from_seeds(include_custom=True)
        assert len(rules) == len(FSMA_RULE_SEEDS) + len(_DEMO_CUSTOM_RULES)

    def test_seed_rules_come_first_preserving_order(self):
        """FSMA seeds ship first, demo custom rules after them."""
        rules = _build_rules_from_seeds(include_custom=True)
        seed_titles = [r["title"] for r in FSMA_RULE_SEEDS]
        for i, title in enumerate(seed_titles):
            assert rules[i].title == title

    def test_custom_rules_appended_at_end(self):
        rules = _build_rules_from_seeds(include_custom=True)
        demo_start = len(FSMA_RULE_SEEDS)
        for i, demo in enumerate(_DEMO_CUSTOM_RULES):
            assert rules[demo_start + i].title == demo["title"]

    def test_custom_rule_ids_continue_sequential_numbering(self):
        """The demo rules get IDs past the FSMA seed count."""
        rules = _build_rules_from_seeds(include_custom=True)
        for i, rule in enumerate(rules):
            assert rule.rule_id == f"sandbox-rule-{i:03d}"

    def test_all_rule_ids_unique_including_custom(self):
        rules = _build_rules_from_seeds(include_custom=True)
        ids = [r.rule_id for r in rules]
        assert len(set(ids)) == len(ids)

    def test_custom_rule_fields_copied_correctly(self):
        rules = _build_rules_from_seeds(include_custom=True)
        demo_start = len(FSMA_RULE_SEEDS)
        for i, demo in enumerate(_DEMO_CUSTOM_RULES):
            built = rules[demo_start + i]
            assert built.severity == demo["severity"]
            assert built.category == demo["category"]
            assert built.evaluation_logic == demo["evaluation_logic"]
            assert built.failure_reason_template == demo["failure_reason_template"]
            assert built.applicability_conditions == demo["applicability_conditions"]


# ===========================================================================
# _DEMO_CUSTOM_RULES — contract checks on the advertised demo set
# ===========================================================================

class TestDemoCustomRulesShape:
    """The demo rules are a marketing surface; assert their core contract."""

    def test_four_demo_rules_defined(self):
        """If someone changes the count, the UI/demo copy likely needs updating."""
        assert len(_DEMO_CUSTOM_RULES) == 4

    @pytest.mark.parametrize("idx, expected_cte", [
        (0, ["cooling", "receiving"]),   # Cold chain
        (1, ["harvesting"]),              # Supplier certification
        (2, ["shipping"]),                # BOL
        (3, ["harvesting"]),              # Field traceability
    ])
    def test_demo_rules_map_to_expected_ctes(self, idx: int, expected_cte):
        """Each demo rule targets the CTE claimed in its description."""
        rule = _DEMO_CUSTOM_RULES[idx]
        assert rule["applicability_conditions"]["cte_types"] == expected_cte

    @pytest.mark.parametrize("rule", _DEMO_CUSTOM_RULES)
    def test_every_demo_rule_has_required_fields(self, rule):
        """Every demo rule must have what ``_build_rules_from_seeds`` reads."""
        required = {
            "title", "description", "severity", "category",
            "applicability_conditions", "citation_reference",
            "evaluation_logic", "failure_reason_template",
            "remediation_suggestion",
        }
        assert required <= set(rule.keys())

    @pytest.mark.parametrize("rule", _DEMO_CUSTOM_RULES)
    def test_every_demo_rule_is_warning_severity(self, rule):
        """Demo rules are non-blocking by design — warnings, not errors."""
        assert rule["severity"] == "warning"

    @pytest.mark.parametrize("rule", _DEMO_CUSTOM_RULES)
    def test_every_demo_rule_category_is_custom_business(self, rule):
        assert rule["category"] == "custom_business_rule"


# ===========================================================================
# Module-level pre-built sets
# ===========================================================================

class TestModuleLevelRulesets:
    """``_SANDBOX_RULES`` and ``_SANDBOX_RULES_WITH_CUSTOM`` cached on import."""

    def test_sandbox_rules_length_matches_fsma_seeds(self):
        assert len(_SANDBOX_RULES) == len(FSMA_RULE_SEEDS)

    def test_sandbox_rules_with_custom_includes_demos(self):
        assert len(_SANDBOX_RULES_WITH_CUSTOM) == (
            len(FSMA_RULE_SEEDS) + len(_DEMO_CUSTOM_RULES)
        )

    def test_sandbox_rules_are_rule_definitions(self):
        assert all(isinstance(r, RuleDefinition) for r in _SANDBOX_RULES)

    def test_sandbox_rules_with_custom_are_rule_definitions(self):
        assert all(
            isinstance(r, RuleDefinition) for r in _SANDBOX_RULES_WITH_CUSTOM
        )


# ===========================================================================
# _get_applicable_rules
# ===========================================================================

class TestGetApplicableRules:
    """Filter rules by ``cte_types`` with fall-through semantics."""

    def test_returns_list(self):
        assert isinstance(_get_applicable_rules("shipping"), list)

    def test_filters_by_event_type(self):
        """A rule scoped to one CTE shouldn't appear for a different one."""
        # Pick a known CTE that the demo rules are not scoped to.
        # ``cooling`` is a demo target, so use ``transformation`` instead —
        # no demo rule claims it.
        rules = _get_applicable_rules("transformation", include_custom=True)
        titles = {r.title for r in rules}
        # Demo rules not for transformation:
        for demo in _DEMO_CUSTOM_RULES:
            if "transformation" not in demo["applicability_conditions"]["cte_types"]:
                assert demo["title"] not in titles

    def test_rule_with_empty_cte_types_matches_everything(self):
        """Empty ``cte_types`` list means "applies to all events"."""
        # Build a synthetic rule set with one empty-list rule and confirm
        # it appears for any event type. We can inspect the existing
        # seeds: if any has empty list, that's evidence enough.
        empty_cte_rules = [
            r for r in _SANDBOX_RULES
            if not r.applicability_conditions.get("cte_types", [])
        ]
        if not empty_cte_rules:
            pytest.skip(
                "No seed rule has empty cte_types — fall-through branch can't "
                "be tested with real seeds alone. See "
                "TestGetApplicableRulesFallthroughBranches for synthetic coverage."
            )
        else:
            for rule in empty_cte_rules:
                assert rule in _get_applicable_rules("harvesting")
                assert rule in _get_applicable_rules("shipping")

    def test_include_custom_false_excludes_demo_rules(self):
        rules = _get_applicable_rules("shipping", include_custom=False)
        demo_titles = {d["title"] for d in _DEMO_CUSTOM_RULES}
        returned_titles = {r.title for r in rules}
        assert not (demo_titles & returned_titles)

    def test_include_custom_true_includes_applicable_demo_rules(self):
        rules = _get_applicable_rules("shipping", include_custom=True)
        titles = {r.title for r in rules}
        assert "Reference Doc: Every Shipment Needs a BOL" in titles

    def test_include_custom_true_excludes_non_applicable_demo_rules(self):
        rules = _get_applicable_rules("shipping", include_custom=True)
        titles = {r.title for r in rules}
        # Cold-chain demo rule scoped to cooling+receiving, not shipping
        assert "Cold Chain: Temperature Must Be Recorded" not in titles

    def test_harvesting_gets_both_harvesting_demo_rules(self):
        """``harvesting`` matches 2 of the 4 demo rules."""
        rules = _get_applicable_rules("harvesting", include_custom=True)
        titles = {r.title for r in rules}
        assert "Supplier Certification: Harvester Must Be Named" in titles
        assert "Field Traceability: Growing Area Required" in titles

    def test_cooling_and_receiving_both_match_cold_chain(self):
        """Multi-CTE demo rule matches each of its listed CTEs."""
        cooling_titles = {r.title for r in _get_applicable_rules("cooling", include_custom=True)}
        receiving_titles = {r.title for r in _get_applicable_rules("receiving", include_custom=True)}
        assert "Cold Chain: Temperature Must Be Recorded" in cooling_titles
        assert "Cold Chain: Temperature Must Be Recorded" in receiving_titles

    def test_unknown_event_type_returns_only_universal_rules(self):
        """An event type no rule targets returns only empty-cte rules."""
        rules = _get_applicable_rules("completely_unknown_cte", include_custom=True)
        for rule in rules:
            cte_types = rule.applicability_conditions.get("cte_types", [])
            assert (not cte_types) or ("all" in cte_types)


class TestGetApplicableRulesFallthroughBranches:
    """Directly exercise the empty-list and "all" fall-through branches.

    The real FSMA seeds may not include both branches; we patch in
    synthetic ``_SANDBOX_RULES`` values to guarantee each code path runs.
    """

    def test_empty_cte_types_list_is_applied_universally(self, monkeypatch):
        universal = RuleDefinition(
            rule_id="test-universal",
            rule_version=1,
            title="Universal Rule",
            description=None,
            severity="info",
            category="test",
            applicability_conditions={"cte_types": []},
            citation_reference=None,
            effective_date=datetime.now(timezone.utc).date(),
            retired_date=None,
            evaluation_logic={"type": "noop"},
            failure_reason_template="always fires",
            remediation_suggestion=None,
        )
        monkeypatch.setattr(rule_loader, "_SANDBOX_RULES", [universal])
        for cte in ("harvesting", "shipping", "cooling", "made_up"):
            assert _get_applicable_rules(cte) == [universal]

    def test_missing_cte_types_key_is_applied_universally(self, monkeypatch):
        """``applicability_conditions`` without ``cte_types`` is the default-to-empty branch."""
        universal = RuleDefinition(
            rule_id="test-no-cte-key",
            rule_version=1,
            title="No CTE Key Rule",
            description=None,
            severity="info",
            category="test",
            applicability_conditions={},
            citation_reference=None,
            effective_date=datetime.now(timezone.utc).date(),
            retired_date=None,
            evaluation_logic={"type": "noop"},
            failure_reason_template="always fires",
            remediation_suggestion=None,
        )
        monkeypatch.setattr(rule_loader, "_SANDBOX_RULES", [universal])
        assert _get_applicable_rules("anything") == [universal]

    def test_all_sentinel_in_cte_types_applies_everywhere(self, monkeypatch):
        all_rule = RuleDefinition(
            rule_id="test-all",
            rule_version=1,
            title="All CTEs Rule",
            description=None,
            severity="info",
            category="test",
            applicability_conditions={"cte_types": ["all"]},
            citation_reference=None,
            effective_date=datetime.now(timezone.utc).date(),
            retired_date=None,
            evaluation_logic={"type": "noop"},
            failure_reason_template="fires for all",
            remediation_suggestion=None,
        )
        monkeypatch.setattr(rule_loader, "_SANDBOX_RULES", [all_rule])
        for cte in ("harvesting", "shipping", "cooling", "made_up"):
            assert _get_applicable_rules(cte) == [all_rule]

    def test_explicit_list_excludes_non_matching_events(self, monkeypatch):
        scoped = RuleDefinition(
            rule_id="test-scoped",
            rule_version=1,
            title="Scoped Rule",
            description=None,
            severity="info",
            category="test",
            applicability_conditions={"cte_types": ["harvesting", "cooling"]},
            citation_reference=None,
            effective_date=datetime.now(timezone.utc).date(),
            retired_date=None,
            evaluation_logic={"type": "noop"},
            failure_reason_template="fires for some",
            remediation_suggestion=None,
        )
        monkeypatch.setattr(rule_loader, "_SANDBOX_RULES", [scoped])
        assert _get_applicable_rules("harvesting") == [scoped]
        assert _get_applicable_rules("cooling") == [scoped]
        assert _get_applicable_rules("shipping") == []
        assert _get_applicable_rules("transformation") == []

    def test_include_custom_uses_with_custom_ruleset(self, monkeypatch):
        """When ``include_custom=True``, ``_SANDBOX_RULES_WITH_CUSTOM`` is consulted."""
        marker_rule = RuleDefinition(
            rule_id="test-marker",
            rule_version=1,
            title="Marker in WITH_CUSTOM",
            description=None,
            severity="info",
            category="test",
            applicability_conditions={"cte_types": ["all"]},
            citation_reference=None,
            effective_date=datetime.now(timezone.utc).date(),
            retired_date=None,
            evaluation_logic={"type": "noop"},
            failure_reason_template="fires",
            remediation_suggestion=None,
        )
        monkeypatch.setattr(rule_loader, "_SANDBOX_RULES", [])
        monkeypatch.setattr(
            rule_loader, "_SANDBOX_RULES_WITH_CUSTOM", [marker_rule]
        )
        # Default path: the empty _SANDBOX_RULES is consulted
        assert _get_applicable_rules("shipping") == []
        # include_custom: the populated _SANDBOX_RULES_WITH_CUSTOM is consulted
        assert _get_applicable_rules("shipping", include_custom=True) == [marker_rule]
