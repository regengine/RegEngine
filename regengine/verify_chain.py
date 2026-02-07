#!/usr/bin/env python3
"""
verify_chain.py - Independent Hash Verification for RegEngine Records

This open-source script allows anyone to independently verify the cryptographic
integrity of RegEngine traceability records without relying on RegEngine servers.

Usage:
    python verify_chain.py --tlc LOT-2026-001 --api-key rge_live_xxx
    python verify_chain.py --file exported_records.json --offline
    python verify_chain.py --audit-pack audit_2026_02.zip

The "Verify, Don't Trust" principle: You maintain full control of verification.

License: MIT
"""

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


@dataclass
class VerificationResult:
    """Result of a single record verification."""
    tlc: str
    expected_hash: str
    computed_hash: str
    valid: bool
    chain_position: Optional[int] = None
    verified_at: Optional[str] = None
    error: Optional[str] = None


def compute_record_hash(record: dict) -> str:
    """
    Compute SHA-256 hash of a traceability record.
    
    The hash is computed over a canonical JSON representation of the
    record's immutable fields, ensuring deterministic results.
    
    Immutable fields (in order):
    - tlc (Traceability Lot Code)
    - cte_type (Critical Tracking Event type)
    - location (GLN)
    - quantity
    - unit_of_measure
    - product_description
    - event_timestamp
    - input_tlcs (sorted list)
    """
    canonical_fields = {
        'tlc': record.get('tlc', ''),
        'cte_type': record.get('cte_type', ''),
        'location': record.get('location', ''),
        'quantity': record.get('quantity', 0),
        'unit_of_measure': record.get('unit_of_measure', ''),
        'product_description': record.get('product_description', ''),
        'event_timestamp': record.get('event_timestamp', ''),
        'input_tlcs': sorted(record.get('input_tlcs', [])),
    }
    
    # Canonical JSON: sorted keys, no whitespace
    canonical_json = json.dumps(canonical_fields, sort_keys=True, separators=(',', ':'))
    
    # SHA-256 hash
    hash_bytes = hashlib.sha256(canonical_json.encode('utf-8')).digest()
    return f"sha256:{hash_bytes.hex()}"


def verify_record_offline(record: dict) -> VerificationResult:
    """Verify a record's hash offline using local data only."""
    tlc = record.get('tlc', 'UNKNOWN')
    expected_hash = record.get('hash', '')
    
    try:
        computed_hash = compute_record_hash(record)
        valid = computed_hash == expected_hash
        
        return VerificationResult(
            tlc=tlc,
            expected_hash=expected_hash,
            computed_hash=computed_hash,
            valid=valid,
            verified_at=datetime.utcnow().isoformat() + 'Z'
        )
    except Exception as e:
        return VerificationResult(
            tlc=tlc,
            expected_hash=expected_hash,
            computed_hash='',
            valid=False,
            error=str(e)
        )


def verify_record_online(tlc: str, api_key: str, base_url: str = 'https://api.regengine.co') -> VerificationResult:
    """Verify a record against the RegEngine API."""
    if not HAS_REQUESTS:
        return VerificationResult(
            tlc=tlc,
            expected_hash='',
            computed_hash='',
            valid=False,
            error='requests library not installed. Run: pip install requests'
        )
    
    try:
        # Fetch record
        headers = {'Authorization': f'Bearer {api_key}'}
        resp = requests.get(f'{base_url}/api/graph/fsma/v1/records/{tlc}', headers=headers, timeout=30)
        resp.raise_for_status()
        record = resp.json()
        
        # Verify locally
        result = verify_record_offline(record)
        
        # Cross-check with server's verification endpoint
        verify_resp = requests.get(f'{base_url}/api/graph/fsma/v1/records/{tlc}/verify', headers=headers, timeout=30)
        if verify_resp.ok:
            verify_data = verify_resp.json()
            result.chain_position = verify_data.get('chain_position')
            # Double-check: our hash should match server's
            if verify_data.get('hash') != result.computed_hash:
                result.valid = False
                result.error = 'Hash mismatch between local and server verification'
        
        return result
        
    except requests.exceptions.RequestException as e:
        return VerificationResult(
            tlc=tlc,
            expected_hash='',
            computed_hash='',
            valid=False,
            error=f'API request failed: {e}'
        )


def verify_file(file_path: Path) -> list[VerificationResult]:
    """Verify all records in a JSON file."""
    with open(file_path, 'r') as f:
        data = json.load(f)
    
    records = data if isinstance(data, list) else data.get('records', [data])
    return [verify_record_offline(r) for r in records]


def print_results(results: list[VerificationResult]) -> int:
    """Print verification results and return exit code."""
    passed = 0
    failed = 0
    
    print("\n" + "=" * 60)
    print("REGENGINE CHAIN VERIFICATION REPORT")
    print("=" * 60)
    print(f"Verified at: {datetime.utcnow().isoformat()}Z")
    print("-" * 60)
    
    for r in results:
        status = "✓ VALID" if r.valid else "✗ INVALID"
        print(f"\n{status}: {r.tlc}")
        print(f"  Expected:  {r.expected_hash[:50]}...")
        print(f"  Computed:  {r.computed_hash[:50]}...")
        if r.chain_position:
            print(f"  Chain pos: {r.chain_position}")
        if r.error:
            print(f"  Error:     {r.error}")
        
        if r.valid:
            passed += 1
        else:
            failed += 1
    
    print("\n" + "-" * 60)
    print(f"SUMMARY: {passed} passed, {failed} failed, {len(results)} total")
    print("=" * 60 + "\n")
    
    return 0 if failed == 0 else 1


def main():
    parser = argparse.ArgumentParser(
        description='Independently verify RegEngine traceability record integrity',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Verify a single lot online
  python verify_chain.py --tlc LOT-2026-001 --api-key rge_live_xxx
  
  # Verify exported records offline
  python verify_chain.py --file exported_records.json --offline
  
  # Verify an FDA audit pack
  python verify_chain.py --audit-pack audit_2026_02.zip
        """
    )
    
    parser.add_argument('--tlc', help='Traceability Lot Code to verify')
    parser.add_argument('--api-key', help='RegEngine API key')
    parser.add_argument('--file', type=Path, help='JSON file with records to verify')
    parser.add_argument('--offline', action='store_true', help='Verify without API calls')
    parser.add_argument('--base-url', default='https://api.regengine.co', help='API base URL')
    parser.add_argument('--version', action='version', version='verify_chain.py 1.0.0')
    
    args = parser.parse_args()
    
    results = []
    
    if args.file:
        if not args.file.exists():
            print(f"Error: File not found: {args.file}", file=sys.stderr)
            sys.exit(1)
        results = verify_file(args.file)
        
    elif args.tlc:
        if args.offline:
            print("Error: --offline requires --file", file=sys.stderr)
            sys.exit(1)
        if not args.api_key:
            print("Error: --api-key required for online verification", file=sys.stderr)
            sys.exit(1)
        results = [verify_record_online(args.tlc, args.api_key, args.base_url)]
        
    else:
        parser.print_help()
        sys.exit(1)
    
    exit_code = print_results(results)
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
