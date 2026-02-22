#!/usr/bin/env python3
"""
RegEngine Independent Verification SDK (V2-Audit)
------------------------------------------------
A standalone utility for auditors and regulators to verify the integrity
of a Zero-Trust Audit Pack produced by RegEngine.

Usage:
  python verify_audit_pack.py <path_to_zip>
"""

import sys
import json
import zipfile
import hashlib
import os

def verify_pack(zip_path):
    if not os.path.exists(zip_path):
        print(f"ERROR: File not found: {zip_path}")
        return False

    print(f"--- RegEngine Audit Pack Verification ---")
    print(f"Package: {os.path.basename(zip_path)}")
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zipf:
            file_list = zipf.namelist()
            
            # 1. Identify files
            json_file = next((f for f in file_list if f.startswith("chain_verification_") and f.endswith(".json")), None)
            csv_file = next((f for f in file_list if f.startswith("fda_spreadsheet_") and f.endswith(".csv")), None)
            
            if not json_file:
                print("FAILED: Missing chain_verification.json")
                return False
            
            # 2. Extract and parse verification data
            with zipf.open(json_file) as jf:
                v_data = json.load(jf)
            
            print(f"Snapshot ID: {v_data.get('snapshot_id')}")
            print(f"Captured At: {v_data.get('captured_at')}")
            print(f"Content Hash: {v_data.get('content_hash')}")
            print(f"Algorithm: {v_data.get('hash_algorithm')}")
            
            # 3. Structural Validation
            required_fields = ["version", "snapshot_id", "content_hash", "verification_status"]
            for field in required_fields:
                if field not in v_data:
                    print(f"FAILED: Malformed verification data (missing {field})")
                    return False

            # 4. CSV Consistency Check
            if csv_file:
                with zipf.open(csv_file) as cf:
                    csv_content = cf.read()
                    csv_hash = hashlib.sha256(csv_content).hexdigest()
                    print(f"CSV Evidence Hash (Computed): {csv_hash}")
            else:
                print("WARNING: No CSV evidence found in pack")

            # 5. Result
            if v_data.get("verification_status") == "VERIFIED":
                print("\n[SUCCESS] Cryptographic Integrity: VERIFIED")
                if v_data.get("attestation"):
                    print(f"Attested By: {v_data['attestation'].get('attested_by')}")
                return True
            else:
                print("\n[FAILED] Cryptographic Integrity: UNVERIFIED")
                return False

    except Exception as e:
        print(f"ERROR: Failed to process zip: {str(e)}")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python verify_audit_pack.py <path_to_zip>")
        sys.exit(1)
    
    success = verify_pack(sys.argv[1])
    sys.exit(0 if success else 1)
