"""S3 helper utilities."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import boto3
import structlog
from botocore.client import BaseClient
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import HTTPException

from .config import get_settings

logger = structlog.get_logger("s3_utils")


def _client() -> BaseClient:
    settings = get_settings()
    session = boto3.session.Session()
    return session.client(
        "s3",
        region_name=settings.object_storage_region,
        endpoint_url=settings.object_storage_endpoint_url,
        aws_access_key_id=settings.object_storage_access_key_id,
        aws_secret_access_key=settings.object_storage_secret_access_key,
    )


def put_json(bucket: str, key: str, payload: Any) -> str:
    """Serialize payload to JSON and upload to S3.

    Returns the S3 URI for the stored object.
    """

    try:
        body = json.dumps(payload, default=_json_serializer).encode("utf-8")
        _client().put_object(Bucket=bucket, Key=key, Body=body)
        return f"s3://{bucket}/{key}"
    except (ClientError, BotoCoreError) as exc:
        if isinstance(exc, ClientError) and exc.response["Error"]["Code"] == "NoSuchBucket":
            # Auto-create bucket for dev/demo robustness
            try:
                _client().create_bucket(Bucket=bucket)
                _client().put_object(Bucket=bucket, Key=key, Body=body)
                return f"s3://{bucket}/{key}"
            except Exception as create_exc:
                logger.error("s3_create_bucket_failed", bucket=bucket, error=str(create_exc))
                # Fall through to original error raise
        
        logger.error("s3_put_failed", bucket=bucket, key=key, error=str(exc))
        raise HTTPException(
            status_code=500, detail="Failed to store data in S3"
        ) from exc


def put_bytes(bucket: str, key: str, content: bytes) -> str:
    """Upload raw bytes to S3 and return the object URI."""

    try:
        _client().put_object(Bucket=bucket, Key=key, Body=content)
        return f"s3://{bucket}/{key}"
    except (ClientError, BotoCoreError) as exc:
        if isinstance(exc, ClientError) and exc.response["Error"]["Code"] == "NoSuchBucket":
             # Auto-create bucket for dev/demo robustness
            try:
                _client().create_bucket(Bucket=bucket)
                _client().put_object(Bucket=bucket, Key=key, Body=content)
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
