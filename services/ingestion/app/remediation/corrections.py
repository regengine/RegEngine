"""Append-only correction patches with a per-case hash chain.

current record = original event dict + ordered patches. Field paths must be
byte-equal to the case's allowed_fields whitelist; segment syntax is
restricted to [a-z0-9_]+ with at most one 'kdes.' prefix — no arrays, no
dunder segments, dict-only assignment.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from fastapi import HTTPException
from sqlalchemy import text

from .validation import canonical_json

_FIELD_PATH_RE = re.compile(r"^(kdes\.)?[a-z0-9_]+$")

GENESIS = "GENESIS"


def validate_field_path(path: str, allowed: Sequence[str]) -> None:
    if path not in set(allowed):
        raise HTTPException(status_code=422, detail=f"Field '{path}' is not authorized for this case")
    if not _FIELD_PATH_RE.match(path) or "__" in path:
        raise HTTPException(status_code=422, detail=f"Field path '{path}' is not a valid field path")


def get_value(event: Dict[str, Any], path: str) -> Any:
    if path.startswith("kdes."):
        return (event.get("kdes") or {}).get(path[5:])
    return event.get(path)


def set_value(event: Dict[str, Any], path: str, value: Any) -> Dict[str, Any]:
    out = copy.deepcopy(event)
    if path.startswith("kdes."):
        out.setdefault("kdes", {})[path[5:]] = value
    else:
        out[path] = value
    return out


def apply_patches(original: Dict[str, Any], patches: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Derive the current record from the original plus ordered patches."""
    current = copy.deepcopy(original)
    for patch in sorted(patches, key=lambda p: p["patch_seq"]):
        current = set_value(current, patch["field_path"], patch["proposed_value"])
    return current


def compute_patch_hash(prev_hash: Optional[str], body: Dict[str, Any]) -> str:
    payload = {"prev_patch_hash": prev_hash or GENESIS, **body}
    return hashlib.sha256(canonical_json(payload).encode()).hexdigest()


def verify_patch_chain(patches: Sequence[Dict[str, Any]]) -> bool:
    prev: Optional[str] = None
    for patch in sorted(patches, key=lambda p: p["patch_seq"]):
        expected = compute_patch_hash(prev, _hash_body(patch))
        if expected != patch["patch_hash"]:
            return False
        prev = patch["patch_hash"]
    return True


def _norm_ts(value: Any) -> Any:
    """Normalize timestamps to UTC isoformat so TIMESTAMPTZ round-trips
    (returned in session timezone) hash identically to insert time."""
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value).astimezone(timezone.utc).isoformat()
        except ValueError:
            return value
    return value


def _hash_body(patch: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "tenant_id": str(patch["tenant_id"]),
        "case_id": str(patch["case_id"]),
        "manifest_record_id": str(patch["manifest_record_id"]),
        "patch_seq": patch["patch_seq"],
        "validation_issue_id": patch.get("validation_issue_id"),
        "field_path": patch["field_path"],
        "previous_value": patch.get("previous_value"),
        "proposed_value": patch["proposed_value"],
        "correcting_org": patch["correcting_org"],
        "actor_name": patch["actor_name"],
        "actor_role": patch["actor_role"],
        "auth_method": patch["auth_method"],
        "correction_reason": patch["correction_reason"],
        "attestation_text": patch["attestation_text"],
        "attested_at": _norm_ts(patch["attested_at"]),
    }


def load_patches(db, *, tenant_id: str, manifest_record_id: str) -> List[Dict[str, Any]]:
    rows = db.execute(
        # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
        text(
            """
            SELECT id, tenant_id, case_id, manifest_record_id, patch_seq,
                   validation_issue_id, field_path, previous_value, proposed_value,
                   correcting_org, actor_name, actor_role, auth_method,
                   correction_reason, attestation_text, attested_at,
                   prev_patch_hash, patch_hash, created_at
            FROM fsma.correction_patches
            WHERE tenant_id = CAST(:tenant_id AS uuid)
              AND manifest_record_id = CAST(:record_id AS uuid)
            ORDER BY patch_seq ASC
            """
        ),
        {"tenant_id": tenant_id, "record_id": manifest_record_id},
    ).fetchall()
    return [
        {
            "id": str(r[0]),
            "tenant_id": str(r[1]),
            "case_id": str(r[2]),
            "manifest_record_id": str(r[3]),
            "patch_seq": r[4],
            "validation_issue_id": r[5],
            "field_path": r[6],
            "previous_value": r[7],
            "proposed_value": r[8],
            "correcting_org": r[9],
            "actor_name": r[10],
            "actor_role": r[11],
            "auth_method": r[12],
            "correction_reason": r[13],
            "attestation_text": r[14],
            "attested_at": r[15].isoformat() if r[15] else None,
            "prev_patch_hash": r[16],
            "patch_hash": r[17],
            "created_at": r[18].isoformat() if r[18] else None,
        }
        for r in rows
    ]


def insert_patches(
    db,
    *,
    tenant_id: str,
    case_id: str,
    manifest_record_id: str,
    changes: Dict[str, str],
    previous_values: Dict[str, Any],
    issue_by_field: Dict[str, str],
    correcting_org: str,
    actor_name: str,
    actor_role: str,
    correction_reason: str,
    attestation_text: str,
    evidence_ref: Optional[str],
    auth_method: str = "remediation_token",
) -> List[str]:
    """Append one patch row per corrected field, hash-chained per case."""
    tail = db.execute(
        # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
        text(
            """
            SELECT patch_seq, patch_hash FROM fsma.correction_patches
            WHERE tenant_id = CAST(:tenant_id AS uuid)
              AND case_id = CAST(:case_id AS uuid)
            ORDER BY patch_seq DESC LIMIT 1
            """
        ),
        {"tenant_id": tenant_id, "case_id": case_id},
    ).fetchone()
    next_seq = (tail[0] + 1) if tail else 1
    prev_hash = tail[1] if tail else None

    attested_at = datetime.now(timezone.utc)
    patch_ids: List[str] = []
    for field_path in sorted(changes.keys()):
        body = {
            "tenant_id": tenant_id,
            "case_id": case_id,
            "manifest_record_id": manifest_record_id,
            "patch_seq": next_seq,
            "validation_issue_id": issue_by_field.get(field_path),
            "field_path": field_path,
            "previous_value": previous_values.get(field_path),
            "proposed_value": changes[field_path],
            "correcting_org": correcting_org,
            "actor_name": actor_name,
            "actor_role": actor_role,
            "auth_method": auth_method,
            "correction_reason": correction_reason,
            "attestation_text": attestation_text,
            "attested_at": attested_at.isoformat(),
        }
        patch_hash = compute_patch_hash(prev_hash, body)
        row = db.execute(
            # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
            text(
                """
                INSERT INTO fsma.correction_patches
                    (tenant_id, case_id, manifest_record_id, patch_seq,
                     validation_issue_id, field_path, previous_value, proposed_value,
                     correcting_org, actor_name, actor_role, auth_method,
                     correction_reason, attestation_text, attested_at, evidence_ref,
                     prev_patch_hash, patch_hash)
                VALUES
                    (CAST(:tenant_id AS uuid), CAST(:case_id AS uuid),
                     CAST(:record_id AS uuid), :patch_seq, :issue_id, :field_path,
                     CAST(:previous_value AS jsonb), CAST(:proposed_value AS jsonb),
                     :correcting_org, :actor_name, :actor_role, :auth_method,
                     :reason, :attestation_text, :attested_at, :evidence_ref,
                     :prev_patch_hash, :patch_hash)
                RETURNING id
                """
            ),
            {
                "tenant_id": tenant_id,
                "case_id": case_id,
                "record_id": manifest_record_id,
                "patch_seq": next_seq,
                "issue_id": issue_by_field.get(field_path),
                "field_path": field_path,
                "previous_value": json.dumps(previous_values.get(field_path)),
                "proposed_value": json.dumps(changes[field_path]),
                "correcting_org": correcting_org,
                "actor_name": actor_name,
                "actor_role": actor_role,
                "auth_method": auth_method,
                "reason": correction_reason,
                "attestation_text": attestation_text,
                "attested_at": attested_at,
                "evidence_ref": evidence_ref,
                "prev_patch_hash": prev_hash,
                "patch_hash": patch_hash,
            },
        ).fetchone()
        patch_ids.append(str(row[0]))
        prev_hash = patch_hash
        next_seq += 1
    return patch_ids
