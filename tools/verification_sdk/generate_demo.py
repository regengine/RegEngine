#!/usr/bin/env python3
"""
Generate demo snapshot export with valid cryptographic hashes.
This creates a sample export file that will pass verification.
"""

import json
import hashlib
from datetime import datetime, timedelta, timezone


def calculate_content_hash(snapshot_data):
    """Calculate content hash using RegEngine's algorithm."""
    canonical = {
        "snapshot_time": snapshot_data["snapshot_time"],
        "substation_id": snapshot_data["substation_id"],
        "system_status": snapshot_data["system_status"],
        "asset_states": snapshot_data["asset_states"],
        "esp_config": snapshot_data["esp_config"],
        "patch_metrics": snapshot_data["patch_metrics"],
        "active_mismatches": sorted(snapshot_data.get("active_mismatches", []))
    }
    
    canonical_json = json.dumps(canonical, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
    return hashlib.sha256(canonical_json.encode('utf-8')).hexdigest()


def calculate_signature_hash(snapshot_id, content_hash):
    """Calculate signature hash."""
    signature_input = f"{snapshot_id}:{content_hash}"
    return hashlib.sha256(signature_input.encode('utf-8')).hexdigest()


def generate_demo_export():
    """Generate valid demo export."""
    base_time = datetime(2026, 1, 30, 0, 0, 0, tzinfo=timezone.utc)
    
    snapshots = []
    previous_id = None
    
    for i in range(3):
        snapshot_id = f"01936d4e-000{i}-7000-8000-00000000000{i+1}"
        snapshot_time = base_time + timedelta(hours=i)
        
        snapshot_data = {
            "id": snapshot_id,
            "snapshot_time": snapshot_time.isoformat(),
            "substation_id": "DEMO-SUBSTATION-ALPHA",
            "facility_name": "Alpha Substation - North Grid",
            "system_status": "NOMINAL",
            "asset_states": {
                "summary": {
                    "total_assets": 12,
                    "verified_count": 12,
                    "mismatch_count": 0,
                    "unknown_count": 0
                },
                "assets": [
                    {
                        "asset_id": "RTU-001",
                        "asset_type": "Remote Terminal Unit",
                        "manufacturer": "Schweitzer Engineering",
                        "model": "SEL-3505",
                        "firmware_version": "R124",
                        "last_verified": (snapshot_time - timedelta(minutes=15)).isoformat(),
                        "verification_method": "AUTOMATED_SCAN"
                    },
                    {
                        "asset_id": "FIREWALL-001",
                        "asset_type": "Industrial Firewall",
                        "manufacturer": "Fortinet",
                        "model": "FortiGate 200F",
                        "firmware_version": "7.4.1",
                        "last_verified": (snapshot_time - timedelta(minutes=10)).isoformat(),
                        "verification_method": "AUTOMATED_SCAN"
                    }
                ]
            },
            "esp_config": {
                "perimeter_devices": [
                    {
                        "device_id": "FIREWALL-001",
                        "zone": "DMZ",
                        "inbound_rules": 12,
                        "outbound_rules": 8
                    }
                ],
                "access_points": [
                    {
                        "name": "VPN Gateway",
                        "type": "Remote Access",
                        "authentication": "MFA Required"
                    }
                ]
            },
            "patch_metrics": {
                "total_vulnerabilities": 0,
                "critical_unpatched": 0,
                "high_unpatched": 0,
                "avg_patch_hours": 8.2 + (i * 0.1),
                "compliance_status": "COMPLIANT"
            },
            "active_mismatches": [],
            "previous_snapshot_id": previous_id
        }
        
        # Calculate hashes
        content_hash = calculate_content_hash(snapshot_data)
        signature_hash = calculate_signature_hash(snapshot_id, content_hash)
        
        snapshot_data["content_hash"] = content_hash
        snapshot_data["signature_hash"] = signature_hash
        
        snapshots.append(snapshot_data)
        previous_id = snapshot_id
    
    export_data = {
        "metadata": {
            "substation_id": "DEMO-SUBSTATION-ALPHA",
            "export_time": datetime.now(timezone.utc).isoformat(),
            "total_snapshots": len(snapshots),
            "verification_sdk_version": "1.0.0",
            "from_time": snapshots[0]["snapshot_time"],
            "to_time": snapshots[-1]["snapshot_time"]
        },
        "snapshots": snapshots
    }
    
    return export_data


if __name__ == "__main__":
    export = generate_demo_export()
    with open("demo_snapshot_export.json", "w") as f:
        json.dump(export, f, indent=2)
    print("✓ Generated demo_snapshot_export.json with valid hashes")
