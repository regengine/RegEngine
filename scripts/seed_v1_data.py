import os
import sys
import time

import requests

INGEST_URL = "http://localhost:8002/v1/ingest"
LIVE_FDA_URL = "https://www.fda.gov/food/food-safety-modernization-act-fsma/fsma-final-rule-requirements-additional-traceability-records-certain-foods"
TENANT_ID = os.environ.get("REGENGINE_TENANT_ID", "00000000-0000-0000-0000-000000000000")


def get_api_key():
    key = os.environ.get("REGENGINE_API_KEY", "")
    if not key:
        raise SystemExit("REGENGINE_API_KEY is not set; refusing to seed without a real API credential.")
    return key


def build_headers(api_key):
    return {
        "X-RegEngine-API-Key": api_key,
        "X-Tenant-ID": TENANT_ID,
        "Content-Type": "application/json",
    }


def log(msg):
    print(f"[SeedV1] {msg}")


def seed_v1(run_id):
    api_key = get_api_key()
    headers = build_headers(api_key)
    log(f"Seeding V1 (Old World) data for run {run_id}...")

    unique_url = f"{LIVE_FDA_URL}?run={run_id}"
    content = """
    <html>
    <body>
    <h1>FSMA Final Rule on Requirements for Additional Traceability Records for Certain Foods</h1>
    <p>
    Compliance Date
    The compliance date for all persons subject to the recordkeeping requirements is Tuesday, January 20, 2026.
    </p>
    <!-- V1 Baseline -->
    </body>
    </html>
    """

    payload = {"text": content, "source_url": unique_url, "source_system": "seed_script", "vertical": "food_safety"}

    try:
        resp = requests.post(INGEST_URL, json=payload, headers=headers)
        if resp.status_code == 200:
            log("✅ V1 Ingest Accepted")
            return True
        else:
            log(f"❌ V1 Ingest Failed: {resp.status_code} - {resp.text}")
            return False
    except Exception as e:
        log(f"❌ Connection Error: {e}")
        return False


if __name__ == "__main__":
    run_id = sys.argv[1] if len(sys.argv) > 1 else str(int(time.time()))
    if seed_v1(run_id):
        time.sleep(5)  # Wait for processing
        sys.exit(0)
    else:
        sys.exit(1)
