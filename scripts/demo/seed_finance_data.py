#!/usr/bin/env python3
"""
Finance Vertical — Seed Data Script
=====================================
Generates 5 realistic finance decision scenarios and runs them through
the full FinanceDecisionService pipeline:

  1. Credit Denial — Thin-File Applicant
  2. Credit Approval — Prime Borrower
  3. Fraud Flag — Suspicious Transaction Pattern
  4. Credit Denial — AI Model with Bias Detected
  5. Limit Adjustment — Good Payment History

Each decision exercises:
  - Regulatory Obligation Evaluation (ROE)
  - Evidence Envelope creation (SHA-256 hash chaining)
  - In-memory persistence

Usage:
    python3 scripts/demo/seed_finance_data.py
"""

import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
_PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from services.finance_api.service import FinanceDecisionService
from services.finance_api.models import DecisionRequest, DecisionType


# ── Scenario Definitions ──────────────────────────────────────

SCENARIOS = [
    {
        "name": "Credit Denial — Thin-File Applicant",
        "request": DecisionRequest(
            decision_id="fin_seed_001",
            decision_type=DecisionType.CREDIT_DENIAL,
            evidence={
                "adverse_action_notice": (
                    "Dear Applicant, we regret to inform you that your application "
                    "for a Rewards Credit Card has been denied."
                ),
                "reason_codes": [
                    "insufficient_credit_history",
                    "limited_number_of_accounts",
                ],
                "reason_description": (
                    "Your credit file does not contain enough established "
                    "tradelines to meet our minimum requirements."
                ),
                "notice_delivery_timestamp": datetime.utcnow().isoformat(),
                "applicant_id": "app_thin_001",
                "decision_date": "2026-02-12",
                "credit_score": 580,
                "income": 38000,
                "debt_to_income": 0.42,
            },
            metadata={
                "model_id": "credit_underwrite_v3",
                "model_version": "3.1.2",
                "decision_timestamp": datetime.utcnow().isoformat(),
            },
        ),
        "expect_risk": ["medium", "high", "critical"],
    },
    {
        "name": "Credit Approval — Prime Borrower",
        "request": DecisionRequest(
            decision_id="fin_seed_002",
            decision_type=DecisionType.CREDIT_APPROVAL,
            evidence={
                "approval_notice": "Congratulations! Your credit application has been approved.",
                "credit_limit": 15000,
                "interest_rate": 12.49,
                "apr_value": "12.49%",
                "apr_disclosure_timestamp": datetime.utcnow().isoformat(),
                "finance_charge_amount": "$1,874.00 estimated first year",
                "finance_charge_disclosure": "Finance charges accrue on unpaid balances at 12.49% APR",
                "itemized_costs": "Annual fee: $0, Balance transfer fee: 3%",
                "amount_financed": 15000,
                "loan_amount": 15000,
                "disclosure_form": "TILA_REG_Z_DISCLOSURE_V2",
                "terms_disclosure": "Standard Visa Signature terms. APR: 12.49%. No annual fee.",
                "applicant_id": "app_prime_002",
                "decision_date": "2026-02-12",
                "credit_score": 760,
                "income": 95000,
                "debt_to_income": 0.18,
            },
            metadata={
                "model_id": "credit_underwrite_v3",
                "model_version": "3.1.2",
            },
        ),
        "expect_risk": ["low", "medium"],
    },
    {
        "name": "Fraud Flag — Suspicious Transaction Pattern",
        "request": DecisionRequest(
            decision_id="fin_seed_003",
            decision_type=DecisionType.FRAUD_FLAG,
            evidence={
                "fraud_indicator": "rapid_succession_transactions",
                "risk_score": 0.94,
                "account_id": "acc_88421",
                "transaction_ids": [
                    "txn_f001", "txn_f002", "txn_f003",
                    "txn_f004", "txn_f005",
                ],
                "detection_timestamp": datetime.utcnow().isoformat(),
                "consumer_injury_assessment": "Potential unauthorized access with $12,450 at risk",
                "avoidability_analysis": "Consumer could not have reasonably avoided automated fraud",
                "benefit_cost_analysis": "Blocking transactions prevents $12,450 loss vs $0 cost",
                "disclosure_accuracy_check": "Fraud alert sent via SMS and email within 30 seconds",
                "materiality_assessment": "Material — exceeds $5,000 threshold",
                "consumer_understanding_validation": "Clear language fraud notification sent",
                "comprehensibility_assessment": "Plain-English fraud alert confirmed readable",
                "reasonable_advantage_analysis": "No advantage taken; protective action only",
                "consumer_vulnerability_check": "Standard consumer, no vulnerability indicators",
            },
            metadata={
                "model_id": "fraud_detection_v2",
                "model_version": "2.3.0",
            },
        ),
        "expect_risk": ["low", "medium", "high"],
    },
    {
        "name": "Credit Denial — AI Model with Bias Detected",
        "request": DecisionRequest(
            decision_id="fin_seed_004",
            decision_type=DecisionType.CREDIT_DENIAL,
            evidence={
                "adverse_action_notice": (
                    "Your application for a personal loan has been denied."
                ),
                "reason_codes": ["high_debt_to_income", "recent_delinquency"],
                "reason_description": "DTI exceeds 50% threshold; 30-day late in last 6 months.",
                "notice_delivery_timestamp": datetime.utcnow().isoformat(),
                "applicant_id": "app_bias_004",
                "decision_date": "2026-02-12",
                "credit_score": 640,
                "income": 52000,
                "debt_to_income": 0.55,
                # ECOA Prohibited Basis evidence
                "protected_class_analysis": "DIR analysis performed across 5 groups",
                "bias_report": "Model shows DIR of 0.74 for Hispanic applicants (below 0.80 threshold)",
                "disparate_impact_ratio": 0.74,
                # SR 11-7 Model Risk Management evidence
                "validation_report_hash": "sha256:a1b2c3d4e5f6789012345678",
                "validator_name": "Model Risk Team — J. Chen",
                "validation_date": "2026-01-15",
                "conceptual_soundness_assessment": "Logistic regression with 42 features; conceptually sound",
                "outcomes_analysis": "Back-testing shows 89% accuracy on holdout set",
                "model_documentation_hash": "sha256:f6e5d4c3b2a1987654321012",
                "model_design_description": "Gradient-boosted decision tree ensemble for credit scoring",
                "intended_use_statement": "Consumer credit decisioning for unsecured personal loans",
                "limitations_disclosure": "Model trained on 2020-2024 data; may not capture post-pandemic shifts",
                "monitoring_report_hash": "sha256:1234567890abcdef12345678",
                "performance_metrics": "AUC: 0.87, KS: 0.62, Gini: 0.74",
                "drift_detection_results": "PSI: 0.08 (within tolerance); feature drift on 'employment_tenure'",
                "monitoring_frequency": "Monthly batch; weekly dashboard review",
                "model_registry_entry": "REG-FIN-CRED-004",
                "model_version_id": "v3.1.2-rc1",
                "model_risk_rating": "HIGH",
                "model_use_case": "Consumer credit underwriting — personal loans",
                # OCC AI Guidance evidence
                "ai_governance_framework": "Board-approved AI Policy v2.1 (Jan 2026)",
                "risk_assessment": "Tier 1 — consumer-facing credit model",
                "control_documentation": "SOC 2 Type II control matrix (CC1-CC9)",
                "board_oversight_evidence": "Quarterly MRM report to Risk Committee",
                "bias_testing_report": "Q4 2025 bias report shows DIR violation for Hispanic group",
                "disparate_impact_analysis": "Full 4/5ths rule analysis across 5 protected classes",
                "protected_class_analysis_detail": "Race, ethnicity, gender, age, national origin assessed",
                "bias_mitigation_evidence": "Retraining with adversarial debiasing scheduled for Q1",
                "model_explanation": "SHAP values computed for top 10 features per decision",
                "feature_importance": "Top 3: DTI (0.28), credit_util (0.22), delinquency_count (0.18)",
                "consumer_explanation_provided": True,
                "training_data_hash": "sha256:abcdef1234567890abcdef12",
                "data_quality_report": "99.2% completeness; 0.3% outlier rate; no missing protected attrs",
                "representativeness_assessment": "Training data demographic distribution within 5% of census",
                "data_source_documentation": "Experian, TransUnion bureau data + internal behavioral data",
            },
            metadata={
                "model_id": "personal_loan_scorer_v3",
                "model_version": "3.1.2-rc1",
                "decision_timestamp": datetime.utcnow().isoformat(),
            },
        ),
        "expect_risk": ["low", "medium", "high"],
    },
    {
        "name": "Limit Adjustment — Good Payment History",
        "request": DecisionRequest(
            decision_id="fin_seed_005",
            decision_type=DecisionType.LIMIT_ADJUSTMENT,
            evidence={
                "new_limit": 25000,
                "previous_limit": 15000,
                "adjustment_reason": "24 months of on-time payments; utilization consistently below 30%",
                "account_id": "acc_loyal_005",
                "account_age_months": 36,
                "payment_history": "36/36 on-time",
                "average_utilization": 0.22,
            },
            metadata={
                "model_id": "limit_optimizer_v1",
                "model_version": "1.0.0",
            },
        ),
        "expect_risk": ["low", "medium"],
    },
]


# ── Runner ─────────────────────────────────────────────────────

def run_seed():
    print()
    print("█" * 70)
    print("█" + " " * 68 + "█")
    print("█" + "  RegEngine Finance — Seed Data Generator".center(68) + "█")
    print("█" + " " * 68 + "█")
    print("█" * 70)

    service = FinanceDecisionService(verticals_dir=str(_PROJECT_ROOT / "verticals"))

    results = []
    all_pass = True

    for i, scenario in enumerate(SCENARIOS, 1):
        name = scenario["name"]
        request = scenario["request"]
        expect_risk = scenario["expect_risk"]

        print(f"\n{'─' * 70}")
        print(f"  [{i}/{len(SCENARIOS)}] {name}")
        print(f"{'─' * 70}")
        print(f"  Decision ID : {request.decision_id}")
        print(f"  Type        : {request.decision_type.value}")
        print(f"  Evidence    : {len(request.evidence)} fields")

        try:
            response = service.record_decision(request)

            status_ok = response.status == "recorded"
            eval_ok = response.evaluation_id is not None
            risk_ok = response.risk_level in expect_risk
            coverage_ok = response.coverage_percent is not None

            passed = status_ok and eval_ok and coverage_ok

            icon = "✅" if passed else "❌"
            print(f"\n  {icon} Status     : {response.status}")
            print(f"  {'✅' if eval_ok else '❌'} Eval ID    : {response.evaluation_id}")
            print(f"  {'✅' if coverage_ok else '❌'} Coverage   : {response.coverage_percent:.1f}%")
            print(f"  {'✅' if risk_ok else '⚠️ '} Risk Level : {response.risk_level} (expected: {', '.join(expect_risk)})")

            results.append({
                "name": name,
                "passed": passed,
                "status": response.status,
                "coverage": response.coverage_percent,
                "risk": response.risk_level,
            })

            if not passed:
                all_pass = False

        except Exception as e:
            print(f"\n  ❌ ERROR: {e}")
            results.append({"name": name, "passed": False, "status": "error", "coverage": 0, "risk": "unknown"})
            all_pass = False

    # ── Chain Stats ──
    print(f"\n{'═' * 70}")
    print("  Evidence Chain Statistics")
    print(f"{'═' * 70}")

    stats = service.get_chain_stats()
    decisions_ok = stats["total_decisions"] == len(SCENARIOS)
    envelopes_ok = stats["total_envelopes"] == len(SCENARIOS)
    chain_ok = stats["latest_envelope_hash"] is not None

    print(f"  {'✅' if decisions_ok else '❌'} Decisions recorded : {stats['total_decisions']} (expected {len(SCENARIOS)})")
    print(f"  {'✅' if envelopes_ok else '❌'} Evidence envelopes : {stats['total_envelopes']} (expected {len(SCENARIOS)})")
    print(f"  {'✅' if chain_ok else '❌'} Chain head hash    : {stats['latest_envelope_hash'][:16]}..." if chain_ok else "  ❌ Chain head hash    : None")

    if not (decisions_ok and envelopes_ok and chain_ok):
        all_pass = False

    # ── Summary Table ──
    print(f"\n{'═' * 70}")
    print("  Summary")
    print(f"{'═' * 70}")
    print(f"  {'#':<3} {'Scenario':<45} {'Coverage':>8}  {'Risk':<8}  {'Result'}")
    print(f"  {'─'*3} {'─'*45} {'─'*8}  {'─'*8}  {'─'*6}")

    for i, r in enumerate(results, 1):
        icon = "✅" if r["passed"] else "❌"
        cov = f"{r['coverage']:.0f}%" if isinstance(r["coverage"], (int, float)) else "—"
        print(f"  {i:<3} {r['name']:<45} {cov:>8}  {r['risk']:<8}  {icon}")

    print()
    if all_pass:
        print("  ✅  ALL SCENARIOS PASSED — Finance seed data pipeline verified!")
    else:
        print("  ⚠️  SOME SCENARIOS HAD ISSUES — review output above.")

    print(f"\n{'█' * 70}\n")

    return all_pass


if __name__ == "__main__":
    success = run_seed()
    sys.exit(0 if success else 1)
