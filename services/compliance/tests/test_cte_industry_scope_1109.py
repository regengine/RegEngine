"""Contract tests for per-industry CTE scoping in fsma_rules.json — #1109.

FSMA 204 defines different CTE sets for different food categories:

* RACs (raw agricultural commodities, e.g. produce): ``HARVESTING``,
  ``COOLING``, ``INITIAL_PACKING`` apply — plus the common
  ``SHIPPING`` / ``RECEIVING`` / ``TRANSFORMATION``.
* Seafood obtained from a fishing vessel: ``FIRST_LAND_BASED_RECEIVING``
  replaces ``INITIAL_PACKING``. Aquaculture uses ``HARVESTING``.
* Dairy / shell eggs / deli: no HARVESTING / COOLING — only the
  general chain-of-custody CTEs.

The flat ``allowed_cte_types`` list alone accepts ``COOLING`` for dairy
or ``FIRST_LAND_BASED_RECEIVING`` for produce, which produces
non-conformant submissions. These tests lock down the per-industry
allowlist so the JSON config cannot drift back to the permissive shape.

Paired with the flat ``allowed_cte_types`` contract in
``test_fsma_rules_contract_1223.py`` — the flat list is the **union**
of every per-industry list; the per-industry map is the **scope**.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

_RULES_PATH = Path(__file__).parent.parent / "app" / "fsma_rules.json"


@pytest.fixture(scope="module")
def rules() -> dict:
    with _RULES_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def by_industry(rules: dict) -> dict:
    return rules["validation"]["cte_types_by_industry"]


@pytest.fixture(scope="module")
def industry_ids(rules: dict) -> set[str]:
    return {i["id"] for i in rules["industries"]}


class TestCTEScopingBlockExists:
    def test_cte_types_by_industry_present(self, rules):
        """The per-industry allowlist block must exist — it's the
        primary fix for #1109 ("COOLING accepted everywhere").
        """
        val = rules["validation"]
        assert "cte_types_by_industry" in val, (
            "cte_types_by_industry missing — flat allowed_cte_types "
            "alone accepts COOLING/FIRST_LAND_BASED_RECEIVING for "
            "industries where they do not apply (FSMA 204 §1.1305)."
        )

    def test_mutually_exclusive_ctes_present(self, rules):
        val = rules["validation"]
        assert "mutually_exclusive_ctes" in val
        pairs = val["mutually_exclusive_ctes"]["pairs"]
        assert ["INITIAL_PACKING", "FIRST_LAND_BASED_RECEIVING"] in pairs, (
            "INITIAL_PACKING and FIRST_LAND_BASED_RECEIVING must be "
            "marked mutually exclusive — per FDA, a given lot is "
            "land-packed (RAC) or vessel-received (seafood), never both."
        )


class TestIndustryKeysMatchRegistry:
    def test_every_declared_industry_has_a_cte_scope(self, rules, by_industry, industry_ids):
        """Every industry in the registry must have a per-industry CTE
        allowlist. An unlisted industry would silently fall back to
        the permissive flat list."""
        scoped = {k for k in by_industry if not k.startswith("_")}
        missing = industry_ids - scoped
        assert not missing, (
            f"cte_types_by_industry missing industries: {missing}. "
            "Every fsma_rules.json industry must declare its CTE scope."
        )

    def test_no_orphan_industry_keys_in_scope_map(self, rules, by_industry, industry_ids):
        scoped = {k for k in by_industry if not k.startswith("_")}
        extra = scoped - industry_ids
        assert not extra, (
            f"cte_types_by_industry has keys with no matching industry: "
            f"{extra}. Orphan keys are unreachable and drift-prone."
        )


class TestCoolingRestrictedToRACProduce:
    def test_cooling_in_fresh_produce(self, by_industry):
        assert "COOLING" in by_industry["fresh-produce"]

    @pytest.mark.parametrize(
        "industry",
        ["seafood", "dairy", "deli-prepared", "shell-eggs"],
    )
    def test_cooling_not_in_non_produce_industries(self, by_industry, industry):
        """FSMA 204 §1.1305: COOLING is defined for RACs (produce)
        only. Listing it for dairy/seafood/eggs is the #1109 bug."""
        assert "COOLING" not in by_industry[industry], (
            f"COOLING must not be in {industry}'s CTE scope — FDA "
            "restricts this CTE to Raw Agricultural Commodities "
            "(produce). Non-conformant submission risk (#1109)."
        )


class TestFirstLandBasedReceivingScopedToSeafood:
    def test_first_land_based_receiving_in_seafood(self, by_industry):
        assert "FIRST_LAND_BASED_RECEIVING" in by_industry["seafood"]

    @pytest.mark.parametrize(
        "industry",
        ["fresh-produce", "dairy", "deli-prepared", "shell-eggs"],
    )
    def test_first_land_based_receiving_not_elsewhere(self, by_industry, industry):
        """Per FDA, FIRST_LAND_BASED_RECEIVING applies only when
        food is obtained from a fishing vessel."""
        assert "FIRST_LAND_BASED_RECEIVING" not in by_industry[industry], (
            f"FIRST_LAND_BASED_RECEIVING must not be in {industry}'s "
            "scope — it describes fishing-vessel handoffs (#1109)."
        )


class TestCommonCTEsCoverEveryIndustry:
    @pytest.mark.parametrize("cte", ["SHIPPING", "RECEIVING", "TRANSFORMATION"])
    def test_common_cte_in_all_industries(self, rules, by_industry, industry_ids, cte):
        """SHIPPING, RECEIVING, TRANSFORMATION apply across every
        FTL food category. A missing entry would silently disable
        chain-of-custody validation for that industry."""
        for industry in industry_ids:
            assert cte in by_industry[industry], (
                f"{cte} must appear in every industry scope; missing "
                f"from {industry}"
            )


class TestFlatListIsUnionOfPerIndustry:
    def test_flat_allowed_is_exactly_the_union(self, rules, by_industry):
        """``allowed_cte_types`` (the flat list consumed by legacy
        readers) must equal the union of every per-industry list.
        Divergence means either: (a) the flat list accepts a CTE no
        industry actually uses, or (b) an industry list references a
        CTE that the flat validator rejects. Both are drift."""
        flat = set(rules["validation"]["allowed_cte_types"])
        union: set[str] = set()
        for key, ctes in by_industry.items():
            if key.startswith("_"):
                continue
            union.update(ctes)
        assert flat == union, (
            f"allowed_cte_types and cte_types_by_industry have diverged. "
            f"Flat-only: {flat - union}. Scoped-only: {union - flat}."
        )


class TestMutualExclusionPairsValid:
    def test_every_pair_member_is_in_flat_list(self, rules):
        """Mutual-exclusion pairs must reference real CTEs — a pair
        naming a CTE absent from allowed_cte_types is unreachable."""
        flat = set(rules["validation"]["allowed_cte_types"])
        pairs = rules["validation"]["mutually_exclusive_ctes"]["pairs"]
        for pair in pairs:
            for cte in pair:
                assert cte in flat, (
                    f"mutually_exclusive_ctes references unknown CTE "
                    f"{cte!r} (pair={pair}); add to allowed_cte_types "
                    f"or drop the pair."
                )

    def test_initial_packing_and_first_land_pair_present(self, rules):
        pairs = rules["validation"]["mutually_exclusive_ctes"]["pairs"]
        # Use a sorted-pair form to tolerate order flips if someone ever
        # edits the file.
        pair_sets = [frozenset(p) for p in pairs]
        expected = frozenset({"INITIAL_PACKING", "FIRST_LAND_BASED_RECEIVING"})
        assert expected in pair_sets, (
            "INITIAL_PACKING / FIRST_LAND_BASED_RECEIVING mutual "
            "exclusion missing — this is the core #1109 invariant."
        )
