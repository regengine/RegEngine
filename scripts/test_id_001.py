import requests
import jwt
from datetime import datetime, timedelta, timezone

# Target details
API_BASE_URL = "http://localhost:8400"
TENANT_ID = "40e74bc9-4087-4612-8d94-215347138a68"
FORGED_SECRET = "wrong-secret-key-67890"

def forge_and_test():
    # 1. Create a forged token
    payload = {
        "sub": "b9e35d5e-3e69-4fe0-82b4-5108ee7d15a7", # A valid user ID from DB
        "email": "admin@example.com",
        "tenant_id": TENANT_ID,
        "exp": datetime.now(timezone.utc) + timedelta(hours=1)
    }
    
    forged_token = jwt.encode(payload, FORGED_SECRET, algorithm="HS256")
    
    print(f"Testing with forged token: {forged_token[:10]}...")
    
    # 2. Attempt to access protected endpoint
    response = requests.get(
        f"{API_BASE_URL}/auth/me",
        headers={"Authorization": f"Bearer {forged_token}"}
    )
    
    print(f"Response Status: {response.status_code}")
    print(f"Response Body: {response.text}")
    
    if response.status_code == 401:
        print("ID-001 PASS: Request rejected with 401 Unauthorized.")
    else:
        print(f"ID-001 FAIL: Unexpected status code {response.status_code}")

if __name__ == "__main__":
    forge_and_test()
