
import sys
import os
from pathlib import Path
from datetime import datetime

# Add project root to path
_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

# Mock SQLAlchemy dependencies since we aren't connecting to real DB in this demo script
# In a real scenario this would import the actual models and session
# This script acts as a "Concept Verification"

from services.admin.app.verticals.healthcare.breach_calculator import BreachRiskCalculator, AccessLogEntry

def run_healthcare_demo():
    print("🏥 Starting Healthcare Vertical Demo...")
    print("---------------------------------------")
    
    # 1. Simulate Project Creation
    print("\n[1] Creating Healthcare Audit Project...")
    project_metadata = {
        "facility_type": "hospital",
        "patient_volume_annual": 12000,
        "emr_system": "epic"
    }
    print(f"    > Project: 'Q1 Compliance Audit - General Hospital'")
    print(f"    > Metadata: {project_metadata}")
    
    # 2. Simulate Loading RulePack
    print("\n[2] Loading 'healthcare_hipaa_v1' RulePack...")
    rules = ["HIPAA-ADM-01", "HIPAA-TECH-01"]
    print(f"    > Activated {len(rules)} base rules.")
    
    # 3. Simulate Active Monitoring (The Breach Calculator)
    print("\n[3] Running Breach Risk Calculator (Active Monitoring)...")
    
    # Generate some logs
    logs = [
        # Normal traffic
        AccessLogEntry(timestamp=datetime.now(), user_id="dr_strange", role="doctor", patient_id="P001", record_type="clinical_notes", action="view"),
        
        # The Attack (VIP Snooping)
        AccessLogEntry(timestamp=datetime.now(), user_id="nurse_joy", role="nurse", patient_id="VIP_999", record_type="clinical_notes", action="view", is_vip=True),
        AccessLogEntry(timestamp=datetime.now(), user_id="admin_bob", role="admin", patient_id="VIP_999", record_type="demographics", action="view", is_vip=True),
        AccessLogEntry(timestamp=datetime.now(), user_id="intern_gary", role="intern", patient_id="VIP_999", record_type="clinical_notes", action="print", is_vip=True),
        AccessLogEntry(timestamp=datetime.now(), user_id="janitor_steve", role="facilities", patient_id="VIP_999", record_type="clinical_notes", action="view", is_vip=True),
    ]
    
    print(f"    > Analyzed {len(logs)} access logs.")
    
    calculator = BreachRiskCalculator()
    alerts = calculator.analyze_access_pattern(logs)
    
    # 4. Display Results
    if alerts:
        print(f"\n🚨 ALERTS DETECTED ({len(alerts)}):")
        for alert in alerts:
            print(f"    [severity={alert.severity}] {alert.description}")
            print(f"    -> Action: {alert.recommended_action}")
    else:
        print("\n✅ No threats detected.")
        
    print("\n---------------------------------------")
    print("Healthcare Vertical Demo Complete.")

if __name__ == "__main__":
    run_healthcare_demo()
