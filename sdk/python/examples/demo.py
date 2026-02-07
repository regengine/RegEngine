#!/usr/bin/env python3
"""
Example usage of the RegEngine Energy SDK.

This script demonstrates how to:
1. Create compliance snapshots
2. Retrieve snapshots
3. Verify chain integrity
"""

import os
from regengine_energy import EnergyCompliance, SystemStatus

# Initialize client (API key from environment or parameter)
client = EnergyCompliance(
    api_key=os.getenv("REGENGINE_API_KEY", "rge_demo_key"),
    base_url=os.getenv("ENERGY_API_URL", "http://localhost:8002")
)

def create_demo_snapshot():
    """Create a sample compliance snapshot."""
    print("📸 Creating compliance snapshot...")
    
    try:
        snapshot = client.snapshots.create(
            substation_id="ALPHA-001",
            facility_name="Alpha Substation - North Grid",
            system_status=SystemStatus.NOMINAL,
            assets=[
                {
                    "id": "T1",
                    "type": "TRANSFORMER",
                    "firmware_version": "2.4.1",
                    "last_verified": "2026-01-26T15:00:00Z",
                    "metadata": {
                        "manufacturer": "ABB",
                        "model": "RESIBLOC",
                        "capacity_kva": 2500
                    }
                },
                {
                    "id": "R1",
                    "type": "RELAY",
                    "firmware_version": "3.1.0",
                    "last_verified": "2026-01-26T15:00:00Z",
                    "metadata": {
                        "manufacturer": "SEL",
                        "model": "SEL-451",
                        "protection_zone": "primary"
                    }
                }
            ],
            esp_config={
                "firewall_version": "2.4.1",
                "ids_enabled": True,
                "patch_level": "current",
                "metadata": {
                    "last_audit": "2028-07-20",
                    "auditor": "NERC Compliance Team"
                }
            },
            regulatory={
                "standard": "NERC-CIP-013-1",
                "audit_ready": True
            },
            trigger_reason="Weekly compliance checkpoint"
        )
        
        print(f"✅ Snapshot created successfully!")
        print(f"   ID: {snapshot.snapshot_id}")
        print(f"   Time: {snapshot.snapshot_time}")
        print(f"   Status: {snapshot.system_status}")
        print(f"   Content Hash: {snapshot.content_hash[:16]}...")
        print(f"   Assets: {snapshot.asset_summary}")
        
        return snapshot.snapshot_id
        
    except Exception as e:
        print(f"❌ Error creating snapshot: {e}")
        return None


def retrieve_snapshot(snapshot_id):
    """Retrieve and display a specific snapshot."""
    print(f"\n🔍 Retrieving snapshot {snapshot_id}...")
    
    try:
        snapshot = client.snapshots.get(snapshot_id)
        print(f"✅ Snapshot retrieved:")
        print(f"   Facility: {snapshot.facility_name if hasattr(snapshot, 'facility_name') else 'N/A'}")
        print(f"   Hash: {snapshot.content_hash}")
        print(f"   Chain Status: {snapshot.chain_status or 'N/A'}")
        
    except Exception as e:
        print(f"❌ Error retrieving snapshot: {e}")


def list_snapshots():
    """List recent snapshots."""
    print("\n📋 Listing recent snapshots...")
    
    try:
        result = client.snapshots.list(
            substation_id="ALPHA-001",
            limit=5,
            offset=0
        )
        
        print(f"✅ Found {result.total} snapshots (showing {len(result.snapshots)}):")
        for snapshot in result.snapshots:
            print(f"   - {snapshot.snapshot_id}: {snapshot.system_status}")
            
    except Exception as e:
        print(f"❌ Error listing snapshots: {e}")


def verify_chain():
    """Verify chain integrity."""
    print("\n⛓️  Verifying chain integrity...")
    
    try:
        verification = client.verification.verify_latest("ALPHA-001")
        
        print(f"✅ Verification complete:")
        print(f"   Verified: {verification.verified}")
        print(f"   Chain Intact: {verification.chain_intact}")
        print(f"   Content Hash Valid: {verification.content_hash_valid}")
        if verification.total_snapshots:
            print(f"   Total Snapshots: {verification.total_snapshots}")
        if verification.errors:
            print(f"   ⚠️  Errors: {verification.errors}")
            
    except Exception as e:
        print(f"❌ Error verifying chain: {e}")


if __name__ == "__main__":
    print("=" * 60)
    print("RegEngine Energy SDK - Example Usage")
    print("=" * 60)
    
    # Create a demo snapshot
    snapshot_id = create_demo_snapshot()
    
    # Retrieve it
    if snapshot_id:
        retrieve_snapshot(snapshot_id)
    
    # List all snapshots
    list_snapshots()
    
    # Verify chain integrity
    verify_chain()
    
    print("\n" + "=" * 60)
    print("✅ Demo complete!")
    print("=" * 60)
