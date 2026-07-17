"""Deterministic evidence bundle for a manifest ingestion run.

Layout follows the FDA export package convention: content files + a
manifest.json carrying per-file and per-record SHA-256 hashes. The bundle
timestamp is excluded from every content hash, and zip member timestamps
are fixed, so re-exporting unchanged accepted content yields identical
record hashes (and, in practice, an identical archive).
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone
from typing import Any, Dict, List

from shared.fda_export.csv_safety import safe_cell

from .corrections import load_patches
from .validation import RULESET_HASH, canonical_json

_ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)

_CSV_COLUMNS = [
    "row_number",
    "cte_type",
    "traceability_lot_code",
    "product_description",
    "quantity",
    "unit_of_measure",
    "event_date",
    "location",
    "tlc_source_reference",
    "reference_document",
    "released_event_id",
]

_DISCLAIMER = (
    "Hashes in this bundle demonstrate post-ingest integrity only: they prove "
    "the accepted data has not changed since export, not that the original "
    "supplier submission was factually true. This bundle is not an FDA "
    "approval and carries no guarantee of regulatory compliance."
)


def record_hash(normalized_payload: Dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(normalized_payload).encode()).hexdigest()


def _accepted_csv(records: List[Dict[str, Any]]) -> str:
    import csv as csv_mod

    buf = io.StringIO()
    writer = csv_mod.writer(buf, quoting=csv_mod.QUOTE_ALL, lineterminator="\n")
    writer.writerow(_CSV_COLUMNS)
    for record in records:
        event = record["normalized_payload"] or {}
        kdes = event.get("kdes") or {}
        row = [
            record["row_number"],
            event.get("cte_type", ""),
            event.get("traceability_lot_code", ""),
            event.get("product_description", ""),
            event.get("quantity", ""),
            event.get("unit_of_measure", ""),
            event.get("timestamp") or kdes.get("receive_date") or kdes.get("ship_date") or "",
            event.get("location_name") or kdes.get("receiving_location") or "",
            kdes.get("tlc_source_reference", ""),
            kdes.get("reference_document", ""),
            record["released_event_id"] or "",
        ]
        writer.writerow([safe_cell(cell) for cell in row])
    return buf.getvalue()


def build_bundle(db, *, tenant_id: str, run_meta: Dict[str, Any], records: List[Dict[str, Any]], run_id: str) -> bytes:
    released = [r for r in records if r["release_status"] == "released"]
    released.sort(key=lambda r: r["row_number"])

    accepted_csv = _accepted_csv(released)
    original_bytes = run_meta["raw_bytes"]

    record_entries = []
    for record in records:
        patches = load_patches(db, tenant_id=tenant_id, manifest_record_id=record["id"])
        record_entries.append(
            {
                "row_number": record["row_number"],
                "record_id": record["id"],
                "row_fingerprint": record["row_fingerprint"],
                "validation_status": record["validation_status"],
                "release_status": record["release_status"],
                "released_event_id": record["released_event_id"],
                "record_hash": record_hash(record["normalized_payload"] or {}),
                "correction_patch_hashes": [p["patch_hash"] for p in patches],
                "ruleset_hash": record["ruleset_hash"],
            }
        )

    content_files = {
        "original_manifest.csv": original_bytes,
        "accepted_records.csv": accepted_csv.encode(),
    }
    file_hashes = {name: hashlib.sha256(data).hexdigest() for name, data in content_files.items()}
    bundle_content_hash = hashlib.sha256(
        canonical_json(
            {
                "file_hashes": file_hashes,
                "records": record_entries,
                "source_sha256": run_meta["sha256"],
                "ruleset_hash": RULESET_HASH,
            }
        ).encode()
    ).hexdigest()

    generated_at = datetime.now(timezone.utc).isoformat()
    manifest = {
        "bundle_version": 1,
        "ingestion_run_id": run_id,
        "source_file": {
            "name": run_meta["filename"],
            "sha256": run_meta["sha256"],
            "size_bytes": len(original_bytes),
        },
        "ruleset_hash": RULESET_HASH,
        "records": record_entries,
        "file_hashes": file_hashes,
        "bundle_content_hash": bundle_content_hash,
        "generated_at": generated_at,  # excluded from bundle_content_hash
        "integrity_note": _DISCLAIMER,
    }

    summary_lines = [
        "SUPPLIER MANIFEST EVIDENCE SUMMARY",
        f"Manifest: {run_meta['filename']} (sha256 {run_meta['sha256']})",
        f"Rows: {len(records)} total, {len(released)} released",
        f"Ruleset: {RULESET_HASH}",
        "",
        "Per-record status:",
    ]
    for entry in record_entries:
        summary_lines.append(
            f"  row {entry['row_number']}: {entry['validation_status']}/{entry['release_status']}"
            + (f" -> event {entry['released_event_id']}" if entry["released_event_id"] else "")
            + (
                f" ({len(entry['correction_patch_hashes'])} correction patch(es))"
                if entry["correction_patch_hashes"]
                else ""
            )
        )
    summary_lines += ["", _DISCLAIMER]

    readme = (
        "RegEngine supplier-remediation evidence bundle\n\n"
        "Files:\n"
        "  original_manifest.csv — byte-exact preserved supplier upload\n"
        "  accepted_records.csv  — current accepted (released) records\n"
        "  manifest.json         — hashes, provenance, correction patch chain heads\n"
        "  summary.txt           — human-readable verification summary\n\n"
        f"Generated at: {generated_at}\n\n"
        f"{_DISCLAIMER}\n"
    )

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in sorted(
            {
                **content_files,
                "manifest.json": json.dumps(manifest, indent=2, sort_keys=True).encode(),
                "summary.txt": "\n".join(summary_lines).encode(),
                "README.txt": readme.encode(),
            }.items()
        ):
            info = zipfile.ZipInfo(name, date_time=_ZIP_EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, data)
    return out.getvalue()
