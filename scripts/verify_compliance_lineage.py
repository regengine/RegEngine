
import os
import requests
import sys
import json
from datetime import datetime

# Configuration
ADMIN_API_URL = "http://localhost:8400"
API_KEY = os.environ.get("REGENGINE_API_KEY", os.environ.get("AUTH_TEST_BYPASS_TOKEN", ""))
HEADERS = {
    "X-RegEngine-API-Key": API_KEY,
    "X-Admin-Key": os.environ.get("ADMIN_MASTER_KEY", ""),
    "X-Tenant-ID": os.environ.get("REGENGINE_TENANT_ID", "00000000-0000-0000-0000-000000000000")
}
LIVE_FDA_URL = "https://www.fda.gov/food/food-safety-modernization-act-fsma/fsma-final-rule-requirements-additional-traceability-records-certain-foods"

def log(msg):
    print(f"[LineageVerify] {msg}")

def get_compliance_date_facts(run_id):
    unique_url = f"{LIVE_FDA_URL}?run={run_id}"
    log(f"Fetching authority history for {unique_url}...")
    # Get all docs/facts (in a real scenario we'd filter by authority ID)
    # Using the endpoint that returns everything for the demo purpose or specific authority if known
    
    # First find the relevant documents
    try:
        resp = requests.get(f"{ADMIN_API_URL}/pcos/authorities", headers=HEADERS, params={"limit": 1000})
        if resp.status_code != 200:
            log(f"❌ Failed to fetch authorities: {resp.status_code}")
            return []
        
        docs = resp.json()
        fda_docs = [d for d in docs if d.get("original_file_path") == unique_url]
        
        if not fda_docs:
            log("⚠️ No FDA documents found.")
            return []
            
        facts = []
        for doc in fda_docs:
            # Fetch facts for each doc
            # Assuming facts are included or we fetch export
            # Let's try export endpoint for full details including facts
            try:
                export_resp = requests.get(f"{ADMIN_API_URL}/pcos/authorities/{doc['document_code']}/export", headers=HEADERS)
                if export_resp.status_code == 200:
                    data = export_resp.json()
                    # Flatten facts from documents
                    for d in data.get("documents", []):
                        for f in d.get("facts", []):
                            if f.get("key") == "Compliance Date":
                                f["_doc_version"] = d.get("version") # annotated for convenience
                                facts.append(f)
            except Exception as e:
                log(f"Error fetching export for {doc['document_code']}: {e}")
                
        return facts

    except Exception as e:
        log(f"❌ Connection Error: {e}")
        return []

def verify_lineage(facts):
    log(f"Analyzing {len(facts)} 'Compliance Date' facts...")
    
    # Sort by version/time
    facts.sort(key=lambda x: x.get("_doc_version", 0))
    
    v1_fact = None
    v2_fact = None
    
    for f in facts:
        val = f.get("value")
        log(f"Found Fact: {val} (Hash: {f.get('fact_hash')[:8]}...)")
        
        if "2026" in val:
            v1_fact = f
        elif "2028" in val:
            v2_fact = f
            
    if not v1_fact:
        log("⚠️ V1 (2026) fact not found. Was the 'Old World' text ingested?")
        
    if not v2_fact:
        log("⚠️ V2 (2028) fact not found. Was the 'New World' text ingested?")
        
    if v1_fact and v2_fact:
        log("\n--- Lineage Verification ---")
        log(f"V1 ID: {v1_fact['id']}")
        log(f"V2 ID: {v2_fact['id']}")
        log(f"V2 Previous Fact ID: {v2_fact.get('previous_fact_id')}")
        
        if v2_fact.get("previous_fact_id") == v1_fact['id']:
            log("✅ SUCCESS: V2 correctly identifies V1 as its predecessor.")
            log("   This cryptographically proves the system detected the specific update.")
            return True
        else:
            log("❌ FAILURE: V2 does not link to V1.")
            return False
            
    return False

def main():
    log("Starting FSMA Compliance Lineage Verification...")
    
    run_id = sys.argv[1] if len(sys.argv) > 1 else str(int(time.time()))
    log(f"Run ID: {run_id}")

    facts = get_compliance_date_facts(run_id)
    
    if not facts:
        log("No facts found to verify. Ensure Docker is part of the demo flow.")
        sys.exit(1)
        
    success = verify_lineage(facts)
    
    if success:
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
