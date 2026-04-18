"""
Hardening tests for ``kernel.control.schema_validator``.

Covers audit #1343:

* Every object schema sets ``additionalProperties: false`` — typos fail.
* Identifier-ish fields enforce the same allowlist as the codegen stack
  (belt + braces for #1285).
* ``validate_snapshot_contract_functions_exist`` (a) validates
  ``vertical_name`` before path join, (b) keeps the resolved path inside
  ``verticals_root``, (c) uses AST presence-of-function rather than a
  substring scan.
* Validation returns every error in one pass, not just the first.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pytest

from kernel.control.schema_validator import (
    validate_obligations_schema,
    validate_snapshot_contract_functions_exist,
    validate_vertical_schema,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _ok_vertical() -> Dict[str, Any]:
    return {
        "name": "food_beverage",
        "version": "1.0.0",
        "regulators": ["FDA"],
        "regulatory_domains": ["FSMA"],
        "decision_types": ["shipment_receipt"],
        "risk_dimensions": ["bias_risk"],
        "evidence_contract": {
            "shipment_receipt": {"required": ["lot_code", "receive_ts"]}
        },
        "snapshot_contract": {
            "function": "compute_snapshot",
            "inputs": ["decisions"],
            "outputs": ["score"],
        },
        "scoring_weights": {
            "bias": 0.5,
            "drift": 0.5,
        },
    }


def _ok_obligations() -> Dict[str, Any]:
    return [
        {
            "id": "FSMA_204_RECEIVE",
            "citation": "21 CFR 1.1320",
            "regulator": "FDA",
            "domain": "FSMA",
            "description": "Receiving CTE must record lot code and timestamp.",
            "triggering_conditions": {"decision_type": "shipment_receipt"},
            "required_evidence": ["lot_code", "receive_ts"],
        }
    ]


# ---------------------------------------------------------------------------
# Typos are rejected (#1343 part 1)
# ---------------------------------------------------------------------------


class TestVerticalSchemaTypos:
    def test_unknown_top_level_key_rejected(self):
        """Typo like ``regulatorss`` must not pass."""
        vertical = _ok_vertical()
        vertical["regulatorss"] = ["FDA"]
        errors = validate_vertical_schema(vertical)
        assert errors, "extra top-level key must produce an error"
        assert any("regulatorss" in e for e in errors)

    def test_unknown_nested_key_rejected(self):
        """Typo inside ``snapshot_contract`` must not pass."""
        vertical = _ok_vertical()
        vertical["snapshot_contract"]["inputz"] = ["oops"]
        errors = validate_vertical_schema(vertical)
        assert errors, "extra nested key must produce an error"

    def test_valid_vertical_has_no_errors(self):
        assert validate_vertical_schema(_ok_vertical()) == []


# ---------------------------------------------------------------------------
# Identifier patterns (#1343 part 2, defence for #1285)
# ---------------------------------------------------------------------------


class TestVerticalSchemaIdentifierPatterns:
    def test_decision_types_reject_quote(self):
        vertical = _ok_vertical()
        vertical["decision_types"] = ['credit_denial"\nimport os\n#']
        errors = validate_vertical_schema(vertical)
        assert errors

    def test_decision_types_reject_hyphen(self):
        vertical = _ok_vertical()
        vertical["decision_types"] = ["credit-denial"]
        errors = validate_vertical_schema(vertical)
        assert errors

    def test_regulators_reject_lowercase(self):
        vertical = _ok_vertical()
        vertical["regulators"] = ["fda"]
        errors = validate_vertical_schema(vertical)
        assert errors

    def test_domains_reject_lowercase(self):
        vertical = _ok_vertical()
        vertical["regulatory_domains"] = ["fsma"]
        errors = validate_vertical_schema(vertical)
        assert errors


class TestObligationsSchemaIdentifierPatterns:
    def test_obligation_id_reject_lowercase(self):
        data = _ok_obligations()
        data[0]["id"] = "lower"
        errors = validate_obligations_schema(data)
        assert errors

    def test_citation_reject_newline(self):
        data = _ok_obligations()
        data[0]["citation"] = "12 CFR 1002.9\nimport os"
        errors = validate_obligations_schema(data)
        assert errors

    def test_required_evidence_reject_upper(self):
        data = _ok_obligations()
        data[0]["required_evidence"] = ["LotCode"]
        errors = validate_obligations_schema(data)
        assert errors

    def test_unknown_obligation_key_rejected(self):
        data = _ok_obligations()
        data[0]["severity"] = "high"  # unknown
        errors = validate_obligations_schema(data)
        assert errors


# ---------------------------------------------------------------------------
# Multi-error reporting (#1343 part 3)
# ---------------------------------------------------------------------------


class TestMultiErrorReporting:
    def test_all_errors_surface_not_just_first(self):
        """Two independent problems in the same file must both appear."""
        vertical = _ok_vertical()
        vertical["name"] = "BadName"  # wrong case
        vertical["decision_types"] = ["BadDecision"]  # wrong case
        errors = validate_vertical_schema(vertical)
        # Expect at least two distinct error messages.
        assert len(errors) >= 2, f"expected >=2 errors, got {errors}"


# ---------------------------------------------------------------------------
# Path traversal + AST check (#1343 part 4)
# ---------------------------------------------------------------------------


class TestSnapshotContractFunctionsExist:
    def test_traversal_attempt_rejected(self, tmp_path: Path):
        errors = validate_snapshot_contract_functions_exist(
            "../../etc/passwd",
            {"function": "compute_snapshot"},
            verticals_root=tmp_path,
        )
        assert errors
        assert any("safe identifier" in e.lower() for e in errors)

    def test_absolute_path_rejected(self, tmp_path: Path):
        errors = validate_snapshot_contract_functions_exist(
            "/etc",
            {"function": "compute_snapshot"},
            verticals_root=tmp_path,
        )
        assert errors

    def test_missing_file_reports_error(self, tmp_path: Path):
        errors = validate_snapshot_contract_functions_exist(
            "food_beverage",
            {"function": "compute_snapshot"},
            verticals_root=tmp_path,
        )
        assert errors
        assert any("not found" in e for e in errors)

    def test_substring_match_does_not_satisfy(self, tmp_path: Path):
        """A file with the function name only in a comment must fail."""
        vdir = tmp_path / "food_beverage"
        vdir.mkdir()
        (vdir / "snapshot_logic.py").write_text(
            "# compute_snapshot stub\n\ndef other():\n    pass\n",
            encoding="utf-8",
        )
        errors = validate_snapshot_contract_functions_exist(
            "food_beverage",
            {"function": "compute_snapshot"},
            verticals_root=tmp_path,
        )
        assert errors
        assert any("not defined" in e for e in errors)

    def test_real_function_definition_passes(self, tmp_path: Path):
        vdir = tmp_path / "food_beverage"
        vdir.mkdir()
        (vdir / "snapshot_logic.py").write_text(
            "def compute_snapshot(x):\n    return x\n",
            encoding="utf-8",
        )
        errors = validate_snapshot_contract_functions_exist(
            "food_beverage",
            {"function": "compute_snapshot"},
            verticals_root=tmp_path,
        )
        assert errors == []

    def test_async_function_definition_passes(self, tmp_path: Path):
        vdir = tmp_path / "food_beverage"
        vdir.mkdir()
        (vdir / "snapshot_logic.py").write_text(
            "async def compute_snapshot(x):\n    return x\n",
            encoding="utf-8",
        )
        errors = validate_snapshot_contract_functions_exist(
            "food_beverage",
            {"function": "compute_snapshot"},
            verticals_root=tmp_path,
        )
        assert errors == []

    def test_syntax_error_in_target_surfaces(self, tmp_path: Path):
        vdir = tmp_path / "food_beverage"
        vdir.mkdir()
        (vdir / "snapshot_logic.py").write_text(
            "def compute_snapshot(x\n    # missing close paren\n",
            encoding="utf-8",
        )
        errors = validate_snapshot_contract_functions_exist(
            "food_beverage",
            {"function": "compute_snapshot"},
            verticals_root=tmp_path,
        )
        assert errors
        assert any("not valid Python" in e for e in errors)
