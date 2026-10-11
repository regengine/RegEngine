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

from .text_loader import MAX_DOC_BYTES, load_artifact

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
        # Fallback: download bytes with the same envelope the presigned
        # path gets via load_artifact (size cap + strict UTF-8). Without
        # this a hostile object could blow memory and malformed bytes
        # would be silently dropped, mutilating lot codes downstream.
        params = {"Bucket": bucket, "Key": key}
        owner = os.getenv("OBJECT_STORAGE_EXPECTED_BUCKET_OWNER")
        if owner:
            params["ExpectedBucketOwner"] = owner
        obj = s3.get_object(**params)
        declared = obj.get("ContentLength")
        if isinstance(declared, int) and declared > MAX_DOC_BYTES:
            raise ValueError("E_DOC_TOO_LARGE: S3 object ContentLength exceeds cap")
        chunks: list[bytes] = []
        total = 0
        body = obj["Body"]
        while True:
            piece = body.read(256 * 1024)
            if not piece:
                break
            total += len(piece)
            if total > MAX_DOC_BYTES:
                raise ValueError("E_DOC_TOO_LARGE: S3 object bytes exceed cap")
            chunks.append(piece)
        data = b"".join(chunks)
        try:
            return data.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise ValueError("E_DOC_DECODE_FAILED") from exc
