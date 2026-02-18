"""
Auto-generated model tests for finance vertical.
"""

import pytest
from pydantic import ValidationError
from ..models import DecisionType, DecisionRequest


def test_decision_type_enum():
    """Test DecisionType enum."""
    # Valid decision types
    assert DecisionType.CREDIT_APPROVAL == "credit_approval"
    assert DecisionType.CREDIT_DENIAL == "credit_denial"
    assert DecisionType.LIMIT_ADJUSTMENT == "limit_adjustment"
    
    # Check all enum values
    types = [e.value for e in DecisionType]
    assert "credit_approval" in types
    assert "credit_denial" in types
    assert "limit_adjustment" in types


def test_decision_request_validation():
    """Test DecisionRequest validation."""
    # Valid request
    valid_request = DecisionRequest(
        decision_id="test_001",
        decision_type=DecisionType.CREDIT_APPROVAL,
        evidence={"score": 750},
        metadata={"model_id": "v1.0"}
    )
    assert valid_request.decision_id == "test_001"
    assert valid_request.decision_type == DecisionType.CREDIT_APPROVAL
    
    # Missing required field should raise ValidationError
    with pytest.raises(ValidationError):
        DecisionRequest(
            decision_type=DecisionType.CREDIT_APPROVAL,
            evidence={},
            metadata={}
            # Missing decision_id
        )
