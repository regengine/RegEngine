import os
import requests
import time
import json
import sys

# Consolidate config
INGEST_URL = "http://localhost:8002/v1/ingest"
ADMIN_API_URL = "http://localhost:8400"
TENANT_ID = os.environ.get("REGENGINE_TENANT_ID", "00000000-0000-0000-0000-000000000000")
API_KEY = os.environ.get("REGENGINE_API_KEY", os.environ.get("AUTH_TEST_BYPASS_TOKEN", ""))
ADMIN_MASTER_KEY = os.environ.get("ADMIN_MASTER_KEY", "")

# Unique Source for this Demo
SOURCE_URL = "http://demo.fda.gov/fsma-204-update-scenario"

# --- SCENARIO DATA ---

# State 1: Old World (Jan 2026)
CONTENT_OLD = """
<html>
<body>
    <h1>FSMA 204 Final Rule</h1>
    <p>The Food Traceability List (FTL) requires additional recordkeeping.</p>
    <p><b>Compliance Date:</b> January 20, 2026.</p>
    <p>All entities must be compliant by this date.</p>
</body>
</html>
"""

# State 2: New World (July 2028)
CONTENT_NEW = """
<html>
<body>
    <h1>FSMA 204 Final Rule - UPDATE</h1>
    <p>The Food Traceability List (FTL) requires additional recordkeeping.</p>
    <p><b>Compliance Date:</b> July 20, 2028.</p>
    <p>All entities must be compliant by this date.</p>
    <p><i>Update: Congressional directive delays enforcement.</i></p>
</body>
</html>
"""

HEADERS = {
    "X-RegEngine-API-Key": API_KEY,
    "X-Admin-Key": ADMIN_MASTER_KEY,
    "X-Tenant-ID": TENANT_ID,
    "Content-Type": "application/json"
}

def log(msg):
    print(f"[FreshnessDemo] {msg}")

def ingest_content(content, version_label):
    log(f"Ingesting {version_label} Content...")
    payload = {
        "text": content,
        "source_url": SOURCE_URL,
        "source_system": "manual_demo",
        "vertical": "food_safety"
    }
    try:
        resp = requests.post(INGEST_URL, json=payload, headers=HEADERS)
        if resp.status_code == 200:
            log(f"✅ Ingest {version_label} Accepted")
            return True
        else:
            log(f"❌ Ingest {version_label} Failed: {resp.status_code} - {resp.text}")
            return False
    except Exception as e:
        log(f"❌ Ingest Connection Error: {e}")
        return False

def wait_for_doc(expect_version, previous_id=None):
    log(f"Waiting for V{expect_version} Document...")
    start = time.time()
    while time.time() - start < 30:
        try:
            resp = requests.get(f"{ADMIN_API_URL}/pcos/authorities", headers=HEADERS)
            if resp.status_code == 200:
                docs = resp.json()
                matches = [d for d in docs if d.get('original_file_path') == SOURCE_URL]
                
                for d in matches:
                    # Heuristic for versioning in this demo
                    # If V1: just need a doc.
                    # If V2: need a doc that supersedes previous_id
                    if expect_version == 1:
                        if not d.get('supersedes_document_id'):
                            return d
                    elif expect_version == 2:
                        if d.get('supersedes_document_id') == previous_id:
                            return d
        except Exception:
            pass
        time.sleep(1)
    return None

def main():
    log("Starting Freshness Pipeline Demo...")
    
    # 1. Ingest Old Content
    if not ingest_content(CONTENT_OLD, "V1 (Old)"):
        sys.exit(1)
        
    doc_v1 = wait_for_doc(1)
    if not doc_v1:
        log("❌ Timed out waiting for V1 document")
        sys.exit(1)
    
    log(f"✅ V1 Document Created: {doc_v1['id']}")
    
    # 2. Ingest New Content (Trigger Update)
    time.sleep(2) # Ensure timestamp difference
    if not ingest_content(CONTENT_NEW, "V2 (New)"):
        sys.exit(1)
        
    doc_v2 = wait_for_doc(2, previous_id=doc_v1['id'])
    if not doc_v2:
        log("❌ Timed out waiting for V2 document (Supersession Chain)")
        sys.exit(1)
        
    log(f"✅ V2 Document Created: {doc_v2['id']}")
    log(f"   Supersedes: {doc_v2['supersedes_document_id']}")
    
    # Verify Content Difference detection via Facts (Optional deeply, but doc chaining proves it)
    log("🎉 Demo Successful: detected content change and maintained lineage.")

if __name__ == "__main__":
    main()
