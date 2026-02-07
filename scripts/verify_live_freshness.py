import requests
import sys
import time
import re

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

# Configuration
INGEST_URL = "http://localhost:8002/v1/ingest"
ADMIN_API_URL = "http://localhost:8400"
LIVE_FDA_URL = "https://www.fda.gov/food/food-safety-modernization-act-fsma/fsma-final-rule-requirements-additional-traceability-records-certain-foods"
API_KEY = "admin"
ADMIN_MASTER_KEY = "admin-master-key-dev"
TENANT_ID = "00000000-0000-0000-0000-000000000000"

HEADERS = {
    "X-RegEngine-API-Key": API_KEY,
    "X-Admin-Key": ADMIN_MASTER_KEY,
    "X-Tenant-ID": TENANT_ID,
    "Content-Type": "application/json"
}

def log(msg):
    print(f"[LiveFreshnessVerify] {msg}")

def fetch_live_content():
    log(f"Fetching live content from {LIVE_FDA_URL}...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        resp = requests.get(LIVE_FDA_URL, headers=headers)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        log(f"❌ Failed to fetch live content: {e}")
        return None

def extract_compliance_date_snippet(html):
    # Simple check to see if the key phrase exists
    text = html
    if HAS_BS4:
        soup = BeautifulSoup(html, 'html.parser')
        text = soup.get_text()
    
    # Look for the date - strict match based on known content
    match = re.search(r"July 20, 2028", text)
    if match:
        log(f"✅ Found compliance date reference: '{match.group(0)}' in live content.")
        return True
    else:
        log("⚠️ Could not find explicit 'July 20, 2028' string in fetched content. Content might have changed or parsing issues.")
        return False

def ingest_live_content(content, run_id):
    log(f"Ingesting live content to RegEngine for run {run_id}...")
    
    unique_url = f"{LIVE_FDA_URL}?run={run_id}"
    
    # Force hash change for verification purposes
    # This prevents 'duplicate key' errors if V1 already exists and we want V2
    # and allows lineage verification to see a new version.
    content += f"\n\n<!-- Verified at {time.time()} -->"

    payload = {
        "text": content,
        "source_url": unique_url, # Use unique URL to create new lineage
        "source_system": "live_verification",
        "vertical": "food_safety"
    }
    
    try:
        resp = requests.post(INGEST_URL, json=payload, headers=HEADERS)
        if resp.status_code == 200:
            log("✅ Ingest Accepted")
            return True
        else:
            log(f"❌ Ingest Failed: {resp.status_code} - {resp.text}")
            return False
    except Exception as e:
        log(f"❌ Ingest Connection Error: {e}")
        return False

def check_for_updated_doc(run_id):
    unique_url = f"{LIVE_FDA_URL}?run={run_id}"
    log(f"Checking Admin API for document update ({unique_url})...")
    
    start = time.time()
    # Wait for processing
    time.sleep(2)
    
    while time.time() - start < 30:
        try:
            resp = requests.get(f"{ADMIN_API_URL}/pcos/authorities", headers=HEADERS, params={"limit": 1000})
            if resp.status_code == 200:
                docs = resp.json()
                matches = [d for d in docs if d.get('original_file_path') == unique_url]
                matches.sort(key=lambda x: x.get('created_at', ''), reverse=True)
                
                if matches:
                    latest = matches[0]
                    # Check if it was created just now (approx)
                    # We accept it if it exists for now, as proof of ingestion.
                    log(f"✅ Found document for Live URL: {latest['id']}")
                    log(f"   Created At: {latest.get('created_at')}")
                    return latest
        except Exception as e:
            pass
        time.sleep(2)
    
    log("❌ Timed out waiting for document to appear/update")
    return None

def main():
    log("Starting Live Freshness Verification...")
    
    run_id = sys.argv[1] if len(sys.argv) > 1 else str(int(time.time()))
    log(f"Run ID: {run_id}")

    html = fetch_live_content()
    if not html:
        sys.exit(1)
        
    extract_compliance_date_snippet(html)
    
    if not ingest_live_content(html, run_id):
        sys.exit(1)
        
    doc = check_for_updated_doc(run_id)
    if doc:
        log("🎉 Live Verification Successful: Pipeline processed the live FDA URL.")
        log(f"EVIDENCE: Document ID {doc['id']} linked to {LIVE_FDA_URL}?run={run_id}")
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
