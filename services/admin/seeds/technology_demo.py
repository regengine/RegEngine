
import sys
import os
from pathlib import Path
from datetime import datetime

# Add project root to path
_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

# Mock dependencies
from services.admin.app.verticals.technology.evidence_collector import EvidenceCollector, EvidenceRequest

def run_tech_demo():
    print("☁️ Starting Technology Vertical Demo...")
    print("---------------------------------------")
    
    # 1. Simulate Project Creation
    print("\n[1] Creating Technology Compliance Scope...")
    project_metadata = {
        "hosting_provider": "aws",
        "data_classification": ["confidential", "internal"],
        "include_security": True,
        "include_availability": True
    }
    print(f"    > Project: 'SOC 2 Type II Readiness Sprint'")
    print(f"    > Metadata: {project_metadata}")
    
    # 2. Simulate Loading RulePack
    print("\n[2] Loading 'tech_soc2_iso_gdpr_v1' RulePack...")
    rules = ["SOC2-TSC-01", "SOC2-EVI-01"]
    print(f"    > Activated {len(rules)} base rules.")
    
    # 3. Simulate The Interaction (Evidence Collector)
    print("\n[3] Running Evidence Collector (Trust Center Automation)...")
    
    # Scenario: "The IPO Crunch"
    # Company needs 100% control coverage to go public.
    
    print("    > Querying Evidence Status...")
    requests = [
        EvidenceRequest(control_id="CC1.1", evidence_type="org_chart", status="collected", last_collected=datetime.now()),
        EvidenceRequest(control_id="CC6.1", evidence_type="access_review", status="collected", last_collected=datetime.now()),
        EvidenceRequest(control_id="CC6.7", evidence_type="encryption_config", status="collected", last_collected=datetime.now()),
        
        # The Problem
        EvidenceRequest(control_id="A1.2", evidence_type="penetration_test", status="missing", last_collected=datetime.now()),
        EvidenceRequest(control_id="A1.3", evidence_type="disaster_recovery_plan", status="expired", last_collected=datetime.now()),
    ]
    
    collector = EvidenceCollector()
    status = collector.check_readiness(requests)
    
    # 4. Display Results
    print(f"\n📊 TRUST CENTER STATUS:")
    print(f"    Health Score: {status.overall_health}%")
    print(f"    Public Badge: [{status.public_status}]")
    print(f"    Passing Controls: {status.passing_controls}")
    print(f"    Failing Controls: {status.failing_controls}")
    
    if status.public_status != "Operational":
        print("\n⚠️  WARNING: Trust Center is degraded. IPO Readiness at risk.")
        
    print("\n---------------------------------------")
    print("Technology Vertical Demo Complete.")

if __name__ == "__main__":
    run_tech_demo()
