"""Checklist prose must not name a CTE the industry cannot use — #2851.

``fsma_rules.json`` carries two independent descriptions of which Critical
Tracking Events apply to an industry:

* ``validation.cte_types_by_industry`` — the machine-readable allowlist that
  ``POST /validate`` enforces (locked down by #1109).
* ``checklists[].requirements[].description`` — the human-readable guidance
  served verbatim to customers by ``GET /checklists``.

Nothing kept them in agreement. The dairy checklist's ``da-5`` instructed
customers to "Record TLC, pack date, package size, and production line at the
PACKING CTE" while dairy's allowlist is ``SHIPPING`` / ``RECEIVING`` /
``TRANSFORMATION`` — and ``PACKING`` is not a CTE name at all in any industry
(the canonical spelling for the packing event is ``INITIAL_PACKING``, which
FSMA 204 reserves for raw agricultural commodities, 21 CFR §1.1320). A
customer who followed the checklist built an event the same service rejects
with ``INVALID_CTE_TYPE``.

Two rules close the gap:

* **Rule A** — every canonical CTE name appearing in checklist prose must be
  in that industry's allowlist. Catches "real CTE, wrong industry".
* **Rule B** — every ``<TOKEN> CTE`` phrase must name a canonical CTE.
  Catches invented spellings like ``PACKING`` that Rule A cannot see.

Both rules need a reliable checklist-to-industry join, which is itself
asserted here: ``checklists[].industry`` holds the industry *display name*
(``"Dairy"``), not its id (``"dairy"``), so the join runs through
``industries[].name``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

_RULES_PATH = Path(__file__).parent.parent / "app" / "fsma_rules.json"

# Uppercase tokens that appear in checklist prose but are not CTE names.
_NON_CTE_TOKENS = frozenset(
    {
        "TLC",
        "TLCS",
        "KDE",
        "KDES",
        "CTE",
        "CTES",
        "FSMA",
        "FDA",
        "UOM",
        "GTIN",
        "GS1",
        "EPCIS",
        "RAC",
        "RACS",
    }
)

# "... at the PACKING CTE" / "... at the SHIPPING CTE"
_CTE_PHRASE = re.compile(r"\b([A-Z][A-Z_]{2,})\s+CTEs?\b")


@pytest.fixture(scope="module")
def rules() -> dict:
    with _RULES_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def canonical_ctes(rules: dict) -> set[str]:
    return set(rules["validation"]["allowed_cte_types"])


@pytest.fixture(scope="module")
def name_to_id(rules: dict) -> dict[str, str]:
    """Industry display name -> industry id."""
    return {i["name"]: i["id"] for i in rules["industries"]}


def _requirements(checklist: dict) -> list[dict]:
    return checklist.get("requirements", [])


def _prose(requirement: dict) -> str:
    return f"{requirement.get('title', '')} {requirement.get('description', '')}"


class TestChecklistIndustryJoin:
    """Rules A and B are vacuous unless every checklist resolves to an
    industry, so the join is asserted before it is relied upon."""

    def test_every_checklist_resolves_to_an_industry(self, rules, name_to_id):
        unresolved = [
            (c["id"], c["industry"])
            for c in rules["checklists"]
            if c["industry"] not in name_to_id
        ]
        assert not unresolved, (
            f"checklists[].industry values with no matching industries[].name: "
            f"{unresolved}. Known names: {sorted(name_to_id)}. Without this join "
            f"the per-industry CTE checks below silently pass on every checklist."
        )

    def test_industry_display_names_are_unique(self, rules):
        names = [i["name"] for i in rules["industries"]]
        assert len(names) == len(set(names)), (
            f"industries[].name is not unique ({names}) — the checklist join "
            f"would be ambiguous."
        )


class TestChecklistCTEsAreInIndustryScope:
    """Rule A: a canonical CTE named in checklist prose must be one the
    industry is actually allowed to submit."""

    def test_named_ctes_are_allowed_for_the_industry(
        self, rules, canonical_ctes, name_to_id
    ):
        by_industry = rules["validation"]["cte_types_by_industry"]
        violations = []
        for checklist in rules["checklists"]:
            industry_id = name_to_id.get(checklist["industry"])
            allowed = set(by_industry.get(industry_id, []))
            if not allowed:
                continue
            for req in _requirements(checklist):
                prose = _prose(req)
                for cte in canonical_ctes:
                    if re.search(rf"\b{re.escape(cte)}\b", prose) and cte not in allowed:
                        violations.append(
                            f"{checklist['id']}/{req['id']} names {cte}, "
                            f"but {industry_id} allows {sorted(allowed)}"
                        )
        assert not violations, (
            "Checklist guidance names a CTE the industry cannot submit. "
            "GET /checklists serves this text verbatim; POST /validate would "
            "reject the resulting event with INVALID_CTE_TYPE (#2851):\n  "
            + "\n  ".join(violations)
        )


class TestChecklistCTESpellingIsCanonical:
    """Rule B: an ``X CTE`` phrase must name a real CTE. This is the rule
    that catches #2851's ``PACKING`` — an invented spelling is invisible to
    Rule A because it matches no canonical name."""

    def test_cte_phrases_name_canonical_ctes(self, rules, canonical_ctes):
        violations = []
        for checklist in rules["checklists"]:
            for req in _requirements(checklist):
                for token in _CTE_PHRASE.findall(_prose(req)):
                    if token in _NON_CTE_TOKENS:
                        continue
                    if token not in canonical_ctes:
                        violations.append(
                            f"{checklist['id']}/{req['id']} says '{token} CTE'"
                        )
        assert not violations, (
            f"Checklist prose names a CTE that is not in "
            f"validation.allowed_cte_types {sorted(canonical_ctes)}. Customers "
            f"follow this text literally (#2851):\n  " + "\n  ".join(violations)
        )

    def test_rule_b_detects_an_invented_spelling(self, canonical_ctes):
        """Guard the guard: the phrase matcher must actually fire on the
        #2851 shape, so a future refactor cannot quietly neuter it."""
        found = _CTE_PHRASE.findall(
            "Record TLC, pack date, package size, and production line at the "
            "PACKING CTE."
        )
        assert "PACKING" in found, f"phrase matcher missed the #2851 shape: {found}"
        assert "PACKING" not in canonical_ctes
        assert "TLC" in _NON_CTE_TOKENS, "TLC must not be reported as a CTE"
