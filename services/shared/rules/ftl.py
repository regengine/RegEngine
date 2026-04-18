"""
FTL (Food Traceability List) scoping helpers for the rules engine.

Per FSMA 204 (21 CFR §1.1310), only foods on the FDA Food Traceability List
are subject to the regulatory recordkeeping and traceability requirements.
Non-FTL foods (bread, canned goods, most produce outside the FTL) must NOT
receive a "compliant" stamp from a regulation that does not apply to them —
see #1346 / #1105.

This module centralizes:
  - The authoritative FTL category list (mirrors services/ingestion/app/product_catalog.py)
  - is_ftl_food(event_data) — whether an event's product is on the FTL
  - get_ftl_category(event_data) — the matching FTL category name (or None)
  - event_has_ftl_hint(event_data) — whether the caller supplied ANY FTL
    classification signal. If not, the safest behavior is to "skip with
    reason" rather than assume FTL.

Lookup precedence (first match wins):
  1. event_data["kdes"]["ftl_covered"] (bool, explicit)
  2. event_data["ftl_covered"] (bool, explicit top-level)
  3. event_data["product"]["ftl_covered"] (bool)
  4. event_data["kdes"]["ftl_category"] (string, exact match against catalog)
  5. event_data["ftl_category"] (string)
  6. event_data["product"]["category"] (string, matched against FTL_CATEGORIES)
  7. event_data["product_category"] (string)
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from shared.rules.utils import get_nested_value

# Mirror of services/ingestion/app/product_catalog.FTL_CATEGORIES.
# Kept in-sync but locally owned so the rules engine does not depend on the
# ingestion service module.
FTL_CATEGORIES = frozenset(
    c.lower()
    for c in [
        "Leafy Greens", "Herbs", "Fresh-Cut Fruits", "Fresh-Cut Vegetables",
        "Finfish", "Crustaceans", "Molluscan Shellfish", "Smoked Finfish",
        "Soft Cheeses", "Shell Eggs", "Nut Butters", "Ready-to-Eat Deli Salads",
        "Fresh Tomatoes", "Fresh Peppers", "Fresh Cucumbers", "Fresh Sprouts",
        "Tropical Tree Fruits", "Fresh Melons",
    ]
)


def _normalize(value: Any) -> Optional[str]:
    """Lower-case + strip for case-insensitive category matching."""
    if not isinstance(value, str):
        return None
    norm = value.strip().lower()
    return norm or None


def get_ftl_category(event_data: Dict[str, Any]) -> Optional[str]:
    """Return the matching FTL category name for the event (or None).

    Category strings are matched case-insensitively against FTL_CATEGORIES.
    Returns the canonical category (lower-case) if matched, else None.
    """
    for path in (
        "kdes.ftl_category",
        "ftl_category",
        "product.category",
        "product_category",
    ):
        norm = _normalize(get_nested_value(event_data, path))
        if norm and norm in FTL_CATEGORIES:
            return norm
    return None


def event_has_ftl_hint(event_data: Dict[str, Any]) -> bool:
    """True iff the event carries any FTL classification signal.

    Used to distinguish "caller says the food is not FTL" (we know it is
    out of scope) from "caller provided no FTL info" (we cannot tell,
    surface the ambiguity rather than silently green-stamp).
    """
    for path in (
        "kdes.ftl_covered",
        "ftl_covered",
        "product.ftl_covered",
        "kdes.ftl_category",
        "ftl_category",
        "product.category",
        "product_category",
    ):
        if get_nested_value(event_data, path) is not None:
            return True
    return False


def is_ftl_food(event_data: Dict[str, Any]) -> Optional[bool]:
    """Tri-state FTL classification for an event's product.

    Returns:
        True  — product is explicitly on the FTL (via flag or category match)
        False — product is explicitly NOT on the FTL (ftl_covered=False OR
                a category was supplied and it does not match the FTL)
        None  — no FTL hint was supplied; caller cannot classify.
                The caller should surface this as a compliance *gap* rather
                than stamp the event compliant (see #1346).
    """
    for path in ("kdes.ftl_covered", "ftl_covered", "product.ftl_covered"):
        v = get_nested_value(event_data, path)
        if isinstance(v, bool):
            return v

    if get_ftl_category(event_data) is not None:
        return True

    # A category was supplied but did not match the FTL — treat as non-FTL.
    for path in ("kdes.ftl_category", "ftl_category", "product.category", "product_category"):
        raw = get_nested_value(event_data, path)
        if isinstance(raw, str) and raw.strip():
            return False

    return None


def rule_applies_to_ftl_category(
    rule_applicability: Dict[str, Any],
    event_ftl_category: Optional[str],
) -> bool:
    """Does this rule apply to the event's FTL category?

    A rule's applicability_conditions may include:
        ftl_scope: ["leafy greens", "herbs", ...]   -- specific categories
        ftl_scope: ["ALL"]                           -- any FTL category
        ftl_scope omitted                            -- treated as ["ALL"]
    """
    ftl_scope = rule_applicability.get("ftl_scope") if rule_applicability else None
    if not ftl_scope:
        # Default — applies to all FTL categories (but caller must still
        # gate that the event IS FTL before invoking this helper).
        return True
    normalized_scope = [_normalize(s) or "" for s in ftl_scope if s]
    if "all" in normalized_scope:
        return True
    return event_ftl_category is not None and event_ftl_category in normalized_scope
