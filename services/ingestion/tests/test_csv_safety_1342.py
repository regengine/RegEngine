"""
Regression coverage for ``app/shared/csv_safety.py``.

The module defends against CSV formula-injection (CWE-1236): a text
export opened in Excel/Sheets/LibreOffice will execute any cell whose
first character is ``=``, ``+``, ``-``, ``@``, tab, or carriage-return.
:func:`sanitize_cell` neutralizes the payload by prefixing dangerous
values with a literal single-quote — preserved as a text-marker by
the spreadsheet client and never rendered.

These tests lock in the exact threat model:

* every dangerous prefix triggers sanitization
* safe values pass through unchanged (no false-positives)
* dict/sequence helpers apply the same rule to every field/cell
* None, numeric, and boolean coercions round-trip sensibly

Tracks GitHub issue #1342 (ingestion test coverage) and ties back to
#1081 / #1272 (FDA export + spreadsheet codepaths that ship this
module in production).
"""

from __future__ import annotations

import pytest

from app.shared.csv_safety import (
    sanitize_cell,
    sanitize_row,
    sanitize_sequence,
)


# ===========================================================================
# sanitize_cell — formula-prefix neutralization
# ===========================================================================

class TestSanitizeCellDangerousPrefixes:

    @pytest.mark.parametrize("payload", [
        "=SUM(A1:A10)",
        "=WEBSERVICE(\"http://evil/\")",
        "=cmd|' /C calc'!A0",
        "+1+cmd",
        "-2-cmd",
        "@SUM(1+1)",
        "\tmalicious",
        "\rmalicious",
    ])
    def test_dangerous_prefix_gets_single_quote_escape(self, payload):
        """Every prefix in the module's block-list must be neutralized."""
        result = sanitize_cell(payload)
        assert result.startswith("'")
        # The original payload is preserved after the quote.
        assert result[1:] == payload

    def test_equals_sign_alone(self):
        assert sanitize_cell("=") == "'="

    def test_plus_sign_alone(self):
        assert sanitize_cell("+") == "'+"

    def test_minus_sign_alone(self):
        assert sanitize_cell("-") == "'-"

    def test_at_sign_alone(self):
        assert sanitize_cell("@") == "'@"

    def test_tab_alone(self):
        assert sanitize_cell("\t") == "'\t"

    def test_carriage_return_alone(self):
        assert sanitize_cell("\r") == "'\r"


# ===========================================================================
# sanitize_cell — safe passthrough
# ===========================================================================

class TestSanitizeCellSafeValues:

    @pytest.mark.parametrize("payload", [
        "Romaine Hearts",
        "Lot #42",                     # # is safe
        "hello world",
        "a=b",                          # = in the middle is safe
        "abc+xyz",                      # + in middle
        "back\\slash",
        "quoted \"inside\"",
        "3.14",
        "2026-01-01T00:00:00Z",
        "tab\tinside\tstring",          # tab in middle is safe
        "carriage\rreturn\rinside",     # \r in middle is safe
    ])
    def test_safe_values_pass_through_unchanged(self, payload):
        assert sanitize_cell(payload) == payload

    def test_empty_string_returns_empty(self):
        assert sanitize_cell("") == ""

    def test_whitespace_only_string_is_safe(self):
        """A leading space is not a formula trigger."""
        assert sanitize_cell("  =1") == "  =1"


# ===========================================================================
# sanitize_cell — non-string inputs
# ===========================================================================

class TestSanitizeCellCoercion:

    def test_none_becomes_empty_string(self):
        assert sanitize_cell(None) == ""

    def test_integer_coerced_to_string(self):
        assert sanitize_cell(42) == "42"

    def test_negative_integer_gets_escaped(self):
        """`-42` starts with `-`, a dangerous prefix."""
        assert sanitize_cell(-42) == "'-42"

    def test_float_coerced_to_string(self):
        assert sanitize_cell(3.14) == "3.14"

    def test_negative_float_gets_escaped(self):
        assert sanitize_cell(-3.14) == "'-3.14"

    def test_boolean_coerced_to_string(self):
        assert sanitize_cell(True) == "True"
        assert sanitize_cell(False) == "False"

    def test_custom_object_coerced_via_str(self):
        class Thing:
            def __str__(self) -> str:
                return "my-thing"
        assert sanitize_cell(Thing()) == "my-thing"

    def test_custom_object_with_dangerous_str_escaped(self):
        class Thing:
            def __str__(self) -> str:
                return "=evil"
        assert sanitize_cell(Thing()) == "'=evil"


# ===========================================================================
# sanitize_row — dict row helper
# ===========================================================================

class TestSanitizeRow:

    def test_empty_dict(self):
        assert sanitize_row({}) == {}

    def test_safe_values_unchanged(self):
        row = {"name": "Romaine", "qty": "100"}
        assert sanitize_row(row) == {"name": "Romaine", "qty": "100"}

    def test_dangerous_value_escaped(self):
        row = {"name": "=evil", "qty": "100"}
        assert sanitize_row(row) == {"name": "'=evil", "qty": "100"}

    def test_mixed_safe_and_dangerous(self):
        row = {
            "a": "safe",
            "b": "=formula",
            "c": "+sum",
            "d": 42,
            "e": None,
        }
        result = sanitize_row(row)
        assert result == {
            "a": "safe",
            "b": "'=formula",
            "c": "'+sum",
            "d": "42",
            "e": "",
        }

    def test_keys_preserved_verbatim(self):
        """Keys are NOT sanitized — only values."""
        row = {"=weird-key": "safe-value"}
        result = sanitize_row(row)
        assert "=weird-key" in result
        assert result["=weird-key"] == "safe-value"

    def test_all_values_coerced_to_string(self):
        row = {"a": 1, "b": 2.5, "c": True}
        result = sanitize_row(row)
        assert all(isinstance(v, str) for v in result.values())


# ===========================================================================
# sanitize_sequence — list/tuple row helper
# ===========================================================================

class TestSanitizeSequence:

    def test_empty_sequence(self):
        assert sanitize_sequence([]) == []
        assert sanitize_sequence(()) == []

    def test_safe_sequence_passes_through(self):
        assert sanitize_sequence(["a", "b", "c"]) == ["a", "b", "c"]

    def test_dangerous_values_escaped(self):
        assert sanitize_sequence(["=evil", "ok", "-1"]) == ["'=evil", "ok", "'-1"]

    def test_tuple_input_returns_list(self):
        result = sanitize_sequence(("=evil", "ok"))
        assert isinstance(result, list)
        assert result == ["'=evil", "ok"]

    def test_mixed_types_all_coerced(self):
        result = sanitize_sequence([None, 1, -1, "=x", True])
        assert result == ["", "1", "'-1", "'=x", "True"]

    def test_generator_input(self):
        """sanitize_sequence works on any iterable, not just lists."""
        def _gen():
            yield "safe"
            yield "=evil"
        assert sanitize_sequence(_gen()) == ["safe", "'=evil"]


# ===========================================================================
# Module surface
# ===========================================================================

class TestModuleSurface:

    def test_public_api_exports(self):
        import app.shared.csv_safety as m
        assert m.__all__ == ["sanitize_cell", "sanitize_row", "sanitize_sequence"]

    def test_dangerous_prefixes_includes_all_known(self):
        """Lock in the prefix list so a future refactor doesn't accidentally
        drop one (e.g., tab — which bypasses quoting heuristics in older
        Excel versions)."""
        import app.shared.csv_safety as m
        assert set(m._DANGEROUS_PREFIXES) == {"=", "+", "-", "@", "\t", "\r"}
