import io
import logging
import os
import re
import sys
from pathlib import Path
from typing import Tuple

import boto3
from botocore.config import Config

logger = logging.getLogger("s3_loader")

# Import shared utilities
from shared.url_validation import PathTraversalError, validate_s3_uri

from .text_loader import load_artifact

S3_URL_RE = re.compile(r"^s3://([^/]+)/(.+)$")


def parse_s3_uri(s3_uri: str) -> Tuple[str, str]:
    """Parse and validate S3 URI.

    Raises:
        ValueError: If URI format is invalid
        PathTraversalError: If key contains traversal patterns
    """
    return validate_s3_uri(s3_uri)


def load_s3_artifact(s3_uri: str) -> str:
    """
    Load S3 artifact and return best-effort plain text using the same conversions
    as `load_artifact` by first obtaining a presigned URL when possible.
    Requires object storage credentials configured in environment.
    """
    bucket, key = parse_s3_uri(s3_uri)
    s3 = boto3.client("s3", config=Config(connect_timeout=5, read_timeout=30, retries={"max_attempts": 2}))
    # Try presigned URL for uniform handling
    try:
        url = s3.generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=int(os.getenv("PRESIGN_EXPIRES", "600")),
        )
        return load_artifact(url)
    except Exception:
        logger.debug("Presigned URL generation failed, falling back to raw download", exc_info=True)
        # Fallback: download bytes and simple decode
        params = {"Bucket": bucket, "Key": key}
        owner = os.getenv("OBJECT_STORAGE_EXPECTED_BUCKET_OWNER")
        if owner:
            params["ExpectedBucketOwner"] = owner
        obj = s3.get_object(**params)
        data = obj["Body"].read()
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            # Never drop bytes silently: log the fallback and decode with
            # visible replacement characters so downstream text shows the
            # gap instead of hiding it.
            logger.warning(
                "s3_fallback_body_not_utf8_using_replace (bucket=%s key=%s bytes=%d)",
                bucket,
                key,
                len(data),
            )
            return data.decode("utf-8", errors="replace")
