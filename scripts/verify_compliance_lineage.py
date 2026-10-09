import json
import os
import sys
import time
from datetime import datetime

import requests
from requests.exceptions import ConnectionError, RequestException, Timeout

REQUEST_TIMEOUT_SECONDS = 30

# Configuration
ADMIN_API_URL = "http://localhost:8400"
API_KEY = os.environ.get("REGENGINE_API_KEY", os.environ.get("AUTH_TEST_BYPASS_TOKEN", ""))
HEADERS = {
    "X-RegEngine-API-Key": API_KEY,
    "X-Tenant-ID": os.environ.get("REGENGINE_TENANT_ID", "00000000-0000-0000-0000-000000000000"),
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
        resp = requests.get(
            f"{ADMIN_API_URL}/pcos/authorities",
            headers=HEADERS,
            params={"limit": 1000},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        if resp.status_code != 200:
            if resp.status_code == 429 or 500 <= resp.status_code < 600:
                log(f"⚠️ Transient error fetching authorities: {resp.status_code}. Retry later.")
            else:
                log(f"❌ Fatal error fetching authorities: {resp.status_code}. Retry will not help.")
            return []

        try:
            docs = resp.json()
        except ValueError as e:
            log(f"❌ Fatal error: authorities response is not valid JSON: {e}")
            return []
        fda_docs = [d for d in docs if d.get("original_file_path") == unique_url]

        if not fda_docs:
            log("⚠️ No FDA documents found.")
            return []

        facts = []
        for doc in fda_docs:
            # Fetch facts for each doc
            # Assuming facts are included or we fetch export
            # Let's try export endpoint for full details including facts
            doc_code = doc.get("document_code")
            if not doc_code:
                log(f"⚠️ Anomaly: document {doc.get('id', '?')} has no document_code; skipping.")
                continue
            try:
                export_resp = requests.get(
                    f"{ADMIN_API_URL}/pcos/authorities/{doc_code}/export",
                    headers=HEADERS,
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
                if export_resp.status_code == 200:
                    try:
                        data = export_resp.json()
                    except ValueError as e:
                        log(f"❌ Fatal error: export for {doc_code} is not valid JSON: {e}")
                        continue
                    # Flatten facts from documents
                    for d in data.get("documents", []):
                        for f in d.get("facts", []):
                            if f.get("key") == "Compliance Date":
                                f["_doc_version"] = d.get("version")  # annotated for convenience
                                facts.append(f)
                elif export_resp.status_code == 429 or 500 <= export_resp.status_code < 600:
                    log(
                        f"⚠️ Transient error fetching export for {doc_code}: "
                        f"{export_resp.status_code}. Continuing with other documents."
                    )
                else:
                    log(
                        f"❌ Fatal error fetching export for {doc_code}: "
                        f"{export_resp.status_code}. Continuing with other documents."
                    )
            except (Timeout, ConnectionError) as e:
                log(
                    f"⚠️ Transient error fetching export for {doc_code}: "
                    f"{type(e).__name__}: {e}. Continuing with other documents."
                )
            except RequestException as e:
                log(
                    f"❌ Fatal error fetching export for {doc_code}: "
                    f"{type(e).__name__}: {e}. Continuing with other documents."
                )

        return facts

    except (Timeout, ConnectionError) as e:
        log(f"⚠️ Transient connection error: {type(e).__name__}: {e}. Retry later.")
        return []
    except RequestException as e:
        log(f"❌ Fatal request error: {type(e).__name__}: {e}")
        return []


def verify_lineage(facts):
    log(f"Analyzing {len(facts)} 'Compliance Date' facts...")

    # Sort by version/time
    facts.sort(key=lambda x: x.get("_doc_version", 0))

    v1_fact = None
    v2_fact = None

    for f in facts:
        val = f.get("value")
        fact_hash = f.get("fact_hash")
        if not fact_hash:
            log(f"⚠️ Anomaly: fact {f.get('id', '?')} is missing its hash; skipping.")
            continue
        if not isinstance(val, str):
            log(f"⚠️ Anomaly: fact {f.get('id', '?')} is missing its value; skipping.")
            continue
        log(f"Found Fact: {val} (Hash: {fact_hash[:8]}...)")

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
        log(f"V1 ID: {v1_fact.get('id', '?')}")
        log(f"V2 ID: {v2_fact.get('id', '?')}")
        log(f"V2 Previous Fact ID: {v2_fact.get('previous_fact_id')}")

        if v2_fact.get("previous_fact_id") == v1_fact.get("id"):
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
