#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""
verify_records.py - Independent Hash Verification for RegEngine Records

This open-source script allows anyone to independently verify the cryptographic
integrity of RegEngine traceability records without relying on RegEngine servers.

Usage:
    regengine-verify --tlc LOT-2026-001 --api-key rge_live_xxx
    regengine-verify --file exported_records.json --offline
    regengine-verify --audit-pack audit_2026_02.zip

The "Verify, Don't Trust" principle: You maintain full control of verification.

NOTE (#2507): this is the per-RECORD verifier — it recomputes each canonical
record's ``sha256_hash`` (see ``compute_record_hash``). It is a DIFFERENT
program from ``frontend/public/sdk/verify_chain.py``, which verifies a
``/proof`` Merkle BUNDLE (per-file leaf hashes + Merkle root). This tool was
renamed from ``verify_chain.py`` -> ``verify_records.py`` (WS-11) to end the
filename collision; the bundle tool keeps its name because it is served at
the public URL https://regengine.co/sdk/verify_chain.py, which external
auditors curl (renaming it would break published instructions). A
deprecation shim remains at ``regengine.verify_chain``.

License: Apache-2.0 — see the repository LICENSE's permissive-exceptions
clause. Previously MIT; copies received under MIT remain MIT-licensed.
"""

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

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


def _first(record: dict, *keys: str, default: str = "") -> str:
    """Return the first present, non-None value among ``keys``.

    Lets the verifier read both the canonical export key
    (``traceability_lot_code``) and any short alias (``tlc``) without
    diverging from the production hash inputs.
    """
    for key in keys:
        value = record.get(key)
        if value is not None:
            return value
    return default


def compute_record_hash(record: dict) -> str:
    """
    Recompute the SHA-256 ``sha256_hash`` of a canonical traceability record.

    This MUST stay byte-for-byte identical to the server's
    ``TraceabilityEvent.compute_sha256_hash`` in
    ``services/shared/canonical_event.py`` — the function that produces the
    ``sha256_hash`` written to ``fsma.traceability_events`` and emitted in
    canonical exports. Any divergence makes every authentic record verify
    as INVALID (#2507).

    Canonical form (pipe-delimited, in this exact order), bare hex digest
    with NO ``sha256:`` prefix:

        event_id | event_type | traceability_lot_code | product_reference |
        quantity | unit_of_measure | from_facility_reference |
        to_facility_reference | event_timestamp |
        json.dumps(kdes, sort_keys=True, default=str)

    Field aliases (``tlc`` for ``traceability_lot_code`` etc.) are accepted
    so the verifier works against either the raw canonical export keys or a
    flattened pack, but the hashed VALUES are the canonical ones.
    """
    event_id = _first(record, "event_id", "id")
    event_type = _first(record, "event_type", "cte_type")
    tlc = _first(record, "traceability_lot_code", "tlc")
    product_reference = _first(record, "product_reference")
    quantity = record.get("quantity", 0)
    unit_of_measure = _first(record, "unit_of_measure")
    from_facility = _first(record, "from_facility_reference", "location")
    to_facility = _first(record, "to_facility_reference")
    event_timestamp = _first(record, "event_timestamp")
    kdes = record.get("kdes", {})

    canonical = "|".join(
        [
            str(event_id),
            event_type,
            tlc,
            product_reference,
            str(quantity),
            unit_of_measure,
            from_facility,
            to_facility,
            event_timestamp,
            json.dumps(kdes, sort_keys=True, default=str),
        ]
    )

    # Bare hex — matches the server's ``hexdigest()`` (no ``sha256:`` prefix).
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def verify_record_offline(record: dict) -> VerificationResult:
    """Verify a record's hash offline using local data only."""
    tlc = _first(record, "traceability_lot_code", "tlc", default="UNKNOWN")
    # Canonical exports emit the per-record digest as ``sha256_hash``;
    # accept a bare ``hash`` alias for flattened packs.
    expected_hash = _first(record, "sha256_hash", "hash")

    try:
        computed_hash = compute_record_hash(record)
        valid = computed_hash == expected_hash

        return VerificationResult(
            tlc=tlc,
            expected_hash=expected_hash,
            computed_hash=computed_hash,
            valid=valid,
            verified_at=datetime.utcnow().isoformat() + "Z",
        )
    except Exception as e:
        return VerificationResult(tlc=tlc, expected_hash=expected_hash, computed_hash="", valid=False, error=str(e))


def verify_record_online(tlc: str, api_key: str, base_url: str = "https://api.regengine.co") -> VerificationResult:
    """Verify a record against the RegEngine API."""
    if not HAS_REQUESTS:
        return VerificationResult(
            tlc=tlc,
            expected_hash="",
            computed_hash="",
            valid=False,
            error="requests library not installed. Run: pip install requests",
        )

    try:
        # Fetch record
        headers = {"Authorization": f"Bearer {api_key}"}
        resp = requests.get(f"{base_url}/api/graph/fsma/v1/records/{tlc}", headers=headers, timeout=30)
        resp.raise_for_status()
        record = resp.json()

        # Verify locally
        result = verify_record_offline(record)

        # Cross-check with server's verification endpoint
        verify_resp = requests.get(f"{base_url}/api/graph/fsma/v1/records/{tlc}/verify", headers=headers, timeout=30)
        if verify_resp.ok:
            verify_data = verify_resp.json()
            result.chain_position = verify_data.get("chain_position")
            # Double-check: our hash should match server's
            if verify_data.get("hash") != result.computed_hash:
                result.valid = False
                result.error = "Hash mismatch between local and server verification"

        return result

    except requests.exceptions.RequestException as e:
        return VerificationResult(
            tlc=tlc, expected_hash="", computed_hash="", valid=False, error=f"API request failed: {e}"
        )


# Envelope keys under which the platform's own export surfaces publish the
# record array. ``records`` is the SDK/audit-pack shape; ``events`` is what
# the canonical list endpoint returns
# (services/ingestion/app/canonical_router.py:158 —
# ``{"tenant_id": ..., "events": [...], "total": N}``). Before #2955 only
# ``records`` was recognised, so a real canonical export fell through to a
# ``[data]`` fallback and the whole envelope dict was hashed as one record.
RECORD_ENVELOPE_KEYS = ("records", "events")

# A bare dict is only treated as a single record if it actually looks like
# one — i.e. it carries a per-record digest. Anything else is an
# unrecognised envelope and is rejected loudly rather than hashed whole.
_RECORD_HASH_KEYS = ("sha256_hash", "hash")


class UnrecognizedExportError(ValueError):
    """Raised when an input file is not a shape the verifier can verify."""


def extract_records(data: object) -> List[dict]:
    """Pull the record array out of a parsed export file.

    Accepts a bare JSON array, or an object carrying the array under one of
    :data:`RECORD_ENVELOPE_KEYS`. A bare object that looks like a single
    record (it has a ``sha256_hash``/``hash``) is treated as a one-record
    input. Anything else raises :class:`UnrecognizedExportError` instead of
    silently hashing the envelope as if it were a record (#2955).
    """
    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        for key in RECORD_ENVELOPE_KEYS:
            value = data.get(key)
            if isinstance(value, list):
                return value
            if value is not None:
                raise UnrecognizedExportError(
                    f'Export key "{key}" is a {type(value).__name__}, expected a list of records.'
                )
        if any(key in data for key in _RECORD_HASH_KEYS):
            return [data]
        raise UnrecognizedExportError(
            "Unrecognized export envelope: expected a JSON array, or an object with a "
            f"record list under one of {list(RECORD_ENVELOPE_KEYS)}, or a single record "
            f"carrying one of {list(_RECORD_HASH_KEYS)}. Got an object with keys: "
            f"{sorted(data)}"
        )

    raise UnrecognizedExportError(
        f"Unrecognized export structure: expected a JSON array or object, got {type(data).__name__}."
    )


def verify_file(file_path: Path) -> List[VerificationResult]:
    """Verify all records in a JSON file.

    Raises:
        UnrecognizedExportError: if the file is not a shape whose records
            can be located. Callers must not treat that as "verified".
    """
    with open(file_path, "r") as f:
        data = json.load(f)

    records = extract_records(data)
    return [verify_record_offline(r) for r in records]


def print_results(results: List[VerificationResult]) -> int:
    """Print verification results and return exit code.

    Returns non-zero when nothing was verified (#2955): an empty result set
    used to print ``SUMMARY: 0 passed, 0 failed, 0 total`` and return 0, so a
    scripted auditor check could not distinguish "every record verified" from
    "there was nothing to verify".
    """
    passed = 0
    failed = 0

    print("\n" + "=" * 60)
    print("REGENGINE CHAIN VERIFICATION REPORT")
    print("=" * 60)
    print(f"Verified at: {datetime.utcnow().isoformat()}Z")
    print("-" * 60)

    if not results:
        print("\nNO RECORDS VERIFIED")
        print(
            "  No records were found in the input. Nothing was verified — this is NOT a pass.\n"
            f"  Looked for: a JSON array, or an object with a record list under one of "
            f"{list(RECORD_ENVELOPE_KEYS)}."
        )
        print("\n" + "-" * 60)
        print("SUMMARY: 0 passed, 0 failed, 0 total — NO RECORDS VERIFIED")
        print("=" * 60 + "\n")
        return 1

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


def _sdk_version() -> str:
    """Report the SDK package version — one source of truth (__init__.py).

    Falls back to "standalone" when the script is run as a lone file
    outside the package (auditors are told they can download and run it
    independently), where the relative import has no parent package.
    """
    try:
        from . import __version__

        return __version__
    except ImportError:
        return "standalone"


def main():
    parser = argparse.ArgumentParser(
        description="Independently verify RegEngine traceability record integrity",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Verify a single lot online
  regengine-verify --tlc LOT-2026-001 --api-key rge_live_xxx
  
  # Verify exported records offline
  regengine-verify --file exported_records.json --offline
  
  # Verify an FDA audit pack
  regengine-verify --audit-pack audit_2026_02.zip
        """,
    )

    parser.add_argument("--tlc", help="Traceability Lot Code to verify")
    parser.add_argument("--api-key", help="RegEngine API key")
    parser.add_argument("--file", type=Path, help="JSON file with records to verify")
    parser.add_argument("--offline", action="store_true", help="Verify without API calls")
    parser.add_argument("--base-url", default="https://api.regengine.co", help="API base URL")
    parser.add_argument("--version", action="version", version=f"regengine-verify {_sdk_version()}")

    args = parser.parse_args()

    results = []

    if args.file:
        # #2955: --file and --tlc select different verification modes; before,
        # --tlc (and --offline) were silently ignored when --file was given, so
        # the exit status did not say which mode actually ran.
        if args.tlc:
            print(
                "Error: --file and --tlc are mutually exclusive (choose file or online verification)", file=sys.stderr
            )
            sys.exit(1)
        if not args.file.exists():
            print(f"Error: File not found: {args.file}", file=sys.stderr)
            sys.exit(1)
        try:
            results = verify_file(args.file)
        except UnrecognizedExportError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        except json.JSONDecodeError as e:
            print(f"Error: {args.file} is not valid JSON: {e}", file=sys.stderr)
            sys.exit(1)

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


if __name__ == "__main__":
    main()
