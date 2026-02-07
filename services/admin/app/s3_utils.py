"""S3 helper utilities for PCOS document storage."""

from __future__ import annotations

import hashlib
from typing import BinaryIO

import boto3
import structlog
from botocore.client import BaseClient
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import HTTPException

from .config import get_settings

logger = structlog.get_logger("s3_utils")


def _client() -> BaseClient:
    """Get configured S3 client."""
    settings = get_settings()
    session = boto3.session.Session()
    return session.client(
        "s3",
        region_name=settings.aws_region,
        endpoint_url=settings.aws_endpoint_url,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )


def _ensure_bucket(bucket: str) -> None:
    """Create bucket if it doesn't exist (for dev/demo)."""
    client = _client()
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError as e:
        if e.response["Error"]["Code"] == "404":
            try:
                client.create_bucket(Bucket=bucket)
                logger.info("s3_bucket_created", bucket=bucket)
            except Exception as create_exc:
                logger.error("s3_create_bucket_failed", bucket=bucket, error=str(create_exc))
                raise


def upload_file(
    bucket: str,
    key: str,
    file_data: BinaryIO,
    content_type: str = "application/octet-stream",
) -> tuple[str, str, int]:
    """Upload file to S3.

    Returns:
        Tuple of (s3_uri, sha256_hash, file_size_bytes)
    """
    try:
        _ensure_bucket(bucket)

        # Read file content and calculate hash
        content = file_data.read()
        file_size = len(content)
        sha256_hash = hashlib.sha256(content).hexdigest()

        # Upload to S3
        _client().put_object(
            Bucket=bucket,
            Key=key,
            Body=content,
            ContentType=content_type,
        )

        s3_uri = f"s3://{bucket}/{key}"
        logger.info(
            "s3_file_uploaded",
            bucket=bucket,
            key=key,
            size_bytes=file_size,
            content_type=content_type,
        )
        return s3_uri, sha256_hash, file_size

    except (ClientError, BotoCoreError) as exc:
        logger.error("s3_upload_failed", bucket=bucket, key=key, error=str(exc))
        raise HTTPException(
            status_code=500, detail="Failed to upload file to storage"
        ) from exc


def generate_presigned_url(bucket: str, key: str, expires_in: int = 3600) -> str:
    """Generate a presigned URL for downloading a file.

    Args:
        bucket: S3 bucket name
        key: Object key
        expires_in: URL expiration in seconds (default 1 hour)

    Returns:
        Presigned URL string
    """
    try:
        url = _client().generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expires_in,
        )
        return url
    except (ClientError, BotoCoreError) as exc:
        logger.error("s3_presign_failed", bucket=bucket, key=key, error=str(exc))
        raise HTTPException(
            status_code=500, detail="Failed to generate download URL"
        ) from exc


def delete_file(bucket: str, key: str) -> bool:
    """Delete a file from S3.

    Returns:
        True if deleted successfully
    """
    try:
        _client().delete_object(Bucket=bucket, Key=key)
        logger.info("s3_file_deleted", bucket=bucket, key=key)
        return True
    except (ClientError, BotoCoreError) as exc:
        logger.error("s3_delete_failed", bucket=bucket, key=key, error=str(exc))
        return False
