"""FSMA 204 Applicability & Exemption Engine.

Migrated from kernel.reporting.fsma_engine as part of meta-epic #2223
(retire kernel/). Closes #2225.

This module hosts the `FSMAApplicabilityEngine` consumed by the FSMA wizard
endpoints in `services/graph/app/routers/fsma/wizard.py`. The sibling
`FSMA204ComplianceEngine` (scoring/report assembly) remains in
`kernel/reporting/fsma_engine.py` because it is consumed by the kernel
reporting service's own `main.py` and tests; it will migrate separately.
"""

from __future__ import annotations

from typing import Any, Dict, List


class FSMAApplicabilityEngine:
    """
    Engine for FSMA 204 applicability and exemption evaluation.

    Covers all 23 FTL categories per 21 CFR Part 1 Subpart S and all 6
    exemption pathways per 21 CFR §1.1305.

    CFR Section Reference:
      §1.1325 = Harvesting AND Cooling
      §1.1330 = Initial Packing (RAC, not from fishing vessel)
      §1.1335 = First Land-Based Receiving (from fishing vessel)
      §1.1340 = Shipping
      §1.1345 = Receiving
      §1.1350 = Transformation
    """

    # -------------------------------------------------------------------------
    # Authoritative FTL category list — 23 categories
    # Verified against 21 CFR Part 1 Subpart S
    # -------------------------------------------------------------------------
    FTL_CATEGORIES: List[Dict[str, Any]] = [
        {
            "id": "leafy-greens-fresh",
            "name": "Leafy Greens (fresh, intact)",
            "examples": "Whole leaf lettuce, spinach bunches, kale, arugula, chard, collard greens",
            "exclusions": "Does not include whole head cabbages or banana/grape/tree leaves.",
            "covered": True,
            "outbreak_frequency": "HIGH",
            "ctes": ["Harvesting", "Cooling", "Initial Packing", "Shipping", "Receiving"],
            "cfr_sections": "§1.1325, §1.1330, §1.1340, §1.1345",
            "kdes": [
                "Traceability Lot Code (TLC)",
                "Location Identifier (GLN)",
                "Date/Time",
                "Quantity & UOM",
                "Product Description",
                "Reference Document Type & Number",
                "TLC Source Location or Reference",
                "Cooling Location Identifier",
                "Field Identification",
            ],
        },
        {
            "id": "leafy-greens-fresh-cut",
            "name": "Leafy Greens (fresh-cut)",
            "examples": "Bagged salad mix, spring mix, pre-washed spinach, chopped romaine, salad kits",
            "exclusions": "Does not include dried or frozen leafy greens.",
            "covered": True,
            "outbreak_frequency": "HIGH",
            "ctes": ["Receiving", "Transformation", "Shipping"],
            "cfr_sections": "§1.1340, §1.1345, §1.1350",
            "kdes": [
                "Traceability Lot Code (TLC)",
                "Location Identifier (GLN)",
                "Date/Time",
                "Quantity & UOM",
                "Product Description",
                "Reference Document Type & Number",
                "Input TLCs",
                "New TLC Assigned",
            ],
        },
        {
            "id": "tomatoes",
            "name": "Tomatoes",
            "examples": "Fresh tomatoes (not canned or dried)",
            "exclusions": None,
            "covered": True,
            "outbreak_frequency": "HIGH",
            "ctes": ["Harvesting", "Cooling", "Initial Packing", "Shipping", "Receiving", "Transformation"],
            "cfr_sections": "§1.1325, §1.1330, §1.1340, §1.1345, §1.1350",
            "kdes": [
                "Traceability Lot Code (TLC)",
                "Location Identifier (GLN)",
                "Date/Time",
                "Quantity & UOM",
                "Product Description",
                "Reference Document Type & Number",
                "TLC Source Location or Reference",
                "Cooling Location Identifier",
                "Field Identification",
            ],
        },
        {
            "id": "peppers",
            "name": "Peppers",
            "examples": "Bell peppers, jalapeños, chili peppers (fresh)",
            "exclusions": None,
            "covered": True,
            "outbreak_frequency": "MODERATE",
            "ctes": ["Harvesting", "Cooling", "Initial Packing", "Shipping", "Receiving", "Transformation"],
            "cfr_sections": "§1.1325, §1.1330, §1.1340, §1.1345, §1.1350",
            "kdes": [
                "Traceability Lot Code (TLC)",
                "Location Identifier (GLN)",
                "Date/Time",
                "Quantity & UOM",
                "Product Description",
                "Reference Document Type & Number",
                "TLC Source Location or Reference",
                "Cooling Location Identifier",
                "Field Identification",
            ],
        },
        {
            "id": "cucumbers",
            "name": "Cucumbers",
            "examples": "Fresh cucumbers",
            "exclusions": None,
            "covered": True,
            "outbreak_frequency": "MODERATE",
            "ctes": ["Harvesting", "Cooling", "Initial Packing", "Shipping", "Receiving", "Transformation"],
            "cfr_sections": "§1.1325, §1.1330, §1.1340, §1.1345, §1.1350",
            "kdes": [
                "Traceability Lot Code (TLC)",
                "Location Identifier (GLN)",
                "Date/Time",
                "Quantity & UOM",
                "Product Description",
                "Reference Document Type & Number",
                "TLC Source Location or Reference",
                "Cooling Location Identifier",
                "Field Identification",
            ],
        },
        {
            "id": "herbs",
            "name": "Fresh Herbs",
            "examples": "Cilantro, parsley, basil (fresh cut)",
            "exclusions": "Herbs in 21 CFR 112.2(a)(1), such as dill, are exempt under §1.1305(e).",
            "covered": True,
            "outbreak_frequency": "MODERATE",
            "ctes": ["Harvesting", "Cooling", "Initial Packing", "Shipping", "Receiving", "Transformation"],
            "cfr_sections": "§1.1325, §1.1330, §1.1340, §1.1345, §1.1350",
            "kdes": [
                "Traceability Lot Code (TLC)",
                "Location Identifier (GLN)",
                "Date/Time",
                "Quantity & UOM",
                "Product Description",
                "Reference Document Type & Number",
                "TLC Source Location or Reference",
                "Cooling Location Identifier",
                "Field Identification",
            ],
        },
        {
            "id": "melons",
            "name": "Melons",
            "examples": "Cantaloupe, honeydew, watermelon",
            "exclusions": None,
            "covered": True,
            "outbreak_frequency": "MODERATE",
            "ctes": ["Harvesting", "Cooling", "Initial Packing", "Shipping", "Receiving", "Transformation"],
            "cfr_sections": "§1.1325, §1.1330, §1.1340, §1.1345, §1.1350",
            "kdes": [
                "Traceability Lot Code (TLC)",
                "Location Identifier (GLN)",
                "Date/Time",
                "Quantity & UOM",
                "Product Description",
                "Reference Document Type & Number",
                "TLC Source Location or Reference",
                "Cooling Location Identifier",
                "Field Identification",
            ],
        },
        {
            "id": "tropical-fruits",
            "name": "Tropical Tree Fruits",
            "examples": "Mangoes, papayas, mamey, guava",
            "exclusions": "Does not include bananas, pineapple, dates, coconut, avocado, or citrus.",
            "covered": True,
            "outbreak_frequency": "MODERATE",
            "ctes": ["Harvesting", "Initial Packing", "Shipping", "Receiving", "Transformation"],
            "cfr_sections": "§1.1325, §1.1330, §1.1340, §1.1345, §1.1350",
            "kdes": [
                "Traceability Lot Code (TLC)",
                "Location Identifier (GLN)",
                "Date/Time",
                "Quantity & UOM",
                "Product Description",
                "Reference Document Type & Number",
                "TLC Source Location or Reference",
                "Field Identification",
            ],
        },
        {
            "id": "sprouts",
            "name": "Sprouts",
            "examples": "Alfalfa, bean, broccoli sprouts",
            "exclusions": None,
            "covered": True,
            "outbreak_frequency": "HIGH",
            "ctes": ["Harvesting", "Initial Packing", "Shipping", "Receiving", "Transformation"],
            "cfr_sections": "§1.1325, §1.1330, §1.1340, §1.1345, §1.1350",
            "kdes": [
                "Traceability Lot Code (TLC)",
                "Location Identifier (GLN)",
                "Date/Time",
                "Quantity & UOM",
                "Product Description",
                "Reference Document Type & Number",
                "Seed Source",
                "Growing Location",
            ],
        },
        {
            "id": "fresh-cut-fruits",
            "name": "Fresh-Cut Fruits",
            "examples": "Pre-cut fruit mixes, fruit cups",
            "exclusions": None,
            "covered": True,
            "outbreak_frequency": "MODERATE",
            "ctes": ["Receiving", "Transformation", "Shipping"],
            "cfr_sections": "§1.1340, §1.1345, §1.1350",
            "kdes": [
                "Traceability Lot Code (TLC)",
                "Location Identifier (GLN)",
                "Date/Time",
                "Quantity & UOM",
                "Product Description",
                "Reference Document Type & Number",
                "Input TLCs",
                "New TLC Assigned",
            ],
        },
        {
            "id": "fresh-cut-vegetables",
            "name": "Fresh-Cut Vegetables (non-leafy)",
            "examples": "Veggie trays, pre-cut carrots, celery sticks, broccoli florets",
            "exclusions": None,
            "covered": True,
            "outbreak_frequency": "MODERATE",
            "ctes": ["Receiving", "Transformation", "Shipping"],
            "cfr_sections": "§1.1340, §1.1345, §1.1350",
            "kdes": [
                "Traceability Lot Code (TLC)",
                "Location Identifier (GLN)",
                "Date/Time",
                "Quantity & UOM",
                "Product Description",
                "Reference Document Type & Number",
                "Input TLCs",
                "New TLC Assigned",
            ],
        },
        {
            "id": "deli-salads",
            "name": "Ready-to-Eat Deli Salads",
            "examples": "Egg salad, seafood salad, pasta salad, potato salad",
            "exclusions": None,
            "covered": True,
            "outbreak_frequency": "MODERATE",
            "ctes": ["Receiving", "Transformation", "Shipping"],
            "cfr_sections": "§1.1340, §1.1345, §1.1350",
            "kdes": [
                "Traceability Lot Code (TLC)",
                "Location Identifier (GLN)",
                "Date/Time",
                "Quantity & UOM",
                "Product Description",
                "Reference Document Type & Number",
                "Input TLCs",
                "New TLC Assigned",
            ],
        },
        {
            "id": "finfish-histamine",
            "name": "Finfish — Scombrotoxin/Histamine-Forming",
            "examples": "Tuna, mackerel, mahi-mahi, bluefish, amberjack, bonito",
            "exclusions": "Catfish (Siluriformes) are USDA-regulated and excluded per §1.1305(g).",
            "covered": True,
            "outbreak_frequency": "HIGH",
            "ctes": ["First Land-Based Receiving", "Shipping", "Receiving", "Transformation"],
            "cfr_sections": "§1.1335, §1.1340, §1.1345, §1.1350",
            "kdes": [
                "Traceability Lot Code (TLC)",
                "Location Identifier (GLN)",
                "Date/Time",
                "Quantity & UOM",
                "Product Description",
                "Reference Document Type & Number",
                "Vessel Name",
                "Harvest Area",
                "Landing Port",
            ],
        },
        {
            "id": "finfish-ciguatoxin",
            "name": "Finfish — Ciguatoxin-Associated",
            "examples": "Barracuda, grouper, snapper, moray eel (tropical reef species)",
            "exclusions": "Catfish (Siluriformes) are USDA-regulated and excluded per §1.1305(g).",
            "covered": True,
            "outbreak_frequency": "MODERATE",
            "ctes": ["First Land-Based Receiving", "Shipping", "Receiving", "Transformation"],
            "cfr_sections": "§1.1335, §1.1340, §1.1345, §1.1350",
            "kdes": [
                "Traceability Lot Code (TLC)",
                "Location Identifier (GLN)",
                "Date/Time",
                "Quantity & UOM",
                "Product Description",
                "Reference Document Type & Number",
                "Vessel Name",
                "Harvest Area",
                "Landing Port",
            ],
        },
        {
            "id": "finfish-other",
            "name": "Finfish — Other (fresh/frozen/previously frozen)",
            "examples": "Salmon, cod, halibut, tilapia, trout, bass, swordfish",
            "exclusions": "Catfish (Siluriformes) are USDA-regulated and excluded per §1.1305(g).",
            "covered": True,
            "outbreak_frequency": "HIGH",
            "ctes": ["First Land-Based Receiving", "Shipping", "Receiving", "Transformation"],
            "cfr_sections": "§1.1335, §1.1340, §1.1345, §1.1350",
            "kdes": [
                "Traceability Lot Code (TLC)",
                "Location Identifier (GLN)",
                "Date/Time",
                "Quantity & UOM",
                "Product Description",
                "Reference Document Type & Number",
                "Vessel Name",
                "Harvest Area",
                "Landing Port",
            ],
        },
        {
            "id": "finfish-smoked",
            "name": "Smoked Finfish",
            "examples": "Smoked salmon, lox, kippered herring, smoked trout, smoked whitefish",
            "exclusions": "Catfish (Siluriformes) are USDA-regulated and excluded per §1.1305(g).",
            "covered": True,
            "outbreak_frequency": "MODERATE",
            "ctes": ["Receiving", "Transformation", "Shipping"],
            "cfr_sections": "§1.1340, §1.1345, §1.1350",
            "kdes": [
                "Traceability Lot Code (TLC)",
                "Location Identifier (GLN)",
                "Date/Time",
                "Quantity & UOM",
                "Product Description",
                "Reference Document Type & Number",
                "Input TLCs",
                "New TLC Assigned",
            ],
        },
        {
            "id": "crustaceans",
            "name": "Crustaceans",
            "examples": "Shrimp, crab, lobster, crawfish",
            "exclusions": None,
            "covered": True,
            "outbreak_frequency": "HIGH",
            "ctes": ["First Land-Based Receiving", "Shipping", "Receiving", "Transformation"],
            "cfr_sections": "§1.1335, §1.1340, §1.1345, §1.1350",
            "kdes": [
                "Traceability Lot Code (TLC)",
                "Location Identifier (GLN)",
                "Date/Time",
                "Quantity & UOM",
                "Product Description",
                "Reference Document Type & Number",
                "Harvest Area",
                "Vessel or Container ID",
            ],
        },
        {
            "id": "molluscan-shellfish",
            "name": "Molluscan Shellfish (bivalves)",
            "examples": "Oysters, clams, mussels, scallops",
            "exclusions": "Except when product consists entirely of shucked adductor muscle. Raw bivalves under NSSP may be exempt per §1.1305(f).",
            "covered": True,
            "outbreak_frequency": "HIGH",
            "ctes": ["First Land-Based Receiving", "Shipping", "Receiving", "Transformation"],
            "cfr_sections": "§1.1335, §1.1340, §1.1345, §1.1350",
            "kdes": [
                "Traceability Lot Code (TLC)",
                "Location Identifier (GLN)",
                "Date/Time",
                "Quantity & UOM",
                "Product Description",
                "Reference Document Type & Number",
                "Harvest Area",
                "Harvest Tag",
                "NSSP Dealer Certificate",
            ],
        },
        {
            "id": "eggs",
            "name": "Shell Eggs",
            "examples": "Whole shell eggs (chicken, duck)",
            "exclusions": "Farms with fewer than 3,000 laying hens are exempt per §1.1305(a)(2).",
            "covered": True,
            "outbreak_frequency": "MODERATE",
            "ctes": ["Shipping", "Receiving"],
            "cfr_sections": "§1.1340, §1.1345",
            "kdes": [
                "Traceability Lot Code (TLC)",
                "Location Identifier (GLN)",
                "Date/Time",
                "Quantity & UOM",
                "Product Description",
                "Reference Document Type & Number",
                "TLC Source Location or Reference",
                "Farm/Flock Identifier",
            ],
        },
        {
            "id": "nut-butters",
            "name": "Nut Butters",
            "examples": "Peanut butter, almond butter",
            "exclusions": None,
            "covered": True,
            "outbreak_frequency": "MODERATE",
            "ctes": ["Receiving", "Transformation", "Shipping"],
            "cfr_sections": "§1.1340, §1.1345, §1.1350",
            "kdes": [
                "Traceability Lot Code (TLC)",
                "Location Identifier (GLN)",
                "Date/Time",
                "Quantity & UOM",
                "Product Description",
                "Reference Document Type & Number",
                "Input TLCs",
                "New TLC Assigned",
            ],
        },
        {
            "id": "cheese-fresh-soft",
            "name": "Fresh Soft Cheese",
            "examples": "Queso fresco, ricotta, mascarpone, cream cheese, panela",
            "exclusions": "Hard cheeses per 21 CFR 133.150 (e.g., cheddar, parmesan, aged cotija) are excluded. Cottage cheese is exempt (finalized April 2026; listed on IMS List, §1.1305(d)).",
            "covered": True,
            "outbreak_frequency": "HIGH",
            "ctes": ["Receiving", "Transformation", "Shipping"],
            "cfr_sections": "§1.1340, §1.1345, §1.1350",
            "kdes": [
                "Traceability Lot Code (TLC)",
                "Location Identifier (GLN)",
                "Date/Time",
                "Quantity & UOM",
                "Product Description",
                "Reference Document Type & Number",
                "Input TLCs",
                "New TLC Assigned",
            ],
        },
        {
            "id": "cheese-soft-ripened",
            "name": "Soft Ripened & Semi-Soft Cheese",
            "examples": "Brie, camembert, monterey jack, muenster, gouda, havarti, oaxaca, feta",
            "exclusions": "Hard cheeses per 21 CFR 133.150 are excluded. Semi-soft includes cheeses with moisture content >39%.",
            "covered": True,
            "outbreak_frequency": "MODERATE",
            "ctes": ["Receiving", "Transformation", "Shipping"],
            "cfr_sections": "§1.1340, §1.1345, §1.1350",
            "kdes": [
                "Traceability Lot Code (TLC)",
                "Location Identifier (GLN)",
                "Date/Time",
                "Quantity & UOM",
                "Product Description",
                "Reference Document Type & Number",
                "Input TLCs",
                "New TLC Assigned",
            ],
        },
        {
            "id": "cheese-unpasteurized",
            "name": "Cheese Made from Unpasteurized Milk (non-hard)",
            "examples": "Raw-milk brie, raw-milk feta, raw-milk camembert, artisanal raw-milk soft cheeses",
            "exclusions": "Hard cheeses aged 60+ days per 21 CFR 133.150 are excluded even if made from unpasteurized milk.",
            "covered": True,
            "outbreak_frequency": "HIGH",
            "ctes": ["Receiving", "Transformation", "Shipping"],
            "cfr_sections": "§1.1340, §1.1345, §1.1350",
            "kdes": [
                "Traceability Lot Code (TLC)",
                "Location Identifier (GLN)",
                "Date/Time",
                "Quantity & UOM",
                "Product Description",
                "Reference Document Type & Number",
                "Input TLCs",
                "New TLC Assigned",
            ],
        },
    ]

    # -------------------------------------------------------------------------
    # Exemption definitions — 6 pathways per 21 CFR §1.1305
    # -------------------------------------------------------------------------
    EXEMPTION_DEFINITIONS: List[Dict[str, Any]] = [
        {
            "id": "small-producer",
            "name": "Small Producer / Very Small Business",
            "citation": "21 CFR §1.1305(a)",
            "exemption_type": "FULL",
            "description": (
                "Produce farms or RAC producers averaging less than $25,000 in annual food sales "
                "over the past 3 years. Shell egg producers with fewer than 3,000 laying hens also qualify. "
                "Threshold is inflation-adjusted using 2020 as baseline."
            ),
        },
        {
            "id": "kill-step",
            "name": "Kill Step Applied",
            "citation": "21 CFR §1.1305(d)",
            "exemption_type": "FULL",
            "description": (
                "Your facility applies a kill step (cooking, pasteurization) that eliminates pathogens "
                "before the food reaches consumers. You must still keep receiving records (§1.1345) "
                "and a record of the kill step application."
            ),
        },
        {
            "id": "direct-to-consumer",
            "name": "Direct-to-Consumer Sales Only",
            "citation": "21 CFR §1.1305(b)",
            "exemption_type": "FULL",
            "description": (
                "You sell ONLY directly to consumers (farm stand, farmers market, CSA). "
                "Applies to food produced on the farm and sold/donated directly to consumers "
                "by the owner, operator, or agent."
            ),
        },
        {
            "id": "small-retail",
            "name": "Small Retail / Restaurant",
            "citation": "21 CFR §1.1305(i)",
            "exemption_type": "FULL",
            "description": (
                "Retail food establishment or restaurant averaging less than $250,000 in annual food "
                "sales over the past 3 years. Threshold is inflation-adjusted using 2020 as baseline. "
                "Most small restaurants and independent grocers qualify."
            ),
        },
        {
            "id": "rarely-consumed-raw",
            "name": "Rarely Consumed Raw",
            "citation": "21 CFR §1.1305(e)",
            "exemption_type": "FULL",
            "description": (
                "You ONLY handle produce on the FDA 'Rarely Consumed Raw' list "
                "(asparagus, potatoes, beets, etc.) as defined in 21 CFR 112.2(a)(1). "
                "These items are excluded from the FTL entirely."
            ),
        },
        {
            "id": "usda-jurisdiction",
            "name": "Exclusive USDA Jurisdiction",
            "citation": "21 CFR §1.1305(g)",
            "exemption_type": "FULL",
            "description": (
                "Your product is under exclusive USDA jurisdiction (Federal Meat Inspection Act, "
                "Poultry Products Inspection Act, or Egg Products Inspection Act). "
                "Includes Siluriformes (catfish family)."
            ),
        },
    ]

    # Set of exemption IDs for O(1) lookup
    _FULL_EXEMPT_IDS: set = {
        "small-producer",
        "kill-step",
        "direct-to-consumer",
        "small-retail",
        "rarely-consumed-raw",
        "usda-jurisdiction",
    }

    def __init__(self) -> None:
        # Build lookup dict for fast access
        self._category_map: Dict[str, Dict[str, Any]] = {c["id"]: c for c in self.FTL_CATEGORIES}
        self._exemption_map: Dict[str, Dict[str, Any]] = {e["id"]: e for e in self.EXEMPTION_DEFINITIONS}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_ftl_categories(self) -> List[Dict[str, Any]]:
        """Return the full list of 23 FTL categories with CTE/KDE metadata."""
        return self.FTL_CATEGORIES

    def get_exemption_definitions(self) -> List[Dict[str, Any]]:
        """Return all 6 exemption definitions."""
        return self.EXEMPTION_DEFINITIONS

    # Legacy alias kept for backward compatibility
    def get_applicability_checklist(self) -> List[Dict[str, Any]]:
        """Return list of FTL categories for selection (legacy alias)."""
        return self.get_ftl_categories()

    def evaluate_applicability(self, selections: List[str]) -> Dict[str, Any]:
        """
        Check if any selected category IDs are on the FTL.

        Args:
            selections: List of FTL category IDs (e.g. ["leafy-greens-fresh", "eggs"])

        Returns:
            dict with keys:
              - is_applicable (bool)
              - covered_categories (list of matched category dicts)
              - not_covered_categories (list of unrecognised IDs)
              - high_outbreak_count (int)
              - reason (str)
        """
        if not selections:
            return {
                "is_applicable": False,
                "covered_categories": [],
                "not_covered_categories": [],
                "high_outbreak_count": 0,
                "reason": "No categories selected",
            }

        covered = [self._category_map[sid] for sid in selections if sid in self._category_map]
        not_covered = [sid for sid in selections if sid not in self._category_map]
        high_outbreak = [c for c in covered if c.get("outbreak_frequency") == "HIGH"]

        is_applicable = len(covered) > 0
        return {
            "is_applicable": is_applicable,
            "covered_categories": covered,
            "not_covered_categories": not_covered,
            "high_outbreak_count": len(high_outbreak),
            "reason": ("Handles items on the FDA Food Traceability List" if is_applicable else "No FTL items handled"),
        }

    def evaluate_exemptions(self, answers: Dict[str, bool]) -> Dict[str, Any]:
        """
        Evaluate FSMA 204 exemption status based on wizard answers.

        Args:
            answers: Dict mapping exemption IDs to boolean answers.
                     e.g. {"small-producer": False, "kill-step": True, ...}

        Returns:
            dict with keys:
              - status ("EXEMPT" | "UNKNOWN" | "NOT_EXEMPT")
              - is_exempt (bool)
              - active_exemptions (list of qualifying exemption dicts)
              - unanswered_count (int)
        """
        active: List[Dict[str, Any]] = []
        unanswered = 0

        for exemption_id, definition in self._exemption_map.items():
            answer = answers.get(exemption_id)
            if answer is None:
                unanswered += 1
            elif answer is True:
                active.append(definition)

        is_exempt = len(active) > 0
        if is_exempt:
            status = "EXEMPT"
        elif unanswered > 0:
            status = "UNKNOWN"
        else:
            status = "NOT_EXEMPT"

        return {
            "status": status,
            "is_exempt": is_exempt,
            "active_exemptions": active,
            "unanswered_count": unanswered,
        }
