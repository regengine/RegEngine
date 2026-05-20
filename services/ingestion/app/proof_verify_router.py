"""Public proof-of-export verification endpoint.

Why this belongs in the FSMA pipeline (production-surface promotion rule
per ``PRODUCTION_SURFACE.md``):

The core production contract is::

    ingest -> canonicalize -> validate -> persist evidence -> export

This router adds a public, tenantless surface in front of the *export*
stage. It is the FSMA pipeline's audit-chain attestation surface: an
external auditor, regulator, retailer, or trade-partner who has been
handed a RegEngine FDA export bundle (ZIP) can independently verify
the bundle's hash chain and Merkle root **without an account, without
tenant context, and without reading any tenant data**. The endpoint
operates purely on the bytes the caller uploaded.

This is the public proof surface for the audit chain — it makes the
hash-chain promise externally checkable, which is the whole point of
having one. Because verification is purely structural (hash recompute,
Merkle root recompute, manifest cross-check), there is nothing tenant
-scoped to leak. The endpoint MUST NOT touch any database, queue, or
tenant-scoped store; static analysis of this module should show zero
imports of ``shared.database``, ``CTEPersistence``, or any tenant-scoped
client.

Endpoint: ``POST /api/v1/proof/verify``
- ``multipart/form-data`` with a single ``bundle`` field (ZIP, <= 5 MB)
- OR ``application/json`` with ``{manifest, events, merkle_root}``.
- No auth. Rate-limited 10 requests/minute/IP via the shared slowapi
  ``limiter`` (``shared.rate_limit``).

Returned JSON::

    {
      "verified": bool,
      "checks": [{"name": str, "passed": bool, "detail": str}, ...],
      "merkle_root_recomputed": str,
      "timestamp": iso8601
    }
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import zipfile
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from shared.merkle_tree import MerkleTree
from shared.rate_limit import limiter

logger = logging.getLogger("proof-verify")

router = APIRouter(prefix="/api/v1/proof", tags=["Public Proof"])


# ---------------------------------------------------------------------------
# Hard limits — public surface, hostile callers assumed
# ---------------------------------------------------------------------------
MAX_BUNDLE_BYTES = 5 * 1024 * 1024  # 5 MB
MAX_DECOMPRESSED_BYTES = 25 * 1024 * 1024  # 5x — defense against zip bombs
MAX_ZIP_ENTRIES = 64
ALLOWED_BUNDLE_CONTENT_TYPES = {
    "application/zip",
    "application/x-zip-compressed",
    "application/octet-stream",  # browsers/curl often default to this for .zip
    "multipart/form-data",
}


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------
class JsonBundle(BaseModel):
    """Lightweight JSON shape for callers who don't want to send a ZIP."""

    manifest: dict[str, Any] = Field(default_factory=dict)
    events: list[dict[str, Any]] = Field(default_factory=list)
    merkle_root: Optional[str] = None


class VerifyCheck(BaseModel):
    name: str
    passed: bool
    detail: str


class VerifyResponse(BaseModel):
    verified: bool
    checks: list[VerifyCheck]
    merkle_root_recomputed: str
    timestamp: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_ip(client_host: Optional[str]) -> str:
    """Anonymize the caller IP for log correlation."""
    if not client_host:
        return "unknown"
    return hashlib.sha256(client_host.encode("utf-8")).hexdigest()[:16]


def _safe_zip_member(name: str) -> bool:
    """Reject path-traversal and absolute-path entries."""
    if not name or name.endswith("/"):
        return False
    if name.startswith("/") or name.startswith("\\"):
        return False
    if ".." in name.replace("\\", "/").split("/"):
        return False
    if ":" in name:  # Windows drive letters
        return False
    return True


def _extract_event_hashes(events: list[dict[str, Any]]) -> list[str]:
    """Pull ``event_hash`` / ``sha256_hash`` from event dicts in order.

    Accepts either key — the FDA export embeds ``sha256_hash`` per event,
    while a stripped-down JSON bundle may use ``event_hash``.
    """
    hashes: list[str] = []
    for event in events:
        h = (
            event.get("event_hash")
            or event.get("sha256_hash")
            or event.get("hash")
        )
        if not isinstance(h, str) or len(h) != 64:
            raise ValueError(
                "events must each carry a 64-char hex 'event_hash' / "
                "'sha256_hash'"
            )
        hashes.append(h)
    return hashes


def _verify_payload(
    *,
    manifest: dict[str, Any],
    events: list[dict[str, Any]],
    declared_root: Optional[str],
    extra_checks: Optional[list[VerifyCheck]] = None,
) -> VerifyResponse:
    """Compute checks + Merkle root for a normalized payload."""
    checks: list[VerifyCheck] = list(extra_checks or [])

    # ---- Schema sanity ----
    if not isinstance(events, list) or not events:
        checks.append(
            VerifyCheck(
                name="events_present",
                passed=False,
                detail="bundle has no events to verify",
            )
        )
        return VerifyResponse(
            verified=False,
            checks=checks,
            merkle_root_recomputed="",
            timestamp=_now_iso(),
        )
    checks.append(
        VerifyCheck(
            name="events_present",
            passed=True,
            detail=f"{len(events)} event(s) found",
        )
    )

    # ---- Event hash extraction ----
    try:
        event_hashes = _extract_event_hashes(events)
    except ValueError as exc:
        checks.append(
            VerifyCheck(
                name="event_hashes_well_formed",
                passed=False,
                detail=str(exc),
            )
        )
        return VerifyResponse(
            verified=False,
            checks=checks,
            merkle_root_recomputed="",
            timestamp=_now_iso(),
        )
    checks.append(
        VerifyCheck(
            name="event_hashes_well_formed",
            passed=True,
            detail=f"{len(event_hashes)} hashes parsed",
        )
    )

    # ---- Recompute Merkle root ----
    tree = MerkleTree(event_hashes)
    recomputed = tree.root

    # ---- Compare to declared root (if provided) ----
    if declared_root:
        passed = recomputed == declared_root
        checks.append(
            VerifyCheck(
                name="merkle_root_matches_declared",
                passed=passed,
                detail=(
                    "recomputed root matches caller-supplied root"
                    if passed
                    else f"declared={declared_root[:16]}... recomputed={recomputed[:16]}..."
                ),
            )
        )
    else:
        checks.append(
            VerifyCheck(
                name="merkle_root_matches_declared",
                passed=True,
                detail="no declared root supplied; recomputed root reported only",
            )
        )

    # ---- Manifest sanity (optional) ----
    if manifest:
        version = manifest.get("version")
        export_type = manifest.get("export_type")
        checks.append(
            VerifyCheck(
                name="manifest_well_formed",
                passed=bool(version),
                detail=f"version={version!r} export_type={export_type!r}",
            )
        )

    verified = all(c.passed for c in checks)
    return VerifyResponse(
        verified=verified,
        checks=checks,
        merkle_root_recomputed=recomputed,
        timestamp=_now_iso(),
    )


def _verify_manifest_file_bundle(
    *,
    zf: zipfile.ZipFile,
    names: list[str],
    manifest: dict[str, Any],
    extra_checks: list[VerifyCheck],
) -> Optional[VerifyResponse]:
    """Verify the public /proof ZIP shape: manifest.files + manifest.merkle.

    The open-source verifier published at ``frontend/public/sdk/verify_chain.py``
    treats file SHA-256 values as Merkle leaves. Keep the API endpoint aligned
    with that public contract so the sample bundle can be checked both in the
    browser and offline.
    """
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        return None

    checks = list(extra_checks)
    checks.append(
        VerifyCheck(
            name="manifest_files_present",
            passed=True,
            detail=f"{len(files)} file manifest entr{'y' if len(files) == 1 else 'ies'} found",
        )
    )

    bad_entries: list[str] = []
    missing: list[str] = []
    mismatched: list[str] = []
    size_mismatched: list[str] = []
    recomputed: list[str] = []

    for idx, entry in enumerate(files):
        if not isinstance(entry, dict):
            bad_entries.append(f"files[{idx}]")
            continue

        path = entry.get("path")
        declared = entry.get("sha256")
        declared_size = entry.get("size")

        if (
            not isinstance(path, str)
            or not _safe_zip_member(path)
            or not isinstance(declared, str)
            or len(declared) != 64
        ):
            bad_entries.append(str(path or f"files[{idx}]"))
            continue

        if path not in names:
            missing.append(path)
            continue

        data = zf.read(path)
        if declared_size is not None and declared_size != len(data):
            size_mismatched.append(path)

        actual = hashlib.sha256(data).hexdigest()
        recomputed.append(actual)
        if actual != declared:
            mismatched.append(path)

    checks.append(
        VerifyCheck(
            name="manifest_file_entries_well_formed",
            passed=not bad_entries and not missing,
            detail=(
                "all manifest file entries are safe and present"
                if not bad_entries and not missing
                else f"bad={bad_entries} missing={missing}"
            ),
        )
    )
    checks.append(
        VerifyCheck(
            name="file_hashes_match_manifest",
            passed=not mismatched and not size_mismatched,
            detail=(
                "all manifest-declared file hashes and sizes match"
                if not mismatched and not size_mismatched
                else f"hash_mismatched={mismatched} size_mismatched={size_mismatched}"
            ),
        )
    )

    merkle = manifest.get("merkle")
    declared_root: Optional[str] = None
    declared_leaves: Any = None
    if isinstance(merkle, dict):
        root = merkle.get("root")
        if isinstance(root, str):
            declared_root = root
        declared_leaves = merkle.get("leaves")

    if isinstance(declared_leaves, list):
        leaves_match = declared_leaves == recomputed
        checks.append(
            VerifyCheck(
                name="manifest_merkle_leaves_match_files",
                passed=leaves_match,
                detail=(
                    "manifest leaves match recomputed file hashes"
                    if leaves_match
                    else "manifest leaves differ from recomputed file hashes"
                ),
            )
        )

    recomputed_root = MerkleTree(recomputed).root if recomputed else ""
    if declared_root:
        root_matches = recomputed_root == declared_root
        checks.append(
            VerifyCheck(
                name="merkle_root_matches_declared",
                passed=root_matches,
                detail=(
                    "recomputed root matches manifest.merkle.root"
                    if root_matches
                    else f"declared={declared_root[:16]}... recomputed={recomputed_root[:16]}..."
                ),
            )
        )
    else:
        checks.append(
            VerifyCheck(
                name="merkle_root_matches_declared",
                passed=False,
                detail="manifest.merkle.root missing",
            )
        )

    version = manifest.get("version")
    checks.append(
        VerifyCheck(
            name="manifest_well_formed",
            passed=bool(version),
            detail=f"version={version!r} file_count={len(files)}",
        )
    )

    return VerifyResponse(
        verified=all(c.passed for c in checks),
        checks=checks,
        merkle_root_recomputed=recomputed_root,
        timestamp=_now_iso(),
    )


def _verify_zip_bundle(raw: bytes) -> VerifyResponse:
    """Open a ZIP bundle in memory and run structural checks."""
    extra: list[VerifyCheck] = []

    if len(raw) > MAX_BUNDLE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"bundle exceeds {MAX_BUNDLE_BYTES} bytes",
        )

    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=400, detail=f"malformed ZIP: {exc}")

    names = zf.namelist()
    if len(names) > MAX_ZIP_ENTRIES:
        raise HTTPException(
            status_code=400,
            detail=f"bundle has too many entries ({len(names)} > {MAX_ZIP_ENTRIES})",
        )

    # Path-traversal / structural validation BEFORE any read.
    for name in names:
        if not _safe_zip_member(name):
            raise HTTPException(
                status_code=400,
                detail=f"unsafe ZIP entry rejected: {name!r}",
            )

    # Total uncompressed size guard (zip-bomb defense).
    total_uncompressed = sum(info.file_size for info in zf.infolist())
    if total_uncompressed > MAX_DECOMPRESSED_BYTES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"decompressed size {total_uncompressed} exceeds "
                f"{MAX_DECOMPRESSED_BYTES}"
            ),
        )
    extra.append(
        VerifyCheck(
            name="zip_structure",
            passed=True,
            detail=(
                f"{len(names)} entries, {total_uncompressed} uncompressed "
                "bytes; no path-traversal"
            ),
        )
    )

    # Manifest is required for ZIP bundles.
    if "manifest.json" not in names:
        raise HTTPException(status_code=400, detail="bundle missing manifest.json")

    try:
        manifest_bytes = zf.read("manifest.json")
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(
            status_code=400, detail=f"manifest.json unreadable: {exc}"
        )

    manifest_file_result = _verify_manifest_file_bundle(
        zf=zf,
        names=names,
        manifest=manifest,
        extra_checks=extra,
    )
    if manifest_file_result is not None:
        return manifest_file_result

    # File-hash cross-check: every name in manifest.file_hashes that is
    # present in the ZIP must hash to the declared digest.
    file_hashes = manifest.get("file_hashes") or {}
    if isinstance(file_hashes, dict) and file_hashes:
        mismatched: list[str] = []
        for fname, declared in file_hashes.items():
            if fname not in names:
                continue
            actual = hashlib.sha256(zf.read(fname)).hexdigest()
            if actual != declared:
                mismatched.append(fname)
        extra.append(
            VerifyCheck(
                name="file_hashes_match_manifest",
                passed=not mismatched,
                detail=(
                    "all declared file hashes match"
                    if not mismatched
                    else f"mismatched: {sorted(mismatched)}"
                ),
            )
        )

    # Pull events + declared root from chain_verification_*.json if present.
    events: list[dict[str, Any]] = []
    declared_root: Optional[str] = None

    chain_files = [n for n in names if n.startswith("chain_verification") and n.endswith(".json")]
    if chain_files:
        try:
            chain_payload = json.loads(zf.read(chain_files[0]).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise HTTPException(
                status_code=400,
                detail=f"chain_verification JSON unreadable: {exc}",
            )
        events = chain_payload.get("events") or []
        declared_root = (
            chain_payload.get("merkle_root")
            or (chain_payload.get("chain_verification") or {}).get("merkle_root")
        )

    # Manifest may also carry an embedded event list / root for simpler bundles.
    if not events:
        events = manifest.get("events") or []
    if not declared_root:
        declared_root = manifest.get("merkle_root") or (
            manifest.get("summary") or {}
        ).get("merkle_root")

    return _verify_payload(
        manifest=manifest,
        events=events,
        declared_root=declared_root,
        extra_checks=extra,
    )


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------
@router.post(
    "/verify",
    response_model=VerifyResponse,
    summary="Public hash-chain / Merkle verification of a RegEngine export bundle",
)
@limiter.limit("10/minute")
async def verify_export(
    request: Request,
    bundle: Optional[UploadFile] = File(default=None),
) -> VerifyResponse:
    """Verify a RegEngine FSMA-204 export bundle without authentication.

    Accepts either a ``multipart/form-data`` upload (``bundle`` ZIP) or
    an ``application/json`` body shaped as :class:`JsonBundle`. Performs
    structural checks plus Merkle-root recomputation against the
    bundle's declared root. Reads no tenant data — operates purely on
    the uploaded bytes.
    """
    ip_hash = _hash_ip(request.client.host if request.client else None)
    content_type = (request.headers.get("content-type") or "").split(";", 1)[0].strip().lower()

    # ---- JSON path ----
    if bundle is None:
        if not content_type.startswith("application/json"):
            raise HTTPException(
                status_code=400,
                detail=(
                    "request must be multipart/form-data with a 'bundle' file "
                    "OR application/json with {manifest, events, merkle_root}"
                ),
            )
        try:
            raw_json = await request.body()
            if len(raw_json) > MAX_BUNDLE_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=f"JSON body exceeds {MAX_BUNDLE_BYTES} bytes",
                )
            payload = JsonBundle.model_validate_json(raw_json)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"malformed JSON: {exc}")

        result = _verify_payload(
            manifest=payload.manifest,
            events=payload.events,
            declared_root=payload.merkle_root,
        )
        logger.info(
            "proof_verify_call",
            extra={
                "mode": "json",
                "ip_hash": ip_hash,
                "verified": result.verified,
                "event_count": len(payload.events),
            },
        )
        return result

    # ---- Multipart / ZIP path ----
    declared_ct = (bundle.content_type or "").lower()
    if declared_ct and declared_ct not in ALLOWED_BUNDLE_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported bundle content-type: {declared_ct!r}",
        )

    raw = await bundle.read(MAX_BUNDLE_BYTES + 1)
    if len(raw) > MAX_BUNDLE_BYTES:
        raise HTTPException(
            status_code=413, detail=f"bundle exceeds {MAX_BUNDLE_BYTES} bytes"
        )
    if not raw:
        raise HTTPException(status_code=400, detail="empty bundle")

    # Allow the multipart caller to send either a ZIP or a JSON blob.
    if raw[:4] == b"PK\x03\x04":
        result = _verify_zip_bundle(raw)
        mode = "zip"
    else:
        try:
            payload = JsonBundle.model_validate_json(raw)
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"bundle is neither a ZIP nor valid JSON: {exc}",
            )
        result = _verify_payload(
            manifest=payload.manifest,
            events=payload.events,
            declared_root=payload.merkle_root,
        )
        mode = "json-in-multipart"

    logger.info(
        "proof_verify_call",
        extra={
            "mode": mode,
            "ip_hash": ip_hash,
            "verified": result.verified,
            "byte_size": len(raw),
        },
    )
    return result
