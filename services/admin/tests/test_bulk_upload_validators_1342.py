"""Coverage sweep for ``services/admin/app/bulk_upload/validators.py`` — #1342.

Targets the uncovered branches in the bulk-upload Pydantic validators:

* ``_autofill_str`` substituting the default when input is empty or below min_len
  (lines 22-29) — validators gate user-supplied CSV/Excel data before persist,
  so an unfilled warning-path silently drops telemetry about auto-corrected rows.
* ``BulkFacilityRow._normalize_roles`` None / list / str / other-type branches
  (lines 87, 90-92) — roles column in bulk CSVs arrives as pipe/comma lists
  and occasionally as ``None``/int; the wrong branch blows up model_validate.
* ``BulkCTEEventRow._normalize_cte`` when the cleaned value is <2 chars
  (line 150) — guarantees a too-short event type is auto-filled rather than
  crashing downstream CTE persistence.
* ``BulkCTEEventRow._normalize_event_time`` None / empty / invalid branches
  (lines 157, 160, 163-164) — the invalid-ISO branch raises ValueError which
  becomes a row-level ValidationError (covered below).
* ``BulkCTEEventRow._normalize_obligations`` None / list / str / other-type
  branches (lines 170-176) — parity with ``_normalize_roles``.
* ``validate_and_normalize_payload`` non-list section (lines 214-221) —
  when a caller uploads ``{"facilities": "not a list"}`` we emit a single
  section-level error instead of crashing.
* ``validate_and_normalize_payload`` Pydantic ValidationError path
  (lines 226-237) — rows that still fail after auto-fill (e.g. non-dict row,
  non-ISO event_time) must demote to severity=warning and skip the row.
* ``validate_and_normalize_payload`` unknown FTL category_id branch
  (lines 254-262) — FTL scoping is a regulatory requirement (see
  project_regulatory_logic_audit_2026_04_17.md re: FTL scoping gap); any
  category_id outside the valid set must emit a warning and be dropped.
"""
from __future__ import annotations

import pytest

from app.bulk_upload.validators import (
    _AUTOFILL_WARNINGS,
    _autofill_str,
    BulkCTEEventRow,
    BulkFacilityRow,
    BulkFTLScopeRow,
    BulkTLCRow,
    compute_payload_sha256,
    next_merkle_hash,
    normalize_cte_type,
    validate_and_normalize_payload,
)


# ─────────────────────────────────────────────────────────────────────
# _autofill_str — the warning-substitution branch (lines 22-29)
# ─────────────────────────────────────────────────────────────────────


def test_autofill_str_substitutes_default_when_empty():
    """Empty strings must substitute the default and record a warning."""
    _AUTOFILL_WARNINGS.clear()
    result = _autofill_str("", field="facility_name", row_hint="row 5", default="Unnamed")
    assert result == "Unnamed"
    assert len(_AUTOFILL_WARNINGS) == 1
    warn = _AUTOFILL_WARNINGS[-1]
    assert warn["field"] == "facility_name"
    assert warn["original"] == "(empty)"
    assert warn["replacement"] == "Unnamed"
    assert warn["hint"] == "row 5"


def test_autofill_str_substitutes_default_when_too_short():
    """Values shorter than min_len substitute the default (original captured)."""
    _AUTOFILL_WARNINGS.clear()
    result = _autofill_str("a", field="facility_name", min_len=2, default="Unnamed")
    assert result == "Unnamed"
    assert _AUTOFILL_WARNINGS[-1]["original"] == "a"


def test_autofill_str_substitutes_for_none_value():
    """None values get normalized to empty string and trigger substitution."""
    _AUTOFILL_WARNINGS.clear()
    result = _autofill_str(None, field="tlc_code", min_len=3, default="TLC-UNKNOWN")
    assert result == "TLC-UNKNOWN"
    assert _AUTOFILL_WARNINGS[-1]["original"] == "(empty)"


def test_autofill_str_keeps_value_when_long_enough():
    """Values >= min_len pass through unchanged (sanity for non-warning branch)."""
    _AUTOFILL_WARNINGS.clear()
    result = _autofill_str("Salinas Packhouse", field="facility_name", min_len=2)
    assert result == "Salinas Packhouse"
    assert _AUTOFILL_WARNINGS == []


# ─────────────────────────────────────────────────────────────────────
# BulkFacilityRow._normalize_roles branches (lines 87, 90-92)
# ─────────────────────────────────────────────────────────────────────


def test_facility_roles_none_becomes_empty_list():
    """None roles column must become [] (line 87)."""
    row = BulkFacilityRow(name="ACME", roles=None)
    assert row.roles == []


def test_facility_roles_list_strips_and_filters_blanks():
    """list-of-strings: strip each, drop empties."""
    row = BulkFacilityRow(name="ACME", roles=["Grower ", "", "  ", "Packer"])
    assert row.roles == ["Grower", "Packer"]


def test_facility_roles_list_coerces_non_string_items():
    """list with int/other types is coerced via str() (line 89)."""
    row = BulkFacilityRow(name="ACME", roles=[1, 2, "Grower"])
    assert row.roles == ["1", "2", "Grower"]


def test_facility_roles_string_splits_on_comma():
    """Single CSV string splits on ',' — most common CSV intake shape."""
    row = BulkFacilityRow(name="ACME", roles="Grower, Packer, Shipper")
    assert row.roles == ["Grower", "Packer", "Shipper"]


def test_facility_roles_string_drops_blank_tokens():
    """CSV string with empty tokens drops them after strip."""
    row = BulkFacilityRow(name="ACME", roles="Grower,,  ,Packer")
    assert row.roles == ["Grower", "Packer"]


def test_facility_roles_unknown_type_becomes_empty_list():
    """Unknown types (int, dict, etc.) fall through to [] (line 92)."""
    row = BulkFacilityRow(name="ACME", roles=42)
    assert row.roles == []
    row2 = BulkFacilityRow(name="ACME", roles={"a": 1})
    assert row2.roles == []


# ─────────────────────────────────────────────────────────────────────
# BulkCTEEventRow._normalize_cte short-value branch (line 150)
# ─────────────────────────────────────────────────────────────────────


def test_cte_event_normalize_cte_falls_back_when_too_short():
    """A cte_type that normalizes to <2 chars auto-fills to 'receiving'."""
    _AUTOFILL_WARNINGS.clear()
    row = BulkCTEEventRow(
        facility_name="ACME Distribution",
        tlc_code="TLC-123",
        cte_type="x",  # normalizes to "x" (1 char) → autofill
    )
    assert row.cte_type == "receiving"
    assert any(w["field"] == "cte_type" for w in _AUTOFILL_WARNINGS)


def test_cte_event_normalize_cte_empty_value_falls_back():
    """An empty cte_type autofills to 'receiving'."""
    _AUTOFILL_WARNINGS.clear()
    row = BulkCTEEventRow(
        facility_name="ACME Distribution",
        tlc_code="TLC-123",
        cte_type="",
    )
    assert row.cte_type == "receiving"


def test_cte_event_normalize_cte_alias_single_letter_expands():
    """Single-letter alias 'r' normalizes to 'receiving' (no autofill)."""
    _AUTOFILL_WARNINGS.clear()
    row = BulkCTEEventRow(
        facility_name="ACME Distribution",
        tlc_code="TLC-123",
        cte_type="r",
    )
    assert row.cte_type == "receiving"
    # Should NOT have a cte_type autofill because alias resolved
    assert not any(w["field"] == "cte_type" for w in _AUTOFILL_WARNINGS)


# ─────────────────────────────────────────────────────────────────────
# BulkCTEEventRow._normalize_event_time branches (lines 157, 160, 163-164)
# ─────────────────────────────────────────────────────────────────────


def test_event_time_none_stays_none():
    """None event_time passes through as None (line 157)."""
    row = BulkCTEEventRow(
        facility_name="ACME Distribution",
        tlc_code="TLC-123",
        cte_type="shipping",
        event_time=None,
    )
    assert row.event_time is None


def test_event_time_empty_string_becomes_none():
    """Empty/whitespace-only event_time becomes None (line 160)."""
    row = BulkCTEEventRow(
        facility_name="ACME Distribution",
        tlc_code="TLC-123",
        cte_type="shipping",
        event_time="   ",
    )
    assert row.event_time is None


def test_event_time_z_suffix_is_normalized():
    """ISO-8601 with trailing 'Z' parses to UTC offset form."""
    row = BulkCTEEventRow(
        facility_name="ACME Distribution",
        tlc_code="TLC-123",
        cte_type="shipping",
        event_time="2026-03-03T12:00:00Z",
    )
    # fromisoformat("...+00:00") gives +00:00 ISO output
    assert row.event_time is not None
    assert row.event_time.startswith("2026-03-03T12:00:00")


def test_event_time_invalid_raises_validation_error():
    """Non-ISO event_time raises ValidationError (lines 163-164)."""
    from pydantic import ValidationError as PydanticValidationError

    with pytest.raises(PydanticValidationError) as excinfo:
        BulkCTEEventRow(
            facility_name="ACME Distribution",
            tlc_code="TLC-123",
            cte_type="shipping",
            event_time="not-an-iso-date",
        )
    assert "event_time must be ISO-8601" in str(excinfo.value)


# ─────────────────────────────────────────────────────────────────────
# BulkCTEEventRow._normalize_obligations branches (lines 170-176)
# ─────────────────────────────────────────────────────────────────────


def test_obligations_none_becomes_empty_list():
    """None obligations -> []."""
    row = BulkCTEEventRow(
        facility_name="ACME Distribution",
        tlc_code="TLC-123",
        cte_type="shipping",
        obligation_ids=None,
    )
    assert row.obligation_ids == []


def test_obligations_list_strips_and_filters():
    """list of strings -> strip each, drop empties."""
    row = BulkCTEEventRow(
        facility_name="ACME Distribution",
        tlc_code="TLC-123",
        cte_type="shipping",
        obligation_ids=["OBL-1 ", "", "  ", "OBL-2"],
    )
    assert row.obligation_ids == ["OBL-1", "OBL-2"]


def test_obligations_string_splits_on_comma():
    """CSV-like string obligation_ids split on commas."""
    row = BulkCTEEventRow(
        facility_name="ACME Distribution",
        tlc_code="TLC-123",
        cte_type="shipping",
        obligation_ids="OBL-1, OBL-2,OBL-3",
    )
    assert row.obligation_ids == ["OBL-1", "OBL-2", "OBL-3"]


def test_obligations_unknown_type_becomes_empty_list():
    """Unknown types (int, dict, etc.) -> [] (line 176)."""
    row = BulkCTEEventRow(
        facility_name="ACME Distribution",
        tlc_code="TLC-123",
        cte_type="shipping",
        obligation_ids=99,
    )
    assert row.obligation_ids == []


# ─────────────────────────────────────────────────────────────────────
# validate_and_normalize_payload — section-level non-list (lines 214-221)
# ─────────────────────────────────────────────────────────────────────


def test_validate_facilities_section_not_a_list_emits_error():
    """If a top-level section is not a list, emit a section-level error."""
    normalized, errors = validate_and_normalize_payload(
        {
            "facilities": "not-a-list",
            "ftl_scopes": [],
            "tlcs": [],
            "events": [],
        },
        supported_cte_types={"shipping", "receiving"},
        valid_ftl_category_ids={"1", "2"},
    )
    assert normalized["facilities"] == []
    assert any(
        e["section"] == "facility" and e["message"] == "Section must be an array"
        for e in errors
    )


def test_validate_multiple_sections_not_lists_all_report():
    """Each offending section emits its own error."""
    normalized, errors = validate_and_normalize_payload(
        {
            "facilities": "nope",
            "ftl_scopes": 123,
            "tlcs": {"bad": "dict"},
            "events": "still-bad",
        },
        supported_cte_types=set(),
        valid_ftl_category_ids=set(),
    )
    section_errors = {
        e["section"]
        for e in errors
        if e.get("message") == "Section must be an array"
    }
    assert section_errors == {"facility", "ftl_scope", "tlc", "event"}
    assert normalized == {"facilities": [], "ftl_scopes": [], "tlcs": [], "events": []}


def test_validate_missing_sections_treated_as_empty():
    """Absent sections default to [] (no errors emitted)."""
    normalized, errors = validate_and_normalize_payload(
        {},
        supported_cte_types={"shipping"},
        valid_ftl_category_ids={"1"},
    )
    assert normalized == {"facilities": [], "ftl_scopes": [], "tlcs": [], "events": []}
    # No section-array errors; no rows -> no autofill warnings
    assert not any(e.get("message") == "Section must be an array" for e in errors)


# ─────────────────────────────────────────────────────────────────────
# validate_and_normalize_payload — Pydantic ValidationError (lines 226-237)
# ─────────────────────────────────────────────────────────────────────


def test_validate_invalid_row_demoted_to_warning_and_skipped():
    """A row that raises ValidationError becomes a warning and is skipped."""
    # A non-dict row cannot be validated by model_validate; it raises
    # ValidationError → hits the exception path.
    normalized, errors = validate_and_normalize_payload(
        {
            "facilities": ["not-a-dict"],  # invalid row shape
            "ftl_scopes": [],
            "tlcs": [],
            "events": [],
        },
        supported_cte_types={"shipping"},
        valid_ftl_category_ids={"1"},
    )
    assert normalized["facilities"] == []  # skipped
    warning_errors = [
        e for e in errors
        if e.get("section") == "facility" and e.get("severity") == "warning"
    ]
    assert len(warning_errors) == 1
    assert warning_errors[0]["row"] == 1
    assert "message" in warning_errors[0]


def test_validate_invalid_event_time_demoted_to_warning():
    """Invalid ISO event_time raises ValidationError → warning row."""
    normalized, errors = validate_and_normalize_payload(
        {
            "facilities": [],
            "ftl_scopes": [],
            "tlcs": [],
            "events": [
                {
                    "facility_name": "ACME",
                    "tlc_code": "TLC-1",
                    "cte_type": "shipping",
                    "event_time": "not-iso",
                }
            ],
        },
        supported_cte_types={"shipping"},
        valid_ftl_category_ids={"1"},
    )
    assert normalized["events"] == []
    warning_errors = [
        e for e in errors
        if e.get("section") == "event" and e.get("severity") == "warning"
    ]
    assert len(warning_errors) == 1
    assert "ISO-8601" in warning_errors[0]["message"]


# ─────────────────────────────────────────────────────────────────────
# validate_and_normalize_payload — unknown FTL category_id (lines 254-262)
# ─────────────────────────────────────────────────────────────────────


def test_validate_ftl_scope_unknown_category_emits_warning_and_drops():
    """Unknown FTL category_id emits a warning and drops the row."""
    normalized, errors = validate_and_normalize_payload(
        {
            "facilities": [],
            "ftl_scopes": [
                {"facility_name": "ACME", "category_id": "999-not-real"},
            ],
            "tlcs": [],
            "events": [],
        },
        supported_cte_types={"shipping"},
        valid_ftl_category_ids={"1", "2"},
    )
    assert normalized["ftl_scopes"] == []
    unknown_errors = [
        e for e in errors
        if e.get("section") == "ftl_scope"
        and "Unknown FTL category_id" in e.get("message", "")
    ]
    assert len(unknown_errors) == 1
    assert unknown_errors[0]["severity"] == "warning"
    assert unknown_errors[0]["row"] == 1


def test_validate_ftl_scope_valid_category_passes_through():
    """A known category_id is retained (sanity for non-warning branch)."""
    normalized, errors = validate_and_normalize_payload(
        {
            "facilities": [],
            "ftl_scopes": [
                {"facility_name": "ACME Distribution", "category_id": "2"},
            ],
            "tlcs": [],
            "events": [],
        },
        supported_cte_types={"shipping"},
        valid_ftl_category_ids={"1", "2"},
    )
    assert len(normalized["ftl_scopes"]) == 1
    assert normalized["ftl_scopes"][0]["category_id"] == "2"
    # No "Unknown FTL category_id" errors
    assert not any(
        "Unknown FTL category_id" in e.get("message", "") for e in errors
    )


# ─────────────────────────────────────────────────────────────────────
# Autofill warnings projection into the errors list
# ─────────────────────────────────────────────────────────────────────


def test_autofill_warning_with_hint_included_in_errors():
    """Autofill warnings propagate to errors with the row hint appended."""
    # Empty facility name triggers autofill; the warning should be reflected
    # in the final errors list.
    normalized, errors = validate_and_normalize_payload(
        {
            "facilities": [
                {"name": "", "street": "1 Main", "city": "SF", "state": "CA", "postal_code": "94103"}
            ],
            "ftl_scopes": [],
            "tlcs": [],
            "events": [],
        },
        supported_cte_types={"shipping"},
        valid_ftl_category_ids={"1"},
    )
    # The facility is still retained with the autofill default
    assert len(normalized["facilities"]) == 1
    assert normalized["facilities"][0]["name"] == "Unnamed Facility"
    # The errors list contains an autofill warning
    autofill_warnings = [e for e in errors if e.get("section") == "autofill"]
    assert len(autofill_warnings) >= 1
    assert all(w["severity"] == "warning" for w in autofill_warnings)


def test_autofill_warning_for_unsupported_cte_type_propagates_hint():
    """Unsupported cte_type triggers a hint-bearing warning ('event row N')."""
    normalized, errors = validate_and_normalize_payload(
        {
            "facilities": [],
            "ftl_scopes": [],
            "tlcs": [],
            "events": [
                {
                    "facility_name": "ACME",
                    "tlc_code": "TLC-1",
                    "cte_type": "totally-unsupported",
                }
            ],
        },
        supported_cte_types={"shipping", "receiving"},
        valid_ftl_category_ids={"1"},
    )
    assert normalized["events"][0]["cte_type"] == "receiving"
    hint_warnings = [
        e for e in errors
        if e.get("section") == "autofill" and "event row 1" in e.get("message", "")
    ]
    assert len(hint_warnings) >= 1


# ─────────────────────────────────────────────────────────────────────
# Sanity — other model validators still produce valid outputs
# ─────────────────────────────────────────────────────────────────────


def test_bulk_tlc_row_autofills_short_codes():
    """TLC codes shorter than 3 chars autofill to TLC-UNKNOWN."""
    _AUTOFILL_WARNINGS.clear()
    row = BulkTLCRow(tlc_code="ab", facility_name="ACME")
    assert row.tlc_code == "TLC-UNKNOWN"


def test_bulk_ftl_scope_row_autofills_short_category():
    """FTL category_id shorter than 1 char autofills to 'unknown'."""
    _AUTOFILL_WARNINGS.clear()
    row = BulkFTLScopeRow(facility_name="ACME", category_id="")
    assert row.category_id == "unknown"


def test_normalize_cte_type_unknown_passes_through():
    """Unknown CTE aliases normalize to their lowercase stripped form."""
    assert normalize_cte_type("ShipPing ") == "shipping"
    assert normalize_cte_type("custom_type") == "custom_type"


def test_compute_payload_sha256_and_next_merkle_chain():
    """compute_payload_sha256 and next_merkle_hash are deterministic thin wrappers."""
    payload = {"a": 1, "b": 2}
    h1 = compute_payload_sha256(payload)
    h2 = compute_payload_sha256(payload)
    assert h1 == h2
    chain = next_merkle_hash(None, h1)
    assert isinstance(chain, str) and len(chain) > 0
