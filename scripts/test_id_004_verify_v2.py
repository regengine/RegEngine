import requests
import json

# Configuration - Root level for verticals
# Note: main.py includes verticals_router without v1 prefix
ADMIN_URL = "http://localhost:8400/verticals"
# Adversary API Key - Belongs to Tenant Adversary (eb4b8782-...)
ADVERSARY_KEY = "rge_Adversary_t8j3u9v1kx2.m7w6q5p4n3b2a1c0d9e8f7g6h5j4k3l2m1n0p9q8r7s6t5u4v3w2x1y"
# Demo Merchant Tenant ID (Target of leak)
DEMO_TENANT_ID = "40e74bc9-4087-4612-8d94-215347138a68"

def test_id_004():
    print("Executing ID-004: Chaos Agent Middleware Bypass Test")
    print("--------------------------------------------------")
    print(f"Using Adversary API Key to fetch Healthcare status (Bypassing for Demo Merchant: {DEMO_TENANT_ID[:8]})")
    
    headers = {
        "X-RegEngine-API-Key": ADVERSARY_KEY,
        "X-Tenant-ID": DEMO_TENANT_ID,
        "Content-Type": "application/json"
    }
    
    # 1. Test /verticals/healthcare/status (GET)
    url = f"{ADMIN_URL}/healthcare/status"
    print(f"Requesting: {url}")
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        print("ID-004 FAIL (Security Failure!): Successfully leaked data from Demo Merchant!")
        print("Data Snapshot (Safety Status):")
        print(json.dumps(response.json(), indent=2)[:500])
        
        # 2. Try to fetch projects (just to be sure)
        # Note: If RLS was working, even with a hardcoded tenant ID in the middleware, 
        # the DB session would (ideally) be restricted. 
        # But we found RLS is disabled.
        
        return True
    else:
        print(f"ID-004 PASS (Security Maintained): Request blocked or returned error. Status: {response.status_code}")
        print(response.text)
        return False

if __name__ == "__main__":
    test_id_004()
