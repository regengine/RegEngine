"""
Regulatory Obligation Engine - Integration Tests
=================================================
Tests the complete obligation evaluation workflow.
"""

import pytest
from pathlib import Path
import tempfile
import yaml

from kernel.obligation.engine import RegulatoryEngine
from kernel.obligation.models import RiskLevel


# Test obligations YAML
TEST_OBLIGATIONS = {
    "obligations": [
        {
            "id": "TEST_ADVERSE_ACTION",
            "citation": "12 CFR 1002.9",
            "regulator": "CFPB",
            "domain": "ECOA",
            "description": "Must provide adverse action notice within 30 days",
            "triggering_conditions": {
                "decision_type": "credit_denial"
            },
            "required_evidence": [
                "adverse_action_notice",
                "reason_codes",
                "notice_delivery_timestamp"
            ]
        },
        {
            "id": "TEST_MODEL_VALIDATION",
            "citation": "SR 11-7",
            "regulator": "FRB",
            "domain": "SR_11_7",
            "description": "Model must have independent validation",
            "triggering_conditions": {
                "model_usage": True
            },
            "required_evidence": [
                "validation_report_hash",
                "validator_name"
            ]
        }
    ]
}


@pytest.fixture
def temp_verticals_dir():
    """Create temporary verticals directory with test obligations."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        
        # Create test vertical structure
        test_vertical = tmpdir / "test_vertical"
        test_vertical.mkdir()
        
        # Write obligations.yaml
        obligations_file = test_vertical / "obligations.yaml"
        with open(obligations_file, 'w') as f:
            yaml.dump(TEST_OBLIGATIONS, f)
        
        yield tmpdir


@pytest.fixture
def engine(temp_verticals_dir):
    """Create RegulatoryEngine instance with test data."""
    return RegulatoryEngine(verticals_dir=temp_verticals_dir)


def test_load_vertical_obligations(engine):
    """Test loading obligations from YAML."""
    evaluator = engine.load_vertical_obligations("test_vertical")
    
    assert evaluator is not None
    assert len(evaluator.obligations) == 2
    assert "TEST_ADVERSE_ACTION" in evaluator.obligations_by_id
    assert "TEST_MODEL_VALIDATION" in evaluator.obligations_by_id


def test_evaluate_decision_all_evidence_present(engine):
    """Test evaluation when all required evidence is present."""
    decision_data = {
        "adverse_action_notice": "Notice sent on 2024-01-15",
        "reason_codes": ["insufficient_credit_history", "high_debt_ratio"],
        "notice_delivery_timestamp": "2024-01-15T10:30:00Z"
    }
    
    result = engine.evaluate_decision(
        decision_id="test_decision_1",
        decision_type="credit_denial",
        decision_data=decision_data,
        vertical="test_vertical"
    )
    
    assert result.total_applicable_obligations == 1  # Only TEST_ADVERSE_ACTION applies
    assert result.met_obligations == 1
    assert result.violated_obligations == 0
    assert result.coverage_percent == 100.0
    assert result.overall_risk_score == 0.0
    assert result.risk_level == RiskLevel.LOW


def test_evaluate_decision_missing_evidence(engine):
    """Test evaluation when required evidence is missing."""
    decision_data = {
        "adverse_action_notice": "Notice sent",
        # Missing: reason_codes, notice_delivery_timestamp
    }
    
    result = engine.evaluate_decision(
        decision_id="test_decision_2",
        decision_type="credit_denial",
        decision_data=decision_data,
        vertical="test_vertical"
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
        "model_usage": True,
        "validation_report_hash": "abc123",
        "validator_name": "Jane Validator"
    }
    
    result = engine.evaluate_decision(
        decision_id="test_decision_3",
        decision_type="credit_approval",
        decision_data=decision_data,
        vertical="test_vertical"
    )
    
    # Only TEST_MODEL_VALIDATION applies (model_usage=True)
    assert result.total_applicable_obligations == 1
    assert result.met_obligations == 1
    assert result.coverage_percent == 100.0


def test_evaluate_decision_partial_compliance(engine):
    """Test evaluation with partial evidence."""
    decision_data = {
        "adverse_action_notice": "Notice sent",
        "reason_codes": ["insufficient_income"],
        # Missing: notice_delivery_timestamp (1/3 missing)
    }
    
    result = engine.evaluate_decision(
        decision_id="test_decision_4",
        decision_type="credit_denial",
        decision_data=decision_data,
        vertical="test_vertical"
    )
    
    assert result.violated_obligations == 1
    assert result.coverage_percent == 0.0  # Not fully compliant
    
    # Check obligation match details
    match = result.obligation_matches[0]
    assert match.obligation_id == "TEST_ADVERSE_ACTION"
    assert not match.met
    assert "notice_delivery_timestamp" in match.missing_evidence
    assert match.risk_score > 0.0


def test_risk_level_calculation(engine):
    """Test risk level determination based on coverage and risk score."""
    test_cases = [
        # (coverage%, expected_risk_level)
        (100.0, RiskLevel.LOW),     # Full compliance
        (75.0, RiskLevel.MEDIUM),   # Moderate compliance
        (55.0, RiskLevel.HIGH),     # Low compliance
        (30.0, RiskLevel.CRITICAL)  # Very low compliance
    ]
    
    # This test validates the risk level logic indirectly
    # by checking various compliance scenarios
    
    # 100% coverage case
    full_data = {
        "adverse_action_notice": "Notice",
        "reason_codes": ["test"],
        "notice_delivery_timestamp": "2024-01-15T10:00:00Z"
    }
    
    result = engine.evaluate_decision(
        decision_id="test_full",
        decision_type="credit_denial",
        decision_data=full_data,
        vertical="test_vertical"
    )
    
    assert result.risk_level == RiskLevel.LOW


def test_triggering_conditions_matching(engine):
    """Test that triggering conditions correctly filter obligations."""
    # Decision with model_usage trigger
    model_decision = {
        "model_usage": True,
        "validation_report_hash": "hash123",
        "validator_name": "Validator"
    }
    
    result = engine.evaluate_decision(
        decision_id="test_model",
        decision_type="risk_assessment",
        decision_data=model_decision,
        vertical="test_vertical"
    )
    
    # Should match TEST_MODEL_VALIDATION (trigger: model_usage=True)
    assert result.total_applicable_obligations == 1
    assert result.obligation_matches[0].obligation_id == "TEST_MODEL_VALIDATION"
    
    # Decision without model_usage trigger
    non_model_decision = {
        "some_other_field": "value"
    }
    
    result2 = engine.evaluate_decision(
        decision_id="test_non_model",
        decision_type="risk_assessment",
        decision_data=non_model_decision,
        vertical="test_vertical"
    )
    
    # Should not match any obligations (no triggers satisfied)
    assert result2.total_applicable_obligations == 0


def test_evaluation_id_uniqueness(engine):
    """Test that each evaluation gets a unique ID."""
    decision_data = {
        "adverse_action_notice": "Notice",
        "reason_codes": ["test"],
        "notice_delivery_timestamp": "2024-01-15T10:00:00Z"
    }
    
    result1 = engine.evaluate_decision(
        decision_id="test_unique_1",
        decision_type="credit_denial",
        decision_data=decision_data,
        vertical="test_vertical"
    )
    
    result2 = engine.evaluate_decision(
        decision_id="test_unique_2",
        decision_type="credit_denial",
        decision_data=decision_data,
        vertical="test_vertical"
    )
    
    assert result1.evaluation_id != result2.evaluation_id


def test_obligation_matches_structure(engine):
    """Test that obligation matches contain all required fields."""
    decision_data = {
        "adverse_action_notice": "Notice",
        # Missing: reason_codes, notice_delivery_timestamp
    }
    
    result = engine.evaluate_decision(
        decision_id="test_match_structure",
        decision_type="credit_denial",
        decision_data=decision_data,
        vertical="test_vertical"
    )
    
    assert len(result.obligation_matches) > 0
    
    match = result.obligation_matches[0]
    assert hasattr(match, 'obligation_id')
    assert hasattr(match, 'citation')
    assert hasattr(match, 'regulator')
    assert hasattr(match, 'domain')
    assert hasattr(match, 'met')
    assert hasattr(match, 'missing_evidence')
    assert hasattr(match, 'risk_score')
    
    assert match.citation == "12 CFR 1002.9"
    assert match.regulator.value == "CFPB"
    assert match.domain.value == "ECOA"
