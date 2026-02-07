import io
import os
import re
import sys
from pathlib import Path
from typing import Tuple

import boto3

# Add shared module to path for validation
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "shared"))
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
    Requires AWS credentials configured in environment or instance profile.
    """
    bucket, key = parse_s3_uri(s3_uri)
    s3 = boto3.client("s3")
    # Try presigned URL for uniform handling
    try:
        url = s3.generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=int(os.getenv("PRESIGN_EXPIRES", "600")),
        )
        return load_artifact(url)
    except Exception:
        # Fallback: download bytes and simple decode
        params = {"Bucket": bucket, "Key": key}
        owner = os.getenv("AWS_EXPECTED_BUCKET_OWNER")
        if owner:
            params["ExpectedBucketOwner"] = owner
        obj = s3.get_object(**params)
        data = obj["Body"].read()
        return data.decode(errors="ignore")
