"""
Hardening tests for ``kernel.control.compiler``.

Covers audit findings:

* **#1302** — ``raise ValidationError(str)`` was a ``TypeError`` under
  Pydantic v2; ``.dict()`` is deprecated. Compiler now raises
  :class:`SchemaValidationError` (a ``ValueError``) and uses
  ``.model_dump()``.
* **#1305** — ``_register_vertical`` raised ``NameError`` because
  ``datetime`` was not imported. The ``datetime`` import now lives at the
  module level and registration is clearly marked as a stub via a warning.

The compiler itself is orphaned (#1366) — no app imports
``kernel.control.compiler`` today. These tests are the safety net for
anyone who later wires it up.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict
from unittest.mock import patch, MagicMock

import pytest
import yaml

from kernel.control.compiler import (
    CompilationResult,
    SchemaValidationError,
    VerticalCompiler,
    VerticalMetadata,
    ObligationDefinition,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _valid_vertical_dict() -> Dict[str, Any]:
    return {
        "name": "food_beverage",
        "version": "1.0.0",
        "regulators": ["FDA"],
        "regulatory_domains": ["FSMA"],
        "decision_types": ["shipment_receipt"],
        "risk_dimensions": ["bias_risk"],
        "evidence_contract": {
            "shipment_receipt": {"required": ["lot_code", "receive_ts"]},
        },
        "snapshot_contract": {
            "function": "compute_snapshot",
            "inputs": ["decisions"],
            "outputs": ["score"],
        },
        "scoring_weights": {
            "bias": 0.25,
            "drift": 0.25,
            "documentation": 0.25,
            "regulatory_mapping": 0.25,
        },
    }


def _valid_obligations_dict() -> Dict[str, Any]:
    return {
        "obligations": [
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
    }


@pytest.fixture
def compiler_with_vertical(tmp_path: Path):
    """A compiler pointed at a real on-disk vertical yaml."""
    verticals = tmp_path / "verticals" / "food_beverage"
    verticals.mkdir(parents=True)
    (verticals / "vertical.yaml").write_text(
        yaml.safe_dump(_valid_vertical_dict()), encoding="utf-8"
    )
    (verticals / "obligations.yaml").write_text(
        yaml.safe_dump(_valid_obligations_dict()), encoding="utf-8"
    )

    compiler = VerticalCompiler(
        verticals_dir=tmp_path / "verticals",
        services_dir=tmp_path / "services",
        output_dir=tmp_path / "out",
    )
    return compiler


# ---------------------------------------------------------------------------
# #1305 — _register_vertical no longer crashes with NameError
# ---------------------------------------------------------------------------


class TestRegisterVerticalNoNameError:
    def test_register_vertical_does_not_raise(self):
        """datetime must be importable at module level."""
        compiler = VerticalCompiler(Path("/tmp"), Path("/tmp"), Path("/tmp"))
        meta = VerticalMetadata(**_valid_vertical_dict())
        # Must not raise NameError.
        compiler._register_vertical("food_beverage", meta)

    def test_register_vertical_appends_stub_warning(self):
        """The stub state must be visible in the compilation result."""
        compiler = VerticalCompiler(Path("/tmp"), Path("/tmp"), Path("/tmp"))
        meta = VerticalMetadata(**_valid_vertical_dict())
        compiler._register_vertical("food_beverage", meta)
        assert any("stub" in w.lower() for w in compiler.warnings)


# ---------------------------------------------------------------------------
# #1302 — Schema validation errors are readable, not TypeErrors
# ---------------------------------------------------------------------------


class TestSchemaValidationErrorMessages:
    def test_bad_scoring_weights_surfaces_readable_error(self, compiler_with_vertical):
        """Scoring weights summing to !=1.0 should produce a clear error."""
        verticals_dir = compiler_with_vertical.verticals_dir
        vertical = _valid_vertical_dict()
        vertical["scoring_weights"] = {"bias": 0.7}  # sums to 0.7
        (verticals_dir / "food_beverage" / "vertical.yaml").write_text(
            yaml.safe_dump(vertical), encoding="utf-8"
        )

        result = compiler_with_vertical.compile_vertical("food_beverage")

        assert result.compilation_status == "failed"
        # The error must be the readable SchemaValidationError message,
        # NOT the Pydantic TypeError repr.
        assert any("Scoring weights must sum" in e for e in result.errors)
        assert not any("line_errors" in e for e in result.errors), (
            "Pydantic TypeError leaked into the result"
        )

    def test_bad_vertical_schema_raises_schema_validation_error(
        self, compiler_with_vertical
    ):
        """Direct call to ``_validate_schemas`` with bad input raises
        SchemaValidationError (a ValueError), not TypeError."""
        vertical = _valid_vertical_dict()
        # Make scoring weights invalid
        vertical["scoring_weights"] = {"bias": 2.0}
        meta = VerticalMetadata(**vertical)
        obligations = [
            ObligationDefinition(**o) for o in _valid_obligations_dict()["obligations"]
        ]

        with pytest.raises(SchemaValidationError) as exc_info:
            compiler_with_vertical._validate_schemas(meta, obligations)

        # ValueError is the parent — make sure we still subclass sensibly.
        assert isinstance(exc_info.value, ValueError)


# ---------------------------------------------------------------------------
# End-to-end: the compiler runs through on a valid vertical
# ---------------------------------------------------------------------------


class TestCompilerHappyPath:
    def test_compiles_valid_vertical_without_crashing(self, compiler_with_vertical):
        """A valid vertical should compile without raising.

        ``_update_openapi_spec`` and ``_register_vertical`` may append
        warnings (registration is a stub) but must not crash.
        """
        result = compiler_with_vertical.compile_vertical("food_beverage")
        # Must not raise — the NameError from #1305 and the TypeError from
        # #1302 would both have landed us in the "failed" branch even on
        # valid input before this fix.
        assert isinstance(result, CompilationResult)
        # With valid input the schema step passes; generation happens.
        assert result.compilation_status == "success", (
            f"Expected success, got errors: {result.errors}"
        )
        # Stub-warning from registration must surface.
        assert any("stub" in w.lower() for w in result.warnings)
