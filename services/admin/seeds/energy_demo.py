
import sys
import os
from pathlib import Path
from datetime import datetime

# Add project root to path
_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

# Mock dependencies
from services.admin.app.verticals.energy.supply_chain import SupplyChainValidator, SoftwareAsset, VendorPatch

def run_energy_demo():
    print("⚡️ Starting Energy Vertical Demo...")
    print("---------------------------------------")
    
    # 1. Simulate Project Creation
    print("\n[1] Creating Energy Compliance Scope...")
    project_metadata = {
        "nerc_region": "wecc",
        "asset_impact_rating": "high",
        "grid_voltage_kv": 500
    }
    print(f"    > Project: 'Substation Alpha NERC CIP Audit'")
    print(f"    > Metadata: {project_metadata}")
    
    # 2. Simulate Loading RulePack
    print("\n[2] Loading 'energy_nerc_cip_v1' RulePack...")
    rules = ["CIP-013-01", "CIP-010-01"]
    print(f"    > Activated {len(rules)} base rules.")
    
    # 3. Simulate The Interaction (Supply Chain Validator)
    print("\n[3] Running Supply Chain Validator (Firmware Integrity)...")
    
    # Scenario: "The Compromised Update"
    # An engineer is about to patch the SCADA system, but the file hash doesn't match the vendor's site.
    
    print("    > Loading Vendor Baselines (Trusted DB)...")
    patches = [
        VendorPatch(patch_id="KB99281", asset_name="SCADA Controller X1", target_version="v4.2.0", official_hash="sha256_trusted_hash_abc123"),
        VendorPatch(patch_id="KB11029", asset_name="Relay Protection", target_version="v1.1", official_hash="sha256_trusted_hash_xyz789"),
    ]
    
    print("    > Scanning Installed Assets...")
    assets = [
        # Clean Asset
        SoftwareAsset(name="Relay Protection", version="v1.1", vendor="GE", file_hash="sha256_trusted_hash_xyz789", is_critical=True),
        
        # Compromised Asset (Hash Mismatch)
        SoftwareAsset(name="SCADA Controller X1", version="v4.2.0", vendor="Siemens", file_hash="sha256_MALICIOUS_HASH_666", is_critical=True),
        
        # Rogue Box
        SoftwareAsset(name="Unknown Raspberry Pi", version="v1.0", vendor="DIY", file_hash="sha256_unknown", is_critical=True),
    ]
    
    validator = SupplyChainValidator()
    alerts = validator.validate_hashes(assets, patches)
    
    # 4. Display Results
    if alerts:
        print(f"\n🚨 NERC CIP VIOLATIONS DETECTED ({len(alerts)}):")
        for alert in alerts:
            print(f"    [severity={alert.severity}] {alert.description}")
            print(f"    -> Rule: {alert.rule_id}")
    else:
        print("\n✅ System Integrity Verified.")
        
    print("\n---------------------------------------")
    print("Energy Vertical Demo Complete.")

if __name__ == "__main__":
    run_energy_demo()
