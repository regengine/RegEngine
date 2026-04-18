"""
Regulatory Obligation Engine - Integration Tests
=================================================
Tests the complete obligation evaluation workflow against FSMA 204 fixtures.

Rewritten from the legacy banking-domain fixtures that caused collection
failures (#1310 — ``RegulatoryDomain.ECOA`` no longer exists) and fixed the
import path (``regulatory_engine.*`` → ``kernel.obligation.*``).
"""

import pytest
from pathlib import Path
import tempfile
import yaml

from kernel.obligation.engine import RegulatoryEngine
from kernel.obligation.models import RiskLevel


# FSMA-only test fixtures.
TEST_OBLIGATIONS = {
    "obligations": [
        {
            "id": "FSMA_204_RECEIVE",
            "citation": "21 CFR 1.1320",
            "regulator": "FDA",
            "domain": "FSMA",
            "description": "Receiving CTE must record lot code and timestamp.",
            "triggering_conditions": {"decision_type": "shipment_receipt"},
            "required_evidence": [
                "lot_code",
                "receive_timestamp",
                "source_tlc",
            ],
        },
        {
            "id": "FSMA_204_TRANSFORMATION",
            "citation": "21 CFR 1.1340",
            "regulator": "FDA",
            "domain": "FSMA",
            "description": "Transformation CTE must link inputs to outputs.",
            "triggering_conditions": {"transformation_event": True},
            "required_evidence": [
                "input_tlcs",
                "output_tlc",
                "transformation_timestamp",
            ],
        },
    ]
}


@pytest.fixture
def temp_verticals_dir():
    """Create temporary verticals directory with FSMA test obligations."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        test_vertical = tmpdir / "food_beverage"
        test_vertical.mkdir()

        obligations_file = test_vertical / "obligations.yaml"
        with open(obligations_file, "w", encoding="utf-8") as f:
            yaml.dump(TEST_OBLIGATIONS, f)

        yield tmpdir


@pytest.fixture
def engine(temp_verticals_dir):
    """Create RegulatoryEngine instance with test data."""
    return RegulatoryEngine(verticals_dir=temp_verticals_dir)


def test_load_vertical_obligations(engine):
    """Test loading obligations from YAML."""
    evaluator = engine.load_vertical_obligations("food_beverage")

    assert evaluator is not None
    assert len(evaluator.obligations) == 2
    assert "FSMA_204_RECEIVE" in evaluator.obligations_by_id
    assert "FSMA_204_TRANSFORMATION" in evaluator.obligations_by_id


def test_evaluate_decision_all_evidence_present(engine):
    """Test evaluation when all required evidence is present."""
    decision_data = {
        "lot_code": "LOT-ABC-001",
        "receive_timestamp": "2026-04-15T10:30:00Z",
        "source_tlc": "supplier-xyz-001",
    }

    result = engine.evaluate_decision(
        decision_id="test_decision_1",
        decision_type="shipment_receipt",
        decision_data=decision_data,
        vertical="food_beverage",
    )

    assert result.total_applicable_obligations == 1  # Only RECEIVE applies
    assert result.met_obligations == 1
    assert result.violated_obligations == 0
    assert result.coverage_percent == 100.0
    assert result.overall_risk_score == 0.0
    assert result.risk_level == RiskLevel.LOW


def test_evaluate_decision_missing_evidence(engine):
    """Test evaluation when required evidence is missing."""
    decision_data = {
        "lot_code": "LOT-ABC-001",
        # Missing: receive_timestamp, source_tlc
    }

    result = engine.evaluate_decision(
        decision_id="test_decision_2",
        decision_type="shipment_receipt",
        decision_data=decision_data,
        vertical="food_beverage",
    )

    assert result.total_applicable_obligations == 1
    assert result.met_obligations == 0
    assert result.violated_obligations == 1
    assert result.coverage_percent == 0.0
    assert result.overall_risk_score > 0.5  # Missing 2/3 fields
    assert result.risk_level == RiskLevel.CRITICAL


def test_evaluate_decision_multiple_obligations(engine):
    """Test evaluation against multiple obligations."""
    decision_data = {
        "transformation_event": True,
        "input_tlcs": ["tlc-1", "tlc-2"],
        "output_tlc": "tlc-3",
        "transformation_timestamp": "2026-04-15T11:00:00Z",
    }

    result = engine.evaluate_decision(
        decision_id="test_decision_3",
        decision_type="batch_split",
        decision_data=decision_data,
        vertical="food_beverage",
    )

    # Only TRANSFORMATION applies (transformation_event=True)
    assert result.total_applicable_obligations == 1
    assert result.met_obligations == 1
    assert result.coverage_percent == 100.0


def test_evaluate_decision_partial_compliance(engine):
    """Test evaluation with partial evidence."""
    decision_data = {
        "lot_code": "LOT-ABC-001",
        "receive_timestamp": "2026-04-15T10:30:00Z",
        # Missing: source_tlc (1/3 missing)
    }

    result = engine.evaluate_decision(
        decision_id="test_decision_4",
        decision_type="shipment_receipt",
        decision_data=decision_data,
        vertical="food_beverage",
    )

    assert result.violated_obligations == 1
    assert result.coverage_percent == 0.0  # Not fully compliant

    match = result.obligation_matches[0]
    assert match.obligation_id == "FSMA_204_RECEIVE"
    assert not match.met
    assert "source_tlc" in match.missing_evidence
    assert match.risk_score > 0.0


def test_risk_level_calculation(engine):
    """Full-compliance case lands in LOW risk."""
    full_data = {
        "lot_code": "LOT-1",
        "receive_timestamp": "2026-04-15T10:00:00Z",
        "source_tlc": "tlc-1",
    }

    result = engine.evaluate_decision(
        decision_id="test_full",
        decision_type="shipment_receipt",
        decision_data=full_data,
        vertical="food_beverage",
    )

    assert result.risk_level == RiskLevel.LOW


def test_triggering_conditions_matching(engine):
    """Test that triggering conditions correctly filter obligations."""
    # Decision with transformation_event trigger
    tx_decision = {
        "transformation_event": True,
        "input_tlcs": ["a"],
        "output_tlc": "b",
        "transformation_timestamp": "2026-04-15T10:00:00Z",
    }

    result = engine.evaluate_decision(
        decision_id="test_tx",
        decision_type="batch_split",
        decision_data=tx_decision,
        vertical="food_beverage",
    )

    assert result.total_applicable_obligations == 1
    assert result.obligation_matches[0].obligation_id == "FSMA_204_TRANSFORMATION"

    # Decision with no triggering condition satisfied
    non_matching = {"some_other_field": "value"}

    result2 = engine.evaluate_decision(
        decision_id="test_none",
        decision_type="unknown",
        decision_data=non_matching,
        vertical="food_beverage",
    )

    assert result2.total_applicable_obligations == 0


def test_evaluation_id_uniqueness(engine):
    """Each evaluation gets a unique ID."""
    decision_data = {
        "lot_code": "LOT-1",
        "receive_timestamp": "2026-04-15T10:00:00Z",
        "source_tlc": "tlc-1",
    }

    result1 = engine.evaluate_decision(
        decision_id="test_unique_1",
        decision_type="shipment_receipt",
        decision_data=decision_data,
        vertical="food_beverage",
    )

    result2 = engine.evaluate_decision(
        decision_id="test_unique_2",
        decision_type="shipment_receipt",
        decision_data=decision_data,
        vertical="food_beverage",
    )

    assert result1.evaluation_id != result2.evaluation_id


def test_obligation_matches_structure(engine):
    """Obligation matches contain all required fields."""
    decision_data = {
        "lot_code": "LOT-1",
        # Missing: receive_timestamp, source_tlc
    }

    result = engine.evaluate_decision(
        decision_id="test_match_structure",
        decision_type="shipment_receipt",
        decision_data=decision_data,
        vertical="food_beverage",
    )

    assert len(result.obligation_matches) > 0

    match = result.obligation_matches[0]
    assert hasattr(match, "obligation_id")
    assert hasattr(match, "citation")
    assert hasattr(match, "regulator")
    assert hasattr(match, "domain")
    assert hasattr(match, "met")
    assert hasattr(match, "missing_evidence")
    assert hasattr(match, "risk_score")

    assert match.citation == "21 CFR 1.1320"
    assert match.regulator.value == "FDA"
    assert match.domain.value == "FSMA"
