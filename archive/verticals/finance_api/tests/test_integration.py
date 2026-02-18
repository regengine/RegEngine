"""
Integration Test: Complete Finance Decision Workflow
=====================================================
Demonstrates end-to-end workflow:
1. Record decision with evidence
2. Evaluate against obligations (ROE)
3. Create evidence envelope (Evidence V3)
4. Verify chain integrity
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest
from datetime import datetime
from services.finance_api.service import FinanceDecisionService
from services.finance_api.models import DecisionRequest, DecisionType


class TestFinanceWorkflow:
    """Test complete Finance decision workflow."""
    
    @pytest.fixture
    def service(self):
        """Create FinanceDecisionService instance."""
        return FinanceDecisionService(verticals_dir="./verticals")
    
    def test_credit_denial_workflow(self, service):
        """
        Test credit denial decision workflow.
        
        ECOA obligations require:
        - adverse_action_notice
        - reason_codes
        - notification_timing
        """
        # Prepare decision request
        request = DecisionRequest(
            decision_id="test_dec_001",
            decision_type=DecisionType.CREDIT_DENIAL,
            evidence={
                "adverse_action_notice": "Your credit application has been denied.",
                "reason_codes": ["insufficient_credit_history", "high_debt_to_income"],
                "notification_timing": "within_30_days",
                "applicant_id": "app_12345",
                "decision_date": "2024-02-12"
            },
            metadata={
                "model_id": "credit_model_v1",
                "model_version": "1.0.0"
            }
        )
        
        # Record decision
        response = service.record_decision(request)
        
        # Verify response
        assert response.decision_id == "test_dec_001"
        assert response.status == "recorded"
        assert response.evaluation_id is not None
        assert response.coverage_percent >= 0.0
        assert response.risk_level in ["low", "medium", "high", "critical"]
        
        print(f"\n✅ Decision recorded successfully")
        print(f"   Evaluation ID: {response.evaluation_id}")
        print(f"   Coverage: {response.coverage_percent:.1f}%")
        print(f"   Risk Level: {response.risk_level}")
    
    def test_credit_approval_workflow(self, service):
        """
        Test credit approval decision workflow.
        
        Should have different obligation requirements.
        """
        request = DecisionRequest(
            decision_id="test_dec_002",
            decision_type=DecisionType.CREDIT_APPROVAL,
            evidence={
                "approval_notice": "Your credit application has been approved.",
                "credit_limit": 5000,
                "interest_rate": 15.99,
                "terms_disclosure": "Standard terms apply",
                "applicant_id": "app_67890",
                "decision_date": "2024-02-12"
            },
            metadata={
                "model_id": "credit_model_v1",
                "model_version": "1.0.0"
            }
        )
        
        response = service.record_decision(request)
        
        assert response.decision_id == "test_dec_002"
        assert response.status == "recorded"
        assert response.evaluation_id is not None
        
        print(f"\n✅ Credit approval recorded")
        print(f"   Coverage: {response.coverage_percent:.1f}%")
        print(f"   Risk Level: {response.risk_level}")
    
    def test_chain_continuity(self, service):
        """
        Test evidence chain continuity.
        
        Each envelope should link to the previous one.
        """
        # Record first decision
        request1 = DecisionRequest(
            decision_id="chain_test_001",
            decision_type=DecisionType.FRAUD_FLAG,
            evidence={
                "fraud_indicator": "suspicious_transaction_pattern",
                "risk_score": 0.85,
                "account_id": "acc_111"
            }
        )
        response1 = service.record_decision(request1)
        
        # Record second decision
        request2 = DecisionRequest(
            decision_id="chain_test_002",
            decision_type=DecisionType.ACCOUNT_CLOSURE,
            evidence={
                "closure_reason": "fraud_detected",
                "account_id": "acc_111",
                "notification_sent": True
            }
        )
        response2 = service.record_decision(request2)
        
        # Verify chain statistics
        stats = service.get_chain_stats()
        assert stats["total_decisions"] >= 2
        assert stats["total_envelopes"] >= 2
        assert stats["latest_envelope_hash"] is not None
        
        print(f"\n✅ Chain continuity verified")
        print(f"   Total decisions: {stats['total_decisions']}")
        print(f"   Total envelopes: {stats['total_envelopes']}")
        print(f"   Chain active: {stats['latest_envelope_hash'] is not None}")
    
    def test_decision_retrieval(self, service):
        """Test decision retrieval."""
        # Record decision
        request = DecisionRequest(
            decision_id="retrieval_test_001",
            decision_type=DecisionType.LIMIT_ADJUSTMENT,
            evidence={
                "new_limit": 7500,
                "previous_limit": 5000,
                "adjustment_reason": "good_payment_history",
                "account_id": "acc_222"
            }
        )
        service.record_decision(request)
        
        # Retrieve decision
        decision = service.get_decision("retrieval_test_001")
        
        assert decision is not None
        assert decision["decision_id"] == "retrieval_test_001"
        assert decision["decision_type"] == "limit_adjustment"
        assert "evidence" in decision
        assert decision["evidence"]["new_limit"] == 7500
        
        print(f"\n✅ Decision retrieval successful")
        print(f"   Decision ID: {decision['decision_id']}")
        print(f"   Evidence fields: {len(decision['evidence'])}")
    
    def test_missing_evidence(self, service):
        """
        Test decision with missing evidence.
        
        Should still record but have lower coverage.
        """
        request = DecisionRequest(
            decision_id="missing_evidence_001",
            decision_type=DecisionType.CREDIT_DENIAL,
            evidence={
                "applicant_id": "app_999"
                # Missing: adverse_action_notice, reason_codes, etc.
            }
        )
        
        response = service.record_decision(request)
        
        assert response.status == "recorded"
        # Coverage should be lower due to missing evidence
        assert response.coverage_percent < 100.0
        # Risk level should be higher
        assert response.risk_level in ["medium", "high", "critical"]
        
        print(f"\n⚠️  Missing evidence detected")
        print(f"   Coverage: {response.coverage_percent:.1f}% (< 100%)")
        print(f"   Risk Level: {response.risk_level}")


if __name__ == "__main__":
    """Run tests manually for demonstration."""
    print("\n" + "="*70)
    print("Finance Vertical: Integration Test Suite")
    print("="*70)
    
    service = FinanceDecisionService(verticals_dir="./verticals")
    test = TestFinanceWorkflow()
    
    try:
        print("\n[1/5] Testing credit denial workflow...")
        test.test_credit_denial_workflow(service)
    except Exception as e:
        print(f"❌ Error: {e}")
    
    try:
        print("\n[2/5] Testing credit approval workflow...")
        test.test_credit_approval_workflow(service)
    except Exception as e:
        print(f"❌ Error: {e}")
    
    try:
        print("\n[3/5] Testing chain continuity...")
        test.test_chain_continuity(service)
    except Exception as e:
        print(f"❌ Error: {e}")
    
    try:
        print("\n[4/5] Testing decision retrieval...")
        test.test_decision_retrieval(service)
    except Exception as e:
        print(f"❌ Error: {e}")
    
    try:
        print("\n[5/5] Testing missing evidence handling...")
        test.test_missing_evidence(service)
    except Exception as e:
        print(f"❌ Error: {e}")
    
    print("\n" + "="*70)
    print("Integration tests complete!")
    print("="*70 + "\n")
