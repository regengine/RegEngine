import sys
import json
import hashlib
import requests
from dataclasses import dataclass
from typing import List, Dict, Optional, Any

@dataclass
class VerificationResult:
    hashes_verified: int
    hashes_failed: int
    lineage_links_verified: int
    lineage_links_failed: int
    orphans_found: int
    consistency_errors: int
    details: List[str]

class ChainVerifier:
    def __init__(self, export_data: Dict[str, Any]):
        self.data = export_data
        self.metadata = export_data.get("verification_metadata", {})
        self.results = VerificationResult(0, 0, 0, 0, 0, 0, [])

    def recompute_hash(self, fact: Dict) -> str:
        # Reconstruct hash input based on metadata algorithm
        # "key|value_type|value|conditions|source_page|source_section"
        
        # NOTE: This mirrors logic in AuthorityLineageService.export_authority_history logic
        # Ideally metadata would parse this dynamically, but hardcoding for Phase 4b
        
        # Serialize Value
        val = fact.get("value")
        val_str = ""
        
        # HACK: The service logic used strict type checks (json.dumps vs str). 
        # Here we attempt to replicate that. In export it comes as serialized JSON types.
        if isinstance(val, (dict, list)):
             val_str = json.dumps(val, sort_keys=True)
        elif val is None:
             val_str = ""
        else:
             val_str = str(val)
             
        # Conditions
        cond = fact.get("condition") or {}
        cond_str = json.dumps(cond, sort_keys=True)
        
        src = fact.get("source_ref") or {}
        page = src.get("page")
        sect = src.get("section")
        
        # Normalized input string matching Worker Logic:
        # hash_input = f"{fact_data['key']}|string|{val_str}|{{}}|None|None"
        # Since we backfilled with a heuristic that hardcoded {} and None/None
        
        # But wait, does existing data have source refs? 
        # The backfill in worker/main.py hardcoded: `validity_conditions={}, ...`
        # And `hash_input = f"...|{{}}|None|None"`
        
        # So for verification of these specific facts, we must expect None/None string literal
        page_str = str(page) if page is not None else "None"
        sect_str = str(sect) if sect is not None else "None"
        
        # Also validity_conditions was hardcoded as `{}` in worker hash input but the fact stores it.
        # If fact stored empty dict, `cond_str` is `{}`.
        
        hash_input = f"{fact['key']}|string|{val_str}|{cond_str}|{page_str}|{sect_str}"
        
        return hashlib.sha256(hash_input.encode('utf-8')).hexdigest()

    def verify(self) -> VerificationResult:
        print(f"Verifying Chain for Authority: {self.data.get('authority_code')}")
        
        all_facts = {}
        
        # 1. Verification of Content Hashes
        for doc in self.data.get("documents", []):
            for fact in doc.get("facts", []):
                computed = self.recompute_hash(fact)
                stored = fact.get("fact_hash")
                
                if computed == stored:
                    self.results.hashes_verified += 1
                else:
                    self.results.hashes_failed += 1
                    self.results.details.append(f"Hash Mismatch Fact {fact['key']}: Expected {computed}, Got {stored}")
                
                all_facts[fact['id']] = fact

        # 2. Verification of Lineage
        for fact_id, fact in all_facts.items():
            prev_id = fact.get("previous_fact_id")
            if prev_id:
                if prev_id not in all_facts:
                     self.results.lineage_links_failed += 1
                     self.results.details.append(f"Broken Link: Fact {fact['key']} (v{fact['version']}) points to missing ancestor {prev_id}")
                else:
                     parent = all_facts[prev_id]
                     if parent['key'] != fact['key']:
                         self.results.lineage_links_failed += 1
                         self.results.details.append(f"Key Mismatch: {fact['key']} -> {parent['key']}")
                     elif parent['version'] >= fact['version']:
                         self.results.consistency_errors += 1
                         self.results.details.append(f"Temporal Error: v{fact['version']} supersedes v{parent['version']}")
                     else:
                         self.results.lineage_links_verified += 1

        return self.results

def main():
    # 1. Fetch Export
    print("Fetching Audit Export...")
    try:
        # Assuming running against local docker stack
        headers = {"X-Tenant-ID": "00000000-0000-0000-0000-000000000000"} 
        # Using correct port 8400 for Admin API
        resp = requests.get("http://localhost:8400/pcos/authorities/DOC-c9d54044/export", headers=headers)
        
        if resp.status_code == 404:
             # Try logical code from test
             resp = requests.get("http://localhost:8400/pcos/authorities/DOC-MOCK-V1/export", headers=headers)

        # Fallback to FSMA if neither works (from test data)
        # Actually, let's look at the test output to see what code was used.
        # "DOC-c9d54044..." was a generated ID. The code was likely "DOC-MOCK-V1" or similar?
        # In worker line 112: `document_code=f"DOC-{event_data.get('document_id')[:8]}"`
        # In test, document_id starts as random UUID.
        
        # Let's try to list first to get the code
        list_resp = requests.get("http://localhost:8400/pcos/authorities", headers=headers)
        if list_resp.status_code == 200:
            docs = list_resp.json()
            if docs:
                code = docs[0]['document_code']
                print(f"Found Authority Code: {code}")
                resp = requests.get(f"http://localhost:8400/pcos/authorities/{code}/export", headers=headers)

        if resp.status_code != 200:
             print(f"Failed to fetch export: {resp.status_code} {resp.text}")
             sys.exit(1)
             
        export_data = resp.json()
        
        # 2. Verify
        verifier = ChainVerifier(export_data)
        results = verifier.verify()
        
        print("\n--- Verification Results ---")
        print(f"Content Hashes: {results.hashes_verified} Verified, {results.hashes_failed} Failed")
        print(f"Lineage Links:  {results.lineage_links_verified} Verified, {results.lineage_links_failed} Failed")
        print(f"Consistency:    {results.consistency_errors} Errors")
        
        for detail in results.details:
            print(f"ERROR: {detail}")
            
        if results.hashes_failed == 0 and results.lineage_links_failed == 0 and results.consistency_errors == 0:
            print("\n✅ INDEPENDENT VERIFICATION PASSED")
            sys.exit(0)
        else:
            print("\n❌ INDEPENDENT VERIFICATION FAILED")
            sys.exit(1)

    except Exception as e:
        print(f"Fatal Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
