"""
Finance API Test Suite
======================
End-to-end tests for Finance vertical API.

Tests complete workflow:
1. Record decision
2. Get decision
3. Get stats
4. Get snapshot
"""

import requests
import json
from datetime import datetime

# API base URL
BASE_URL = "http://localhost:8000"


def print_section(title):
    """Print section header."""
    print("\n" + "="*70)
    print(f"  {title}")
    print("="*70)


def test_health():
    """Test health endpoints."""
    print_section("1. Health Checks")
    
    # Global health
    response = requests.get(f"{BASE_URL}/health")
    print(f"\nGlobal Health: {response.status_code}")
    print(json.dumps(response.json(), indent=2))
    
    # Finance health
    response = requests.get(f"{BASE_URL}/v1/finance/health")
    print(f"\nFinance Health: {response.status_code}")
    print(json.dumps(response.json(), indent=2))
    
    # ROE health
    response = requests.get(f"{BASE_URL}/v1/obligations/health")
    print(f"\nROE Health: {response.status_code}")
    print(json.dumps(response.json(), indent=2))
    
    # Evidence health
    response = requests.get(f"{BASE_URL}/v1/evidence/health")
    print(f"\nEvidence Health: {response.status_code}")
    print(json.dumps(response.json(), indent=2))


def test_record_credit_denial():
    """Test recording a credit denial decision."""
    print_section("2. Record Credit Denial Decision")
    
    decision = {
        "decision_id": "test_dec_001",
        "decision_type": "credit_denial",
        "evidence": {
            "adverse_action_notice": "Your credit application has been denied due to insufficient credit history.",
            "reason_codes": ["insufficient_credit_history", "high_debt_to_income"],
            "notification_timing": "within_30_days",
            "applicant_id": "app_12345",
            "decision_date": "2024-02-12",
            "credit_score": 620,
            "income": 45000,
            "debt_to_income": 0.48
        },
        "metadata": {
            "model_id": "credit_model_v1",
            "model_version": "1.0.0",
            "decision_timestamp": datetime.utcnow().isoformat()
        }
    }
    
    print(f"\nRequest:")
    print(json.dumps(decision, indent=2))
    
    response = requests.post(
        f"{BASE_URL}/v1/finance/decision/record",
        json=decision
    )
    
    print(f"\nResponse: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print(json.dumps(result, indent=2))
        print(f"\n✅ Decision recorded successfully!")
        print(f"   Evaluation ID: {result.get('evaluation_id')}")
        print(f"   Coverage: {result.get('coverage_percent', 0):.1f}%")
        print(f"   Risk Level: {result.get('risk_level')}")
        return result
    else:
        print(f"❌ Error: {response.text}")
        return None


def test_record_credit_approval():
    """Test recording a credit approval decision."""
    print_section("3. Record Credit Approval Decision")
    
    decision = {
        "decision_id": "test_dec_002",
        "decision_type": "credit_approval",
        "evidence": {
            "approval_notice": "Your credit application has been approved!",
            "credit_limit": 5000,
            "interest_rate": 15.99,
            "terms_disclosure": "Standard terms and conditions apply. APR: 15.99%",
            "applicant_id": "app_67890",
            "decision_date": "2024-02-12",
            "credit_score": 720,
            "income": 75000,
            "debt_to_income": 0.25
        },
        "metadata": {
            "model_id": "credit_model_v1",
            "model_version": "1.0.0"
        }
    }
    
    response = requests.post(
        f"{BASE_URL}/v1/finance/decision/record",
        json=decision
    )
    
    print(f"Response: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print(json.dumps(result, indent=2))
        print(f"\n✅ Approval recorded!")
        return result
    else:
        print(f"❌ Error: {response.text}")
        return None


def test_get_decision(decision_id):
    """Test retrieving a decision."""
    print_section(f"4. Retrieve Decision: {decision_id}")
    
    response = requests.get(f"{BASE_URL}/v1/finance/decision/{decision_id}")
    
    print(f"Response: {response.status_code}")
    if response.status_code == 200:
        decision = response.json()
        print(json.dumps(decision, indent=2))
        print(f"\n✅ Decision retrieved!")
        return decision
    else:
        print(f"❌ Error: {response.text}")
        return None


def test_get_stats():
    """Test getting Finance API statistics."""
    print_section("5. Finance API Statistics")
    
    response = requests.get(f"{BASE_URL}/v1/finance/stats")
    
    print(f"Response: {response.status_code}")
    if response.status_code == 200:
        stats = response.json()
        print(json.dumps(stats, indent=2))
        print(f"\n✅ Stats retrieved!")
        print(f"   Decisions recorded: {stats.get('decisions_recorded')}")
        print(f"   Evidence envelopes: {stats.get('evidence_envelopes')}")
        print(f"   Chain status: {stats.get('chain_status')}")
        return stats
    else:
        print(f"❌ Error: {response.text}")
        return None


def test_get_snapshot():
    """Test getting compliance snapshot."""
    print_section("6. Compliance Snapshot")
    
    response = requests.get(f"{BASE_URL}/v1/finance/snapshot")
    
    print(f"Response: {response.status_code}")
    if response.status_code == 200:
        snapshot = response.json()
        print(json.dumps(snapshot, indent=2))
        print(f"\n✅ Snapshot computed!")
        print(f"   Total Compliance: {snapshot.get('total_compliance_score', 0):.1f}")
        print(f"   Bias Score: {snapshot.get('bias_score', 0):.1f}")
        print(f"   Drift Score: {snapshot.get('drift_score', 0):.1f}")
        print(f"   Documentation: {snapshot.get('documentation_score', 0):.1f}")
        print(f"   Regulatory: {snapshot.get('regulatory_mapping_score', 0):.1f}")
        print(f"   Risk Level: {snapshot.get('risk_level')}")
        return snapshot
    else:
        print(f"❌ Error: {response.text}")
        return None


def test_fraud_flag():
    """Test fraud detection decision."""
    print_section("7. Record Fraud Flag Decision")
    
    decision = {
        "decision_id": "test_dec_003",
        "decision_type": "fraud_flag",
        "evidence": {
            "fraud_indicator": "suspicious_transaction_pattern",
            "risk_score": 0.92,
            "account_id": "acc_99999",
            "transaction_ids": ["txn_001", "txn_002", "txn_003"],
            "detection_timestamp": datetime.utcnow().isoformat()
        },
        "metadata": {
            "model_id": "fraud_detection_v2",
            "model_version": "2.1.0"
        }
    }
    
    response = requests.post(
        f"{BASE_URL}/v1/finance/decision/record",
        json=decision
    )
    
    print(f"Response: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print(json.dumps(result, indent=2))
        print(f"\n✅ Fraud flag recorded!")
        return result
    else:
        print(f"❌ Error: {response.text}")
        return None


def main():
    """Run all tests."""
    print("\n" + "█"*70)
    print("█" + " "*68 + "█")
    print("█" + "  RegEngine Finance API - End-to-End Test Suite".center(68) + "█")
    print("█" + " "*68 + "█")
    print("█"*70)
    
    try:
        # Test 1: Health checks
        test_health()
        
        # Test 2-3: Record decisions
        denial_result = test_record_credit_denial()
        approval_result = test_record_credit_approval()
        
        # Test 4: Retrieve decision
        if denial_result:
            test_get_decision(denial_result.get("decision_id"))
        
        # Test 5: Get stats
        test_get_stats()
        
        # Test 6: Get snapshot
        test_get_snapshot()
        
        # Test 7: Additional decision type
        test_fraud_flag()
        
        # Final stats
        print_section("8. Final Statistics")
        test_get_stats()
        
        print("\n" + "█"*70)
        print("█" + " "*68 + "█")
        print("█" + "  ✅ ALL TESTS PASSED - Finance API Operational!".center(68) + "█")
        print("█" + " "*68 + "█")
        print("█"*70 + "\n")
        
    except requests.exceptions.ConnectionError:
        print("\n❌ Cannot connect to server. Make sure server is running:")
        print("   python3 server.py")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
