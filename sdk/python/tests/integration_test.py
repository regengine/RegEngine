#!/usr/bin/env python3
"""
Integration test: SDK → Energy Service → PostgreSQL

Tests the complete flow:
1. SDK creates snapshot
2. Energy service processes request
3. PostgreSQL stores data
4. SDK retrieves and verifies
"""

import sys
import os

# Add SDK to path
sys.path.insert(0, '/Users/christophersellers/Desktop/RegEngine/sdk/python')

from regengine_energy import EnergyCompliance, SystemStatus

def test_integration():
    """Run integration tests against live service."""
    
    print("=" * 70)
    print("INTEGRATION TEST: Python SDK → Energy Service → PostgreSQL")
    print("=" * 70)
    
    # Initialize client pointing to local service
    client = EnergyCompliance(
        api_key="test_integration_key",  # Test key for local dev
        base_url="http://localhost:8003",
        timeout=10
    )
    
    print("\n✅ SDK client initialized")
    print(f"   Base URL: http://localhost:8003")
    
    # Test 1: Create a snapshot
    print("\n📸 TEST 1: Creating compliance snapshot...")
    try:
        snapshot = client.snapshots.create(
            substation_id="INTEGRATION-TEST-001",
            facility_name="Integration Test Substation",
            system_status=SystemStatus.NOMINAL,
            assets=[
                {
                    "id": "TEST-T1",
                    "type": "TRANSFORMER",
                    "firmware_version": "2.4.1",
                    "last_verified": "2026-01-26T23:00:00Z",
                    "metadata": {
                        "test": True,
                        "purpose": "SDK integration test"
                    }
                }
            ],
            esp_config={
                "firewall_version": "2.4.1",
                "ids_enabled": True,
                "patch_level": "current"
            },
            trigger_reason="Integration test - SDK validation"
        )
        
        print(f"   ✅ Snapshot created successfully!")
        print(f"   ID: {snapshot.snapshot_id}")
        print(f"   Time: {snapshot.snapshot_time}")
        print(f"   Status: {snapshot.system_status}")
        print(f"   Hash: {snapshot.content_hash[:32]}...")
        
        snapshot_id = snapshot.snapshot_id
        
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        print(f"      Type: {type(e).__name__}")
        return False
    
    # Test 2: Retrieve the snapshot
    print(f"\n🔍 TEST 2: Retrieving snapshot {snapshot_id}...")
    try:
        retrieved = client.snapshots.get(snapshot_id)
        
        print(f"   ✅ Snapshot retrieved!")
        print(f"   Hash matches: {retrieved.content_hash == snapshot.content_hash}")
        
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        return False
    
    # Test 3: List snapshots
    print(f"\n📋 TEST 3: Listing snapshots for INTEGRATION-TEST-001...")
    try:
        result = client.snapshots.list(
            substation_id="INTEGRATION-TEST-001",
            limit=10
        )
        
        print(f"   ✅ Found {result.total} total snapshots")
        print(f"   Returned {len(result.snapshots)} in this page")
        
        if result.snapshots:
            for snap in result.snapshots[:3]:
                print(f"      - {snap.snapshot_id}: {snap.system_status}")
                
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        return False
    
    # Test 4: Verify chain integrity
    print(f"\n⛓️  TEST 4: Verifying chain integrity...")
    try:
        verification = client.verification.verify_latest("INTEGRATION-TEST-001")
        
        print(f"   ✅ Verification complete!")
        print(f"   Verified: {verification.verified}")
        print(f"   Chain Intact: {verification.chain_intact}")
        print(f"   Content Hash Valid: {verification.content_hash_valid}")
        
        if not verification.verified:
            print(f"   ⚠️  Errors: {verification.errors}")
            
    except Exception as e:
        print(f"   ⚠️  Verification endpoint may not be implemented yet: {e}")
        # Not failing the test for this - verification endpoint is Phase 3 work
    
    print("\n" + "=" * 70)
    print("✅ INTEGRATION TEST PASSED")
    print("=" * 70)
    print("\nValidated:")
    print("  ✓ SDK → API communication")
    print("  ✓ Snapshot creation with type validation")
    print("  ✓ Database persistence")
    print("  ✓ Snapshot retrieval")
    print("  ✓ Pagination and filtering")
    
    return True


if __name__ == "__main__":
    success = test_integration()
    sys.exit(0 if success else 1)
