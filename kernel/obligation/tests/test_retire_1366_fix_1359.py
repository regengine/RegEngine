"""
Tests for #1366 (retire kernel/control + obligation/routes) and
#1359 (FSMA-only Regulator enum, RiskWeight/ComplianceScore reserved,
       _compute_overall_risk docstring matches code).
"""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path


# ---------------------------------------------------------------------------
# #1366 — kernel/control deleted
# ---------------------------------------------------------------------------


def test_kernel_control_directory_gone() -> None:
    """kernel/control/ must be fully deleted (#1366)."""
    control_dir = Path(__file__).parent.parent.parent / "control"
    assert not control_dir.exists(), (
        f"kernel/control/ still exists at {control_dir} — should be deleted per #1366."
    )


def test_kernel_control_not_importable() -> None:
    """kernel.control must not be importable after retirement (#1366)."""
    try:
        importlib.import_module("kernel.control")
        raise AssertionError(
            "kernel.control is still importable — kernel/control/ should have been "
            "deleted as part of #1366."
        )
    except ModuleNotFoundError:
        pass  # expected


def test_obligation_routes_not_importable() -> None:
    """kernel.obligation.routes must not be importable after retirement (#1366)."""
    try:
        importlib.import_module("kernel.obligation.routes")
        raise AssertionError(
            "kernel.obligation.routes is still importable — routes.py should have "
            "been deleted as part of #1366."
        )
    except ModuleNotFoundError:
        pass  # expected


# ---------------------------------------------------------------------------
# #1359 — Regulator enum is FDA-only
# ---------------------------------------------------------------------------


def test_regulator_enum_fda_only() -> None:
    """Regulator must contain only FDA after banking-regulator removal (#1359)."""
    from kernel.obligation.models import Regulator

    members = {m.value for m in Regulator}
    assert members == {"FDA"}, (
        f"Regulator enum contains unexpected values: {members}. "
        "OCC, CFPB, FRB, FDIC, NCUA were removed in #1359."
    )


def test_regulator_banking_names_gone() -> None:
    """Banking regulator names must not exist on the Regulator enum (#1359)."""
    from kernel.obligation.models import Regulator

    for name in ("OCC", "CFPB", "FRB", "FDIC", "NCUA"):
        assert not hasattr(Regulator, name), (
            f"Regulator.{name} still present — should have been removed in #1359."
        )


# ---------------------------------------------------------------------------
# #1359 — RiskWeight / ComplianceScore present but documented as reserved
# ---------------------------------------------------------------------------


def test_risk_weight_exists_as_reserved() -> None:
    """RiskWeight must exist (for compat re-export) and be documented reserved (#1359)."""
    from kernel.obligation.models import RiskWeight

    assert RiskWeight is not None
    doc = RiskWeight.__doc__ or ""
    assert "RESERVED" in doc, (
        "RiskWeight docstring must contain 'RESERVED' to signal it is not used "
        "by the current FSMA evaluator (#1359)."
    )


def test_compliance_score_exists_as_reserved() -> None:
    """ComplianceScore must exist (for compat re-export) and be documented reserved (#1359)."""
    from kernel.obligation.models import ComplianceScore

    assert ComplianceScore is not None
    doc = ComplianceScore.__doc__ or ""
    assert "RESERVED" in doc, (
        "ComplianceScore docstring must contain 'RESERVED' to signal it is not "
        "used by the current FSMA evaluator (#1359)."
    )


# ---------------------------------------------------------------------------
# #1359 — _compute_overall_risk docstring says "unweighted mean"
# ---------------------------------------------------------------------------


def test_compute_overall_risk_docstring_says_unweighted_mean() -> None:
    """_compute_overall_risk docstring must say 'unweighted mean' to match code (#1359)."""
    from kernel.obligation.evaluator import ObligationEvaluator

    doc = inspect.getdoc(ObligationEvaluator._compute_overall_risk) or ""
    assert "unweighted mean" in doc.lower(), (
        f"_compute_overall_risk docstring must say 'unweighted mean'. Got: {doc!r}"
    )


def test_compute_overall_risk_is_flat_mean() -> None:
    """_compute_overall_risk must return the arithmetic mean of risk_scores (#1359)."""
    from unittest.mock import MagicMock
    from kernel.obligation.evaluator import ObligationEvaluator
    from kernel.obligation.models import ObligationMatch, Regulator, RegulatoryDomain

    def _match(score: float) -> ObligationMatch:
        return ObligationMatch(
            obligation_id="X",
            citation="21 CFR 1.0",
            regulator=Regulator.FDA,
            domain=RegulatoryDomain.FSMA,
            met=score == 0.0,
            missing_evidence=[],
            risk_score=score,
        )

    evaluator = ObligationEvaluator.__new__(ObligationEvaluator)
    matches = [_match(0.0), _match(0.5), _match(1.0)]
    result = evaluator._compute_overall_risk(matches)
    assert abs(result - 0.5) < 1e-9, f"Expected 0.5, got {result}"
