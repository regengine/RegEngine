import requests

# Target details
API_BASE_URL = "http://localhost:8400"
DEMO_PROJECT_ID = "11f5a92e-9be0-47b7-9047-1b59ba0f88ec"
ADVERSARY_KEY = "rge_Q-9KZljwkC6DNfgyH7_yfg.7mjQ9BBc-yfs4N7Ug6jnfqkWQMU4LFvgltx5IiLSwg0"

def cross_tenant_test():
    print(f"Attempting to access Demo Project ({DEMO_PROJECT_ID}) using Adversary Key...")
    
    # Attempt to get risk details for the demo project
    response = requests.get(
        f"{API_BASE_URL}/verticals/healthcare-enterprise/{DEMO_PROJECT_ID}/risk",
        headers={"X-RegEngine-API-Key": ADVERSARY_KEY}
    )
    
    print(f"Response Status: {response.status_code}")
    print(f"Response Body: {response.text}")
    
    if response.status_code == 403:
        print("ID-002 PASS: Request rejected with 403 Forbidden.")
    elif response.status_code == 404:
        print("ID-002 PASS: Request rejected with 404 (Resource not found for this tenant).")
    else:
        print(f"ID-002 FAIL: Unexpected status code {response.status_code}")

if __name__ == "__main__":
    cross_tenant_test()
