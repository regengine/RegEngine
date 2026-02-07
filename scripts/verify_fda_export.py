import requests
import sys
import datetime

ADMIN_API_URL = "http://localhost:8400"
API_KEY = "admin"
TENANT_ID = "00000000-0000-0000-0000-000000000000"
ADMIN_MASTER_KEY = "admin-master-key-dev"

HEADERS = {
    "X-RegEngine-API-Key": API_KEY,
    "X-Admin-Key": ADMIN_MASTER_KEY,
    "X-Tenant-ID": TENANT_ID,
}

def verify_export():
    print("Verifying FDA Request Mode Export...")

    start_date = "2025-01-01"
    end_date = "2029-01-01"
    
    # Path Candidates based on code inspection (double prefix)
    paths = [
        "/fsma/v1/fsma/export/fda-request", # Direct double prefix
        "/v1/fsma/export/fda-request",      # Single prefix (if one invalid)
        "/fsma/export/fda-request",         # Short prefix
        "/fsma/compliance/export/fda-request" # Explicit router structure
    ]
    
    # Service Hosts
    hosts = [
        ("Graph Direct", "http://localhost:8200"),
        ("Admin Proxy", "http://localhost:8400/graph"),
    ]

    for host_name, host_url in hosts:
        for path in paths:
            full_url = f"{host_url}{path}"
            print(f"Trying {host_name}: {full_url}")
            try:
                resp = requests.get(full_url, headers=HEADERS, params={"start_date": start_date, "end_date": end_date})
                if resp.status_code == 200:
                    print(f"✅ SUCCESS at {full_url}")
                    print(resp.text[:500])
                    return
                else:
                    print(f"   {resp.status_code}")
            except Exception as e:
                print(f"   Connection Failed: {e}")

    print("❌ All attempts failed.")

if __name__ == "__main__":
    verify_export()
