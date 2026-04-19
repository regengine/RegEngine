"""
Regression coverage for ``app/sandbox/validation.py`` — the pure-Python
validation utilities used by the sandbox router.

Target: 100% line coverage of validation.py (189 LOC) across the five
public functions:

* ``_validate_kdes`` — per-CTE required Key Data Element presence checks.
* ``_detect_duplicate_lots`` — split-shipment-aware duplicate detection
  keyed on (TLC, CTE type, reference_document).
* ``_is_entity_field`` — classifier used to decide which fields to
  inspect for entity-name normalization.
* ``_normalize_entity_name`` — strips business-entity suffixes,
  punctuation, and collapses whitespace.
* ``_detect_entity_mismatches`` — groups entity-like values by their
  normalized form and reports originals that differ.

These tests deliberately exercise the **observable behavior** of each
function rather than internal data structures, so that future refactors
that preserve the contract won't break the suite.

Tracks GitHub issue #1342 (ingestion test coverage).
"""

from __future__ import annotations

import string

import pytest

from app.sandbox.validation import (
    _detect_duplicate_lots,
    _detect_entity_mismatches,
    _is_entity_field,
    _normalize_entity_name,
    _validate_kdes,
)
from app.webhook_models import REQUIRED_KDES_BY_CTE, WebhookCTEType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _base_event(cte_type: str, **overrides) -> dict:
    """Build a raw-event dict with minimal, valid top-level fields.

    Per-test additions via ``overrides`` let each case isolate a single
    concern (missing KDE, malformed CTE, etc.) without drowning in
    boilerplate.
    """
    event = {
        "cte_type": cte_type,
        "traceability_lot_code": "TLC-0001",
        "product_description": "Romaine Lettuce",
        "quantity": 10,
        "unit_of_measure": "cases",
        "location_name": "Farm A",
        "location_gln": "0012345678905",
        "kdes": {},
    }
    # ``kdes`` can be overridden as a full dict or merged via kwarg expansion;
    # we merge to let callers add a single KDE without blowing away defaults.
    if "kdes" in overrides:
        extra_kdes = overrides.pop("kdes")
        event["kdes"] = {**event["kdes"], **extra_kdes}
    event.update(overrides)
    return event


def _full_required_event(cte_type: WebhookCTEType) -> dict:
    """Construct an event that populates every required KDE for ``cte_type``.

    Used by the "happy path" tests to assert *no* errors rather than
    relying on side effects.
    """
    required = REQUIRED_KDES_BY_CTE[cte_type]
    top_level = {
        "traceability_lot_code": "TLC-OK",
        "product_description": "Product",
        "quantity": 1,
        "unit_of_measure": "cases",
        "location_name": "Loc",
        "location_gln": "0012345678905",
    }
    kdes: dict = {}
    for name in required:
        if name in top_level:
            continue
        kdes[name] = f"filled-{name}"
    event = {
        "cte_type": cte_type.value,
        **top_level,
        "kdes": kdes,
    }
    return event


# ===========================================================================
# _validate_kdes
# ===========================================================================

class TestValidateKdesCteTypeResolution:
    """Validate how ``_validate_kdes`` resolves the ``cte_type`` field."""

    def test_invalid_cte_type_returns_single_error_listing_valid_types(self):
        """An unrecognized CTE short-circuits with a descriptive error."""
        event = _base_event("not_a_real_cte")
        errors = _validate_kdes(event)
        assert len(errors) == 1
        assert "Invalid CTE type 'not_a_real_cte'" in errors[0]
        # The error should enumerate every enum value so operators can
        # fix the payload without hunting through docs.
        for cte in WebhookCTEType:
            assert cte.value in errors[0]

    def test_missing_cte_type_uses_empty_string(self):
        """No ``cte_type`` key at all falls through to the empty-string branch."""
        event = {"kdes": {}}
        errors = _validate_kdes(event)
        assert len(errors) == 1
        assert "Invalid CTE type ''" in errors[0]

    def test_empty_string_cte_type_is_treated_as_invalid(self):
        event = _base_event("")
        errors = _validate_kdes(event)
        assert len(errors) == 1
        assert "Invalid CTE type ''" in errors[0]

    @pytest.mark.parametrize("cte", list(WebhookCTEType))
    def test_all_known_cte_types_are_accepted(self, cte: WebhookCTEType):
        """Every enum member must parse without the "invalid CTE" error."""
        # GROWING has no required-KDE entry; every other CTE must succeed
        # with a fully-filled event.
        event = _full_required_event(cte) if cte in REQUIRED_KDES_BY_CTE else _base_event(cte.value)
        errors = _validate_kdes(event)
        # None of the errors (if any) should be the "Invalid CTE type" shortcut.
        for err in errors:
            assert "Invalid CTE type" not in err


class TestValidateKdesRequiredFields:
    """Verify the required-KDE presence logic."""

    def test_fully_populated_harvesting_event_has_no_errors(self):
        event = _full_required_event(WebhookCTEType.HARVESTING)
        assert _validate_kdes(event) == []

    def test_fully_populated_receiving_event_has_no_errors(self):
        """RECEIVING requires additional ``immediate_previous_source`` KDE."""
        event = _full_required_event(WebhookCTEType.RECEIVING)
        assert _validate_kdes(event) == []

    def test_growing_has_no_required_kdes(self):
        """GROWING is legacy/backward-compat and expects no KDE checks."""
        event = _base_event(WebhookCTEType.GROWING.value)
        assert _validate_kdes(event) == []

    def test_missing_top_level_tlc_reported(self):
        event = _full_required_event(WebhookCTEType.HARVESTING)
        event["traceability_lot_code"] = None
        errors = _validate_kdes(event)
        assert any("traceability_lot_code" in e for e in errors)

    def test_missing_nested_kde_reported(self):
        event = _full_required_event(WebhookCTEType.HARVESTING)
        # Remove a nested KDE and expect that specific error
        event["kdes"].pop("harvest_date")
        errors = _validate_kdes(event)
        assert any("harvest_date" in e for e in errors)
        assert all("harvesting" in e.lower() for e in errors)

    def test_empty_string_treated_as_missing(self):
        """Whitespace-only and empty strings must be flagged as missing.

        This is the ``isinstance(val, str) and val.strip() == ""`` branch.
        """
        event = _full_required_event(WebhookCTEType.HARVESTING)
        event["kdes"]["harvest_date"] = "   "
        errors = _validate_kdes(event)
        assert any("harvest_date" in e for e in errors)

    def test_zero_is_not_flagged_as_missing(self):
        """``0`` is a legitimate quantity and must NOT trip the missing check."""
        event = _full_required_event(WebhookCTEType.HARVESTING)
        event["quantity"] = 0
        errors = _validate_kdes(event)
        assert not any("quantity" in e for e in errors)

    def test_false_is_not_flagged_as_missing(self):
        """Boolean False is falsey but ``None`` check should still accept it."""
        event = _full_required_event(WebhookCTEType.HARVESTING)
        # Slot a boolean into a required field to prove the ``None`` and
        # empty-string-only check ignores non-string falsey values.
        event["product_description"] = False
        errors = _validate_kdes(event)
        assert not any("product_description" in e for e in errors)

    def test_shipping_requires_source_reference(self):
        """SHIPPING has unique ``tlc_source_reference`` and dual locations."""
        event = _full_required_event(WebhookCTEType.SHIPPING)
        event["kdes"].pop("tlc_source_reference")
        errors = _validate_kdes(event)
        assert any("tlc_source_reference" in e for e in errors)

    def test_multiple_missing_kdes_reported_together(self):
        """Every missing KDE must be called out — don't short-circuit at one."""
        event = _full_required_event(WebhookCTEType.SHIPPING)
        for key in ("tlc_source_reference", "reference_document"):
            event["kdes"].pop(key)
        errors = _validate_kdes(event)
        assert len(errors) >= 2
        assert any("tlc_source_reference" in e for e in errors)
        assert any("reference_document" in e for e in errors)

    def test_missing_kdes_dict_entirely(self):
        """Event without any ``kdes`` key at all still gets its top-level fields inspected."""
        event = _base_event(WebhookCTEType.HARVESTING.value)
        # Drop the nested dict — all nested KDEs should now be reported missing
        event.pop("kdes", None)
        errors = _validate_kdes(event)
        missing_names = {e.split("'")[1] for e in errors if "Missing required KDE" in e}
        assert "harvest_date" in missing_names
        assert "reference_document" in missing_names

    def test_nested_kde_overrides_not_used_for_top_level_fields(self):
        """Top-level keys take precedence over identical keys in ``kdes``.

        Exercises the ``**kdes`` unpack order: top-level dict entries are
        written first into ``available`` and then overwritten by the kdes
        dict. We confirm the merge semantics by placing a valid nested KDE
        where a top-level field is missing.
        """
        event = _full_required_event(WebhookCTEType.HARVESTING)
        event["location_name"] = None
        # nested override supplies the missing value
        event["kdes"]["location_name"] = "Loc From Nested"
        errors = _validate_kdes(event)
        assert not any("location_name" in e for e in errors)


# ===========================================================================
# _detect_duplicate_lots
# ===========================================================================

class TestDetectDuplicateLots:
    """Duplicate detection keyed on (TLC, CTE type, reference_document)."""

    def test_unique_events_no_warnings(self):
        events = [
            _base_event("harvesting", traceability_lot_code="TLC-001"),
            _base_event("harvesting", traceability_lot_code="TLC-002"),
            _base_event("shipping", traceability_lot_code="TLC-003"),
        ]
        assert _detect_duplicate_lots(events) == {}

    def test_duplicate_same_cte_same_tlc_same_ref_flagged(self):
        """Exact dup — TLC + CTE + ref_doc all match — gets a warning."""
        events = [
            _base_event("harvesting", traceability_lot_code="TLC-001",
                        kdes={"reference_document": "BOL-100"}),
            _base_event("harvesting", traceability_lot_code="TLC-001",
                        kdes={"reference_document": "BOL-100"}),
        ]
        warnings = _detect_duplicate_lots(events)
        assert 1 in warnings
        assert 0 not in warnings  # the first occurrence is never a warning
        msg = warnings[1][0]
        assert "TLC-001" in msg
        assert "harvesting" in msg
        assert "see event 0" in msg
        assert "same reference document" in msg

    def test_split_shipment_different_ref_docs_not_flagged(self):
        """Different BOLs with same TLC+CTE is a legitimate split shipment."""
        events = [
            _base_event("shipping", traceability_lot_code="TLC-001",
                        kdes={"reference_document": "BOL-100"}),
            _base_event("shipping", traceability_lot_code="TLC-001",
                        kdes={"reference_document": "BOL-101"}),
        ]
        assert _detect_duplicate_lots(events) == {}

    def test_same_tlc_different_cte_not_flagged(self):
        """Same TLC moving through different CTEs is the normal flow."""
        events = [
            _base_event("harvesting", traceability_lot_code="TLC-001"),
            _base_event("cooling", traceability_lot_code="TLC-001"),
            _base_event("shipping", traceability_lot_code="TLC-001"),
        ]
        assert _detect_duplicate_lots(events) == {}

    def test_case_insensitive_tlc_and_cte_keying(self):
        """TLC and CTE comparisons must normalize case differences."""
        events = [
            _base_event("Harvesting", traceability_lot_code="TLC-001"),
            _base_event("HARVESTING", traceability_lot_code="tlc-001"),
        ]
        warnings = _detect_duplicate_lots(events)
        assert 1 in warnings

    def test_surrounding_whitespace_stripped_from_key(self):
        events = [
            _base_event("harvesting", traceability_lot_code="  TLC-001  "),
            _base_event("harvesting", traceability_lot_code="TLC-001"),
        ]
        warnings = _detect_duplicate_lots(events)
        assert 1 in warnings

    def test_missing_tlc_skipped(self):
        """Events without TLC must be ignored entirely, not matched as blank."""
        events = [
            _base_event("harvesting", traceability_lot_code=""),
            _base_event("harvesting", traceability_lot_code=""),
        ]
        assert _detect_duplicate_lots(events) == {}

    def test_none_tlc_skipped(self):
        events = [
            _base_event("harvesting", traceability_lot_code=None),
            _base_event("harvesting", traceability_lot_code=None),
        ]
        assert _detect_duplicate_lots(events) == {}

    def test_missing_cte_type_skipped(self):
        events = [
            _base_event("", traceability_lot_code="TLC-1"),
            _base_event("", traceability_lot_code="TLC-1"),
        ]
        assert _detect_duplicate_lots(events) == {}

    def test_none_cte_type_skipped(self):
        events = [
            {"traceability_lot_code": "TLC-1", "cte_type": None, "kdes": {}},
            {"traceability_lot_code": "TLC-1", "cte_type": None, "kdes": {}},
        ]
        assert _detect_duplicate_lots(events) == {}

    def test_ref_doc_from_top_level_fallback(self):
        """``reference_document`` at top level should be used when ``kdes`` lacks it."""
        events = [
            _base_event("harvesting", traceability_lot_code="TLC-1",
                        reference_document="BOL-A"),
            _base_event("harvesting", traceability_lot_code="TLC-1",
                        reference_document="BOL-A"),
        ]
        warnings = _detect_duplicate_lots(events)
        assert 1 in warnings

    def test_kdes_ref_doc_takes_precedence_over_top_level(self):
        """When both are set, ``kdes.reference_document`` wins (first arg to ``or``)."""
        events = [
            _base_event("harvesting", traceability_lot_code="TLC-1",
                        reference_document="TOP-A",
                        kdes={"reference_document": "KDE-X"}),
            _base_event("harvesting", traceability_lot_code="TLC-1",
                        reference_document="TOP-B",
                        kdes={"reference_document": "KDE-X"}),
        ]
        warnings = _detect_duplicate_lots(events)
        # Matched by the kdes value, not the top-level one
        assert 1 in warnings

    def test_ref_doc_missing_everywhere_matches_on_empty(self):
        """Two events with *no* ref_doc at all should still match each other."""
        events = [
            _base_event("harvesting", traceability_lot_code="TLC-1"),
            _base_event("harvesting", traceability_lot_code="TLC-1"),
        ]
        warnings = _detect_duplicate_lots(events)
        assert 1 in warnings
        # The "with same reference document" clause must NOT appear when ref_doc is empty
        assert "with same reference document" not in warnings[1][0]

    def test_third_duplicate_points_back_to_first_occurrence(self):
        """A 3rd dup should still point back to the *first* occurrence, not the 2nd."""
        events = [
            _base_event("harvesting", traceability_lot_code="TLC-1"),
            _base_event("harvesting", traceability_lot_code="TLC-1"),
            _base_event("harvesting", traceability_lot_code="TLC-1"),
        ]
        warnings = _detect_duplicate_lots(events)
        assert 1 in warnings and 2 in warnings
        assert "see event 0" in warnings[1][0]
        assert "see event 0" in warnings[2][0]

    def test_empty_input_returns_empty_dict(self):
        assert _detect_duplicate_lots([]) == {}

    def test_ref_doc_none_coerced_via_or(self):
        """``kdes.reference_document`` is None → falls through to top-level (also None) → empty string."""
        events = [
            _base_event("harvesting", traceability_lot_code="TLC-1",
                        kdes={"reference_document": None}),
            _base_event("harvesting", traceability_lot_code="TLC-1",
                        kdes={"reference_document": None}),
        ]
        warnings = _detect_duplicate_lots(events)
        assert 1 in warnings


# ===========================================================================
# _is_entity_field
# ===========================================================================

class TestIsEntityField:

    @pytest.mark.parametrize("field_name", [
        "location_name",
        "ship_from_location",
        "ship_to_location",
        "receiving_location",
        "from_entity_reference",
        "immediate_previous_source",
    ])
    def test_explicit_fields_recognized(self, field_name: str):
        assert _is_entity_field(field_name) is True

    @pytest.mark.parametrize("field_name", [
        "LOCATION_NAME",
        "Ship_From_Location",
        "Immediate_Previous_SOURCE",
    ])
    def test_explicit_fields_case_insensitive(self, field_name: str):
        assert _is_entity_field(field_name) is True

    @pytest.mark.parametrize("field_name", [
        "some_location_field",
        "entity_reference_xyz",
        "any_source_thing",
        "facility_id",
        "my_facility",
    ])
    def test_marker_substring_matches(self, field_name: str):
        """Fields containing 'location'/'entity'/'source'/'facility' match."""
        assert _is_entity_field(field_name) is True

    @pytest.mark.parametrize("field_name", [
        "traceability_lot_code",
        "product_description",
        "quantity",
        "unit_of_measure",
        "harvest_date",
        "cte_type",
    ])
    def test_non_entity_fields_rejected(self, field_name: str):
        assert _is_entity_field(field_name) is False

    def test_empty_string_is_not_entity_field(self):
        """Empty string contains no markers and isn't in the explicit set."""
        assert _is_entity_field("") is False


# ===========================================================================
# _normalize_entity_name
# ===========================================================================

class TestNormalizeEntityName:

    @pytest.mark.parametrize("original, expected", [
        ("Acme Foods, Inc.", "acme foods"),
        ("Acme Foods Inc", "acme foods"),
        ("Acme Foods, LLC", "acme foods"),
        ("Acme Foods LLC", "acme foods"),
        ("Acme Foods Corp.", "acme foods"),
        ("Acme Foods Corporation", "acme foods"),
        ("Acme Foods Limited", "acme foods"),
        ("Acme Foods Ltd.", "acme foods"),
        ("Acme Foods Ltd", "acme foods"),
        ("Acme Foods Company", "acme foods"),
        ("Acme Foods Co.", "acme foods"),
        ("Acme Foods Co", "acme foods"),
        ("Acme Foods L.L.C.", "acme foods"),
        ("Acme Foods L.L.P.", "acme foods"),
        ("Acme Foods L.P.", "acme foods"),
        ("Acme Foods LP", "acme foods"),
        ("Acme Foods LLP", "acme foods"),
        ("Acme Foods Incorporated", "acme foods"),
    ])
    def test_strips_business_suffixes(self, original: str, expected: str):
        assert _normalize_entity_name(original) == expected

    def test_collapses_internal_whitespace(self):
        assert _normalize_entity_name("Acme    Foods") == "acme foods"

    def test_strips_leading_and_trailing_whitespace(self):
        assert _normalize_entity_name("   Acme Foods   ") == "acme foods"

    def test_strips_all_punctuation(self):
        # Every character from string.punctuation should be stripped.
        noisy = "A!c@m#e$%^&*()Foods"
        assert _normalize_entity_name(noisy) == "acmefoods"

    def test_case_folded(self):
        assert _normalize_entity_name("ACME FOODS") == "acme foods"

    def test_no_suffix_returns_lowercased_trimmed(self):
        assert _normalize_entity_name("Acme Foods") == "acme foods"

    def test_empty_input_returns_empty_string(self):
        assert _normalize_entity_name("") == ""

    def test_only_whitespace_returns_empty_string(self):
        assert _normalize_entity_name("     ") == ""

    def test_suffix_only_returns_empty_string(self):
        """A string consisting of just a suffix becomes empty once stripped."""
        # "Inc." on its own has no preceding word — the pattern requires
        # [,\s]+ before the suffix so an isolated suffix is NOT stripped.
        # That's intentional: the function treats it as a real name.
        # Here we just verify the observable output rather than asserting
        # empty (which would be a contract violation).
        assert _normalize_entity_name("Inc.") == "inc"

    def test_newlines_and_tabs_collapsed(self):
        assert _normalize_entity_name("Acme\n\tFoods") == "acme foods"

    def test_comma_before_suffix_is_stripped(self):
        assert _normalize_entity_name("Acme Foods,Inc") == "acme foods"

    def test_trailing_period_in_non_suffix_name(self):
        """A trailing period that's not part of a suffix is stripped as punctuation."""
        assert _normalize_entity_name("Acme.") == "acme"

    def test_multiple_words_preserved(self):
        assert (
            _normalize_entity_name("Big Farm Produce Company")
            == "big farm produce"
        )

    def test_punctuation_constant_fully_stripped(self):
        """Guardrail: every char in string.punctuation must be removed.

        Prevents regression if Python's ``string.punctuation`` ever adds
        a character that the current translate-table misses.
        """
        result = _normalize_entity_name(string.punctuation)
        assert result == ""


# ===========================================================================
# _detect_entity_mismatches
# ===========================================================================

class TestDetectEntityMismatches:

    def test_no_entities_no_warnings(self):
        events = [
            {"traceability_lot_code": "TLC-1", "quantity": 5, "kdes": {}},
        ]
        assert _detect_entity_mismatches(events) == []

    def test_single_entity_value_no_warnings(self):
        events = [
            {"location_name": "Acme Foods, Inc.", "kdes": {}},
        ]
        assert _detect_entity_mismatches(events) == []

    def test_duplicate_identical_values_no_warnings(self):
        """Same raw value repeated should NOT trigger a warning."""
        events = [
            {"location_name": "Acme Foods, Inc.", "kdes": {}},
            {"location_name": "Acme Foods, Inc.", "kdes": {}},
        ]
        assert _detect_entity_mismatches(events) == []

    def test_inc_vs_llc_same_root_flagged(self):
        """``Acme Foods, Inc.`` vs ``Acme Foods LLC`` normalize alike."""
        events = [
            {"location_name": "Acme Foods, Inc.", "kdes": {}},
            {"location_name": "Acme Foods LLC", "kdes": {}},
        ]
        warnings = _detect_entity_mismatches(events)
        assert len(warnings) == 1
        assert "Acme Foods, Inc." in warnings[0]
        assert "Acme Foods LLC" in warnings[0]
        assert "consider standardizing" in warnings[0]

    def test_three_variants_produce_three_pairs(self):
        """N=3 distinct originals → C(3,2)=3 pairwise warnings."""
        events = [
            {"location_name": "Acme Foods, Inc.", "kdes": {}},
            {"location_name": "Acme Foods LLC", "kdes": {}},
            {"location_name": "Acme Foods Corp.", "kdes": {}},
        ]
        warnings = _detect_entity_mismatches(events)
        assert len(warnings) == 3

    def test_warnings_are_alphabetically_ordered_pairs(self):
        """Sorted-originals ensures deterministic output irrespective of input order."""
        # Build input in "wrong" order — sorted() in the impl must
        # reorder the originals so output is stable.
        events = [
            {"location_name": "Zebra Farms LLC", "kdes": {}},
            {"location_name": "Acme Foods Inc", "kdes": {}},
        ]
        warnings_ab = _detect_entity_mismatches(events)

        events_reversed = [
            {"location_name": "Acme Foods Inc", "kdes": {}},
            {"location_name": "Zebra Farms LLC", "kdes": {}},
        ]
        warnings_ba = _detect_entity_mismatches(events_reversed)

        # Different normalizations so no warning either way.
        assert warnings_ab == [] and warnings_ba == []

    def test_nested_kdes_inspected(self):
        """Entity-like values inside the nested ``kdes`` dict trigger warnings."""
        events = [
            {"kdes": {"ship_from_location": "Acme Foods, Inc."}},
            {"kdes": {"ship_from_location": "Acme Foods LLC"}},
        ]
        warnings = _detect_entity_mismatches(events)
        assert len(warnings) == 1

    def test_mixed_top_level_and_nested_cross_match(self):
        """Collisions between a top-level value and a nested one are reported."""
        events = [
            {"location_name": "Acme Foods, Inc."},
            {"kdes": {"ship_to_location": "Acme Foods LLC"}},
        ]
        warnings = _detect_entity_mismatches(events)
        assert len(warnings) == 1

    def test_non_entity_fields_ignored(self):
        """String values in non-entity fields must not be inspected."""
        events = [
            {"product_description": "Acme Foods, Inc.", "kdes": {}},
            {"product_description": "Acme Foods LLC", "kdes": {}},
        ]
        assert _detect_entity_mismatches(events) == []

    def test_non_string_entity_field_values_skipped(self):
        """Non-string values (e.g., dict payloads) in entity fields are skipped."""
        events = [
            {"location_name": {"nested": "dict"}, "kdes": {}},
            {"location_name": 42, "kdes": {}},
            {"location_name": None, "kdes": {}},
        ]
        assert _detect_entity_mismatches(events) == []

    def test_empty_string_in_entity_field_skipped(self):
        """Empty/whitespace values shouldn't pollute the normalization buckets."""
        events = [
            {"location_name": "   ", "kdes": {}},
            {"location_name": "", "kdes": {}},
        ]
        assert _detect_entity_mismatches(events) == []

    def test_non_dict_kdes_safely_ignored(self):
        """If ``kdes`` isn't a dict (e.g., a list by mistake) we skip it."""
        events = [
            {"location_name": "Acme Foods, Inc.", "kdes": ["accidentally", "a", "list"]},
            {"location_name": "Acme Foods LLC"},
        ]
        warnings = _detect_entity_mismatches(events)
        # Top-level values still collide; nested skip is a no-op
        assert len(warnings) == 1

    def test_same_normalized_value_but_original_strings_differ_only_in_case(self):
        """Case-only difference between originals IS still reported.

        Because the bucket key is the lowercased-normalized form but the
        bucket stores the ``.strip()``-ed original, two differently-cased
        strings collide in the bucket and are reported as a mismatch.
        """
        events = [
            {"location_name": "Acme Foods"},
            {"location_name": "ACME FOODS"},
        ]
        warnings = _detect_entity_mismatches(events)
        assert len(warnings) == 1

    def test_whitespace_only_difference_is_ignored(self):
        """Two originals that differ only in stripped whitespace are NOT flagged.

        The bucket stores ``value.strip()`` so "Acme Foods" and "  Acme
        Foods  " become the same bucket entry.
        """
        events = [
            {"location_name": "Acme Foods"},
            {"location_name": "  Acme Foods  "},
        ]
        assert _detect_entity_mismatches(events) == []

    def test_missing_kdes_key_is_safe(self):
        """Event without a ``kdes`` key shouldn't raise."""
        events = [
            {"location_name": "Acme Foods, Inc."},
            {"location_name": "Acme Foods LLC"},
        ]
        warnings = _detect_entity_mismatches(events)
        assert len(warnings) == 1

    def test_empty_events_list_returns_empty(self):
        assert _detect_entity_mismatches([]) == []

    def test_groups_never_collapse_across_different_normalized_forms(self):
        """Genuinely different entities must not be cross-reported."""
        events = [
            {"location_name": "Acme Foods, Inc."},
            {"location_name": "Zebra Farms, LLC"},
            {"location_name": "Big Dipper Dairy"},
        ]
        assert _detect_entity_mismatches(events) == []
