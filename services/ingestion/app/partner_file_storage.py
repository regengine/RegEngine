"""First-file partner upload persistence (SEL-549 / partner-uploads).

Uploads land in the private ``partner-uploads`` bucket under a tenant-scoped
path. Metadata is recorded in ``public.partner_files``; ``fsma.manifest_blobs``
keeps the SHA-256 + ``storage_url`` pointer and leaves ``raw_bytes`` NULL when
object storage is configured.

Synthetic / test fixtures only until SEL-590 clears. Do not invent partner
payloads; callers pass bytes they already hold.
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Any, Dict, Optional
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import text

logger = logging.getLogger("partner_file_storage")

PARTNER_UPLOADS_BUCKET = "partner-uploads"
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def tenant_object_key(
    *,
    tenant_id: str,
    engagement_id: str,
    filename: str,
    object_id: Optional[str] = None,
) -> str:
    """Build ``tenants/{tenant}/engagements/{engagement}/{uuid}-{filename}``."""
    from .s3_utils import safe_s3_key_component, _validate_s3_key

    oid = object_id or str(uuid4())
    safe_name = safe_s3_key_component(filename, fallback="upload.csv")
    key = (
        f"tenants/{safe_s3_key_component(tenant_id, fallback='tenant')}"
        f"/engagements/{safe_s3_key_component(engagement_id, fallback='engagement')}"
        f"/{safe_s3_key_component(oid, fallback='object')}-{safe_name}"
    )
    _validate_s3_key(key)
    return key


def persist_partner_upload(
    db,
    *,
    tenant_id: str,
    engagement_id: str,
    content: bytes,
    filename: str,
    content_type: Optional[str],
    uploaded_by: Optional[str],
    ingestion_run_id: str,
) -> Dict[str, Any]:
    """Store bytes in partner-uploads (when configured) and write metadata + blob pointer.

    Returns a dict with ``partner_file_id``, ``storage_url``, ``storage_path``,
    ``sha256``, and ``used_object_storage``.
    """
    from .remediation.audit_utils import audit_event
    from .s3_utils import is_object_storage_configured, put_bytes

    if not content:
        raise HTTPException(status_code=400, detail="Empty upload")

    sha256 = hashlib.sha256(content).hexdigest()
    ctype = content_type or "text/csv"
    partner_file_id = str(uuid4())
    storage_path = tenant_object_key(
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        filename=filename,
        object_id=partner_file_id,
    )
    used_object_storage = False
    storage_url: Optional[str] = None
    raw_bytes_param: Optional[bytes] = content

    if is_object_storage_configured():
        storage_url = put_bytes(
            PARTNER_UPLOADS_BUCKET,
            storage_path,
            content,
            ctype,
        )
        used_object_storage = True
        raw_bytes_param = None  # pointer-only row; bytes live in the bucket
        db.execute(
            # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
            text(
                """
                INSERT INTO public.partner_files (
                    id, tenant_id, engagement_id, storage_bucket, storage_path,
                    content_sha256, byte_size, content_type, original_filename,
                    status
                ) VALUES (
                    CAST(:id AS uuid),
                    CAST(:tenant_id AS uuid),
                    CAST(:engagement_id AS uuid),
                    :bucket,
                    :storage_path,
                    :sha256,
                    :byte_size,
                    :content_type,
                    :filename,
                    'uploaded'
                )
                """
            ),
            {
                "id": partner_file_id,
                "tenant_id": tenant_id,
                "engagement_id": engagement_id,
                "bucket": PARTNER_UPLOADS_BUCKET,
                "storage_path": storage_path,
                "sha256": sha256,
                "byte_size": len(content),
                "content_type": ctype,
                "filename": filename,
            },
        )

    db.execute(
        # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
        text(
            """
            INSERT INTO fsma.manifest_blobs
                (ingestion_run_id, tenant_id, raw_bytes, sha256,
                 original_filename, content_type, uploaded_by, storage_url)
            VALUES
                (CAST(:run_id AS uuid), CAST(:tenant_id AS uuid), :raw_bytes,
                 :sha256, :filename, :content_type, :uploaded_by, :storage_url)
            """
        ),
        {
            "run_id": ingestion_run_id,
            "tenant_id": tenant_id,
            "raw_bytes": raw_bytes_param,
            "sha256": sha256,
            "filename": filename,
            "content_type": ctype,
            "uploaded_by": uploaded_by,
            "storage_url": storage_url,
        },
    )

    audit_event(
        db,
        tenant_id=tenant_id,
        event_type="partner_file.upload",
        action="partner_file.upload",
        severity="info",
        actor_id=uploaded_by,
        resource_type="partner_file" if used_object_storage else "manifest_blob",
        resource_id=partner_file_id if used_object_storage else ingestion_run_id,
        metadata={
            "ingestion_run_id": ingestion_run_id,
            "engagement_id": engagement_id,
            "storage_bucket": PARTNER_UPLOADS_BUCKET if used_object_storage else None,
            "storage_path": storage_path if used_object_storage else None,
            "storage_url": storage_url,
            "content_sha256": sha256,
            "byte_size": len(content),
            "original_filename": filename,
            "used_object_storage": used_object_storage,
        },
    )

    return {
        "partner_file_id": partner_file_id if used_object_storage else None,
        "storage_url": storage_url,
        "storage_path": storage_path if used_object_storage else None,
        "sha256": sha256,
        "used_object_storage": used_object_storage,
    }


def load_bytes_from_storage_url(storage_url: str) -> bytes:
    """Fetch object bytes for an ``s3://bucket/key`` storage_url."""
    from .s3_utils import get_raw_document

    if not storage_url.startswith("s3://"):
        raise HTTPException(status_code=500, detail="Unsupported storage_url scheme")
    without = storage_url[len("s3://") :]
    bucket, _, key = without.partition("/")
    if not bucket or not key:
        raise HTTPException(status_code=500, detail="Malformed storage_url")
    doc = get_raw_document(key=key, bucket=bucket)
    return doc["content"]


def resolve_manifest_raw_bytes(
    *,
    raw_bytes: Any,
    storage_url: Optional[str],
) -> bytes:
    """Return manifest bytes from bytea or, when null, from storage_url."""
    if raw_bytes is not None:
        return bytes(raw_bytes)
    if storage_url:
        return load_bytes_from_storage_url(storage_url)
    raise HTTPException(status_code=404, detail="Manifest payload not found")
