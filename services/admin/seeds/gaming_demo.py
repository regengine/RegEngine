
import sys
import os
from pathlib import Path
from datetime import datetime

# Add project root to path
_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

# Mock dependencies
from services.admin.app.verticals.gaming.risk_scorer import PlayerRiskScorer, DepositEvent

def run_gaming_demo():
    print("🎲 Starting Gaming Vertical Demo...")
    print("---------------------------------------")
    
    # 1. Simulate Project Creation
    print("\n[1] Creating Gaming Compliance Scope...")
    project_metadata = {
        "jurisdiction": "nevada",
        "license_type": "casino",
        "aml_reporting_threshold_usd": 10000.00
    }
    print(f"    > Project: 'Las Vegas Strip Anti-Money Laundering Review'")
    print(f"    > Metadata: {project_metadata}")
    
    # 2. Simulate Loading RulePack
    print("\n[2] Loading 'gaming_aml_gli_v1' RulePack...")
    rules = ["GAM-KYC-01", "GAM-AML-01"]
    print(f"    > Activated {len(rules)} base rules.")
    
    # 3. Simulate The Interaction (Risk Scorer)
    print("\n[3] Running Player Risk Scorer (AML Logic)...")
    
    # Scenario: "The Smurf Attack"
    # A syndicate uses 5 different accounts to deposit money from the same coffee shop IP
    
    print("    > Ingesting Live Deposit Feed...")
    deposits = [
        # The Ring (Same IP: 192.168.1.105)
        DepositEvent(timestamp=datetime.now(), player_id="USER_001", amount=2000.0, ip_address="192.168.1.105", method="app"),
        DepositEvent(timestamp=datetime.now(), player_id="USER_002", amount=2000.0, ip_address="192.168.1.105", method="app"),
        DepositEvent(timestamp=datetime.now(), player_id="USER_003", amount=2000.0, ip_address="192.168.1.105", method="app"),
        DepositEvent(timestamp=datetime.now(), player_id="USER_004", amount=2000.0, ip_address="192.168.1.105", method="app"),
        DepositEvent(timestamp=datetime.now(), player_id="USER_005", amount=2000.0, ip_address="192.168.1.105", method="app"),
        
        # Innocent Bystander
        DepositEvent(timestamp=datetime.now(), player_id="USER_999", amount=50.0, ip_address="10.0.0.1", method="credit"),
    ]
    print(f"      - Ingested {len(deposits)} transactions.")
    
    scorer = PlayerRiskScorer()
    alerts = scorer.analyze_deposits(deposits)
    
    # 4. Display Results
    if alerts:
        print(f"\n🚨 AML RISK DETECTED ({len(alerts)}):")
        for alert in alerts:
            print(f"    [severity={alert.severity}] {alert.description}")
            print(f"    -> Rule Triggered: {alert.rule_triggered}")
    else:
        print("\n✅ No AML risks detected.")
        
    print("\n---------------------------------------")
    print("Gaming Vertical Demo Complete.")

if __name__ == "__main__":
    run_gaming_demo()
