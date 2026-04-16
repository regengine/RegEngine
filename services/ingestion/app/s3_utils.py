"""S3 helper utilities.

Provides low-level S3 operations for the ingestion service, including
raw document persistence to the 'regengine-ingest-raw' bucket.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

import boto3
import structlog
from botocore.client import BaseClient
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import HTTPException

from .config import get_settings

logger = structlog.get_logger("s3_utils")

RAW_INGEST_BUCKET = "regengine-ingest-raw"

# All uploads use AES-256 server-side encryption at rest.
_SSE = {"ServerSideEncryption": "AES256"}


def _client() -> BaseClient:
    settings = get_settings()
    if not settings.object_storage_access_key_id or not settings.object_storage_secret_access_key:
        raise NotImplementedError(
            "S3 storage is not configured — set OBJECT_STORAGE_ACCESS_KEY_ID and "
            "OBJECT_STORAGE_SECRET_ACCESS_KEY environment variables before using S3 operations."
        )
    session = boto3.session.Session()
    return session.client(
        "s3",
        region_name=settings.object_storage_region,
        endpoint_url=settings.object_storage_endpoint_url,
        aws_access_key_id=settings.object_storage_access_key_id,
        aws_secret_access_key=settings.object_storage_secret_access_key,
    )


def _ensure_bucket_security(client: BaseClient, bucket: str) -> None:
    """Apply public access block and enforce encryption on a bucket.

    Called after bucket creation to ensure no objects can be made public
    and all uploads require server-side encryption.
    """
    try:
        client.put_public_access_block(
            Bucket=bucket,
            PublicAccessBlockConfiguration={
                "BlockPublicAcls": True,
                "IgnorePublicAcls": True,
                "BlockPublicPolicy": True,
                "RestrictPublicBuckets": True,
            },
        )
        logger.info("s3_public_access_blocked", bucket=bucket)
    except (ClientError, BotoCoreError) as exc:
        # Non-fatal — some S3-compatible stores (MinIO) may not support this
        logger.warning("s3_public_access_block_failed", bucket=bucket, error=str(exc))

    try:
        client.put_bucket_encryption(
            Bucket=bucket,
            ServerSideEncryptionConfiguration={
                "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}],
            },
        )
        logger.info("s3_default_encryption_set", bucket=bucket)
    except (ClientError, BotoCoreError) as exc:
        logger.warning("s3_default_encryption_failed", bucket=bucket, error=str(exc))


def put_json(bucket: str, key: str, payload: Any) -> str:
    """Serialize payload to JSON and upload to S3.

    Returns the S3 URI for the stored object.
    """

    try:
        body = json.dumps(payload, default=_json_serializer).encode("utf-8")
        _client().put_object(Bucket=bucket, Key=key, Body=body, ContentType="application/json", **_SSE)
        return f"s3://{bucket}/{key}"
    except (ClientError, BotoCoreError) as exc:
        if isinstance(exc, ClientError) and exc.response["Error"]["Code"] == "NoSuchBucket":
            # Auto-create bucket for dev/demo robustness
            try:
                client = _client()
                client.create_bucket(Bucket=bucket)
                _ensure_bucket_security(client, bucket)
                client.put_object(Bucket=bucket, Key=key, Body=body, ContentType="application/json", **_SSE)
                return f"s3://{bucket}/{key}"
            except Exception as create_exc:
                logger.error("s3_create_bucket_failed", bucket=bucket, error=str(create_exc))
                # Fall through to original error raise

        logger.error("s3_put_failed", bucket=bucket, key=key, error=str(exc))
        raise HTTPException(
            status_code=500, detail="Failed to store data in S3"
        ) from exc


def put_bytes(
    bucket: str, key: str, content: bytes, content_type: str = "application/octet-stream"
) -> str:
    """Upload raw bytes to S3 and return the object URI."""

    try:
        _client().put_object(Bucket=bucket, Key=key, Body=content, ContentType=content_type, **_SSE)
        return f"s3://{bucket}/{key}"
    except (ClientError, BotoCoreError) as exc:
        if isinstance(exc, ClientError) and exc.response["Error"]["Code"] == "NoSuchBucket":
             # Auto-create bucket for dev/demo robustness
            try:
                _client().create_bucket(Bucket=bucket)
                _client().put_object(Bucket=bucket, Key=key, Body=content, ContentType=content_type, **_SSE)
                return f"s3://{bucket}/{key}"
            except Exception as create_exc:
                logger.error("s3_create_bucket_failed", bucket=bucket, error=str(create_exc))
                # Fall through

        logger.error("s3_put_failed", bucket=bucket, key=key, error=str(exc))
        raise HTTPException(
            status_code=500, detail="Failed to store data in S3"
        ) from exc


def _json_serializer(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value)} is not JSON serializable")


def _ensure_bucket(client: BaseClient, bucket: str) -> None:
    """Create bucket if it does not exist (dev/demo convenience)."""
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError as exc:
        error_code = exc.response["Error"]["Code"]
        if error_code in ("404", "NoSuchBucket"):
            try:
                client.create_bucket(Bucket=bucket)
                logger.info("s3_bucket_created", bucket=bucket)
            except (ClientError, BotoCoreError) as create_exc:
                logger.error("s3_create_bucket_failed", bucket=bucket, error=str(create_exc))
                raise
        else:
            raise


# ---------------------------------------------------------------------------
# Raw document persistence for the 'regengine-ingest-raw' bucket
# ---------------------------------------------------------------------------


def upload_raw_document(
    content: bytes,
    tenant_id: str,
    document_type: str = "unknown",
    filename: Optional[str] = None,
    content_type: str = "application/octet-stream",
    metadata: Optional[dict[str, str]] = None,
) -> dict[str, str]:
    """Store a raw incoming document to the regengine-ingest-raw bucket.

    Key layout: ``<tenant_id>/<YYYY>/<MM>/<DD>/<document_type>/<uuid>[-filename]``

    Returns a dict with ``s3_uri``, ``bucket``, ``key``, and ``document_id``.
    """
    now = datetime.now(timezone.utc)
    document_id = str(uuid4())
    date_prefix = now.strftime("%Y/%m/%d")
    safe_type = document_type.lower().replace(" ", "_")

    suffix = ""
    if filename:
        # Sanitize filename for use in S3 key
        safe_name = filename.replace("/", "_").replace("\\", "_").strip()
        if safe_name:
            suffix = f"-{safe_name}"

    key = f"{tenant_id}/{date_prefix}/{safe_type}/{document_id}{suffix}"

    s3 = _client()
    s3_metadata: dict[str, str] = {
        "tenant_id": tenant_id,
        "document_type": document_type,
        "document_id": document_id,
        "ingested_at": now.isoformat(),
    }
    if metadata:
        s3_metadata.update(metadata)

    try:
        _ensure_bucket(s3, RAW_INGEST_BUCKET)
        s3.put_object(
            Bucket=RAW_INGEST_BUCKET,
            Key=key,
            Body=content,
            ContentType=content_type,
            Metadata=s3_metadata,
            **_SSE,
        )
        logger.info(
            "raw_document_uploaded",
            bucket=RAW_INGEST_BUCKET,
            key=key,
            size=len(content),
            tenant_id=tenant_id,
        )
        return {
            "s3_uri": f"s3://{RAW_INGEST_BUCKET}/{key}",
            "bucket": RAW_INGEST_BUCKET,
            "key": key,
            "document_id": document_id,
        }
    except (ClientError, BotoCoreError) as exc:
        logger.error(
            "raw_document_upload_failed",
            bucket=RAW_INGEST_BUCKET,
            key=key,
            error=str(exc),
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to store raw document in S3",
        ) from exc


def get_raw_document(
    key: str,
    bucket: str = RAW_INGEST_BUCKET,
) -> dict[str, Any]:
    """Retrieve a raw document from S3 by its key.

    Returns a dict with ``content`` (bytes), ``content_type``, ``metadata``,
    and ``content_length``.
    """
    s3 = _client()
    try:
        response = s3.get_object(Bucket=bucket, Key=key)
        return {
            "content": response["Body"].read(),
            "content_type": response.get("ContentType", "application/octet-stream"),
            "metadata": response.get("Metadata", {}),
            "content_length": response.get("ContentLength", 0),
        }
    except ClientError as exc:
        error_code = exc.response["Error"]["Code"]
        if error_code == "NoSuchKey":
            logger.warning("raw_document_not_found", bucket=bucket, key=key)
            raise HTTPException(
                status_code=404,
                detail=f"Document not found: {key}",
            ) from exc
        logger.error("raw_document_get_failed", bucket=bucket, key=key, error=str(exc))
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve raw document from S3",
        ) from exc
    except BotoCoreError as exc:
        logger.error("raw_document_get_failed", bucket=bucket, key=key, error=str(exc))
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve raw document from S3",
        ) from exc


def list_raw_documents(
    tenant_id: str,
    prefix: Optional[str] = None,
    max_keys: int = 1000,
    bucket: str = RAW_INGEST_BUCKET,
) -> list[dict[str, Any]]:
    """List raw documents in S3 for a given tenant.

    Optionally narrow with an additional prefix (e.g. date or document type).
    Returns a list of dicts with ``key``, ``size``, ``last_modified``, and
    ``s3_uri`` for each object.
    """
    s3 = _client()
    search_prefix = f"{tenant_id}/"
    if prefix:
        search_prefix = f"{tenant_id}/{prefix}"

    documents: list[dict[str, Any]] = []
    try:
        paginator = s3.get_paginator("list_objects_v2")
        page_iterator = paginator.paginate(
            Bucket=bucket,
            Prefix=search_prefix,
            PaginationConfig={"MaxItems": max_keys},
        )
        for page in page_iterator:
            for obj in page.get("Contents", []):
                documents.append({
                    "key": obj["Key"],
                    "size": obj["Size"],
                    "last_modified": obj["LastModified"].isoformat()
                    if isinstance(obj["LastModified"], datetime)
                    else str(obj["LastModified"]),
                    "s3_uri": f"s3://{bucket}/{obj['Key']}",
                })
        return documents
    except ClientError as exc:
        error_code = exc.response["Error"]["Code"]
        if error_code in ("NoSuchBucket", "404"):
            logger.info("raw_documents_bucket_not_found", bucket=bucket)
            return []
        logger.error("raw_documents_list_failed", bucket=bucket, error=str(exc))
        raise HTTPException(
            status_code=500,
            detail="Failed to list raw documents from S3",
        ) from exc
    except BotoCoreError as exc:
        logger.error("raw_documents_list_failed", bucket=bucket, error=str(exc))
        raise HTTPException(
            status_code=500,
            detail="Failed to list raw documents from S3",
        ) from exc
