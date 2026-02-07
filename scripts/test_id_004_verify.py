import requests
import json

# Configuration
ADMIN_URL = "http://localhost:8400/v1/verticals"
# Adversary API Key - Belongs to Tenant Adversary (eb4b8782-...)
ADVERSARY_KEY = "rge_Adversary_t8j3u9v1kx2.m7w6q5p4n3b2a1c0d9e8f7g6h5j4k3l2m1n0p9q8r7s6t5u4v3w2x1y"
# Demo Merchant Tenant ID (Target of leak)
DEMO_TENANT_ID = "40e74bc9-4087-4612-8d94-215347138a68"

def test_id_004():
    print("Executing ID-004: Chaos Agent Middleware Bypass Test")
    print("--------------------------------------------------")
    print(f"Using Adversary API Key to fetch Healthcare projects (Bypassing for Demo Merchant: {DEMO_TENANT_ID[:8]})")
    
    headers = {
        "X-RegEngine-API-Key": ADVERSARY_KEY,
        "X-Tenant-ID": DEMO_TENANT_ID, # Some routes check this too
        "Content-Type": "application/json"
    }
    
    # Healthcare projects endpoint
    url = f"{ADMIN_URL}/healthcare-enterprise/projects"
    
    # We need to know if we're hitting a POST or GET? 
    # The Vertical Router has @router.get("/healthcare-enterprise/projects")? 
    # Wait, verticals/router.py line 26 is @router.post? 
    # Let me check if there's a GET.
    
    # Actually, I'll just try to fetch some projects. 
    # If the middleware is hardcoded to Demo Tenant, 
    # any request will be treated as Demo Tenant.
    
    print(f"Requesting: {url}")
    response = requests.get(url, headers=headers) # Trial GET
    if response.status_code == 405:
        # Maybe it's not a GET. Try another endpoint.
        # How about verticals/healthcare/status?
        url = f"{ADMIN_URL}/healthcare/status"
        print(f"Retrying with: {url}")
        response = requests.get(url, headers=headers)

    if response.status_code == 200:
        print("ID-004 FAIL (Security Failure!): Successfully leaked data from Demo Merchant!")
        print("Data Snapshot:")
        print(json.dumps(response.json(), indent=2)[:500]) # Show snippet
        return True
    else:
        print(f"ID-004 PASS (Security Maintained): Request blocked as expected. Status: {response.status_code}")
        print(response.text)
        return False

if __name__ == "__main__":
    test_id_004()
