"""Regression test for #1102 — every CTE type must have seed rules
covering its FDA-mandated KDEs.

Original bug: only RECEIVING had explicit per-CTE KDE enforcement
rules; the other six CTE flows relied on universal rules (TLC present,
quantity, product description) that don't cover the CTE-specific KDEs
required by 21 CFR 1.1320-1.1350.

This test parametrizes across all 7 FSMA CTE types and asserts that
``FSMA_RULE_SEEDS`` includes at least the FDA-cited KDE rules for
each. The assertion is on *count per CTE type* (as a floor) so new
rules are always welcome; the test only fails when a previously-
covered CTE regresses.

Pure-Python; no DB.
"""

from __future__ import annotations

from collections import Counter

import pytest

from services.shared.rules.seeds import FSMA_RULE_SEEDS


# Floor counts per CTE type. Each number is the **minimum** ``kde_presence``
# seed rules the CTE must have, acting as a regression guard against
# the original #1102 pattern where every non-RECEIVING CTE had zero.
#
# Floors match current post-fix coverage — new seeds are welcome but
# these numbers must not regress. Rules in other categories
# (``source_reference``, ``temporal_order``, ``mass_balance``, etc.)
# are not counted; they exist but #1102 was specifically about
# per-CTE KDE presence.
_CTE_KDE_FLOORS: dict[str, int] = {
    # 21 CFR §1.1327 — Harvest Date, Farm Location, Commodity+Variety
    "harvesting": 3,
    # §1.1325 — Cooling Date, Cooling Location. Temperature thresholds are
    # operational checks, not FSMA 204 KDE presence blockers.
    "cooling": 2,
    # §1.1335 — Packing Date, Harvester Business Name, Packing Location
    # (new), Harvest Location Ref (new)
    "initial_packing": 4,
    # §1.1325 — Landing Date, Entry Point (new), Source Vessel (new)
    "first_land_based_receiving": 3,
    # §1.1340 — Ship-From, Ship-To, Ship Date (Reference Document and
    # TLC Source Reference live in other categories)
    "shipping": 3,
    # §1.1345 — Receive Date, Receiving Location, Immediate Previous
    # Source, TLC Source Reference
    "receiving": 4,
    # §1.1350 — Transformation Date (Input TLCs Required lives in the
    # relational category, not kde_presence)
    "transformation": 1,
}


def _count_kde_rules_for_cte(cte_type: str) -> int:
    """Count seed rules applying to ``cte_type`` with category ``kde_presence``."""
    return sum(
        1
        for seed in FSMA_RULE_SEEDS
        if seed.get("category") == "kde_presence"
        and cte_type in (
            seed.get("applicability_conditions") or {}
        ).get("cte_types", [])
    )


@pytest.mark.parametrize(
    "cte_type,floor",
    sorted(_CTE_KDE_FLOORS.items()),
)
def test_every_cte_has_floor_kde_rules(cte_type: str, floor: int):
    """Each of the 7 FSMA CTE types must have at least ``floor`` seed
    rules in the ``kde_presence`` category scoped to it — #1102."""
    count = _count_kde_rules_for_cte(cte_type)
    assert count >= floor, (
        f"{cte_type} has only {count} per-CTE kde_presence seed rules, "
        f"expected at least {floor} per FDA citations. Gap closes #1102 "
        f"for non-RECEIVING CTEs."
    )


def test_no_cte_has_zero_per_cte_rules():
    """Defense-in-depth check: every CTE in the floors table has at
    least ONE rule (catches the original #1102 regression shape)."""
    for cte_type in _CTE_KDE_FLOORS:
        count = _count_kde_rules_for_cte(cte_type)
        assert count > 0, (
            f"{cte_type} has zero per-CTE kde_presence seed rules — "
            "original #1102 regression would return to this state"
        )


def test_citation_references_are_21_cfr_and_not_receiving_only():
    """Sanity check: the new non-receiving seed rules should cite
    §1.1325 / §1.1335 / §1.1340 / §1.1350, not receiving-only citations."""
    non_receiving_citations: Counter[str] = Counter()
    for seed in FSMA_RULE_SEEDS:
        if seed.get("category") != "kde_presence":
            continue
        cte_types = (
            seed.get("applicability_conditions") or {}
        ).get("cte_types", [])
        if "receiving" in cte_types and len(cte_types) == 1:
            continue
        cite = seed.get("citation_reference", "")
        # Match the section token only; whitespace formatting varies.
        for section in (
            "\u00a71.1325",  # first_land_based_receiving
            "\u00a71.1327",  # harvesting
            "\u00a71.1335",  # initial_packing
            "\u00a71.1340",  # shipping
            "\u00a71.1350",  # transformation
        ):
            if section in cite:
                non_receiving_citations[section] += 1
                break
    # We expect each of the six non-receiving sections to show up at
    # least once in the seed rules.
    missing = [
        s for s in (
            "\u00a71.1325",
            "\u00a71.1327",
            "\u00a71.1335",
            "\u00a71.1340",
            "\u00a71.1350",
        )
        if non_receiving_citations[s] == 0
    ]
    assert not missing, (
        f"Seed rules cite no 21 CFR sections for: {missing}. Non-RECEIVING "
        "CTEs need at least one seed rule each per #1102."
    )
