import os

import boto3
import structlog
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from .config import get_settings

logger = structlog.get_logger("s3_utils")

# Size envelope for supplier-linked S3 objects. The HTTP ingestion path
# already caps bodies (see MAX_DOC_BYTES in text_loader.py); without a
# matching cap here one oversized object is buffered fully into consumer
# memory. Defaults to the same envelope; override with NLP_MAX_S3_BYTES.
MAX_S3_BYTES = int(os.getenv("NLP_MAX_S3_BYTES", os.getenv("NLP_MAX_DOC_BYTES", "25000000")))

_READ_CHUNK_SIZE = 256 * 1024


class S3ObjectTooLargeError(ValueError):
    """Raised when an S3 object exceeds the size envelope."""


_S3_CONFIG = Config(
    connect_timeout=5,
    read_timeout=30,
    retries={"max_attempts": 2},
)


def s3_client():
    settings = get_settings()
    return boto3.client("s3", endpoint_url=settings.object_storage_endpoint_url, config=_S3_CONFIG)


def get_bytes(bucket: str, key: str, max_bytes: int = MAX_S3_BYTES) -> bytes:
    try:
        cli = s3_client()
        obj = cli.get_object(Bucket=bucket, Key=key)
        # Check the declared length first so an obviously oversized
        # object is rejected before any bytes are buffered.
        declared = obj.get("ContentLength") or 0
        if declared > max_bytes:
            logger.warning(
                "s3_object_too_large",
                bucket=bucket,
                key=key,
                declared_bytes=declared,
                max_bytes=max_bytes,
            )
            raise S3ObjectTooLargeError(
                f"E_DOC_TOO_LARGE: s3://{bucket}/{key} declares {declared} bytes, cap is {max_bytes}"
            )
        # Cap the streamed bytes too: a wrong or missing ContentLength
        # must not let an unbounded body into memory.
        body = obj["Body"]
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = body.read(_READ_CHUNK_SIZE)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                logger.warning(
                    "s3_object_too_large",
                    bucket=bucket,
                    key=key,
                    max_bytes=max_bytes,
                )
                raise S3ObjectTooLargeError(f"E_DOC_TOO_LARGE: s3://{bucket}/{key} exceeds {max_bytes} bytes")
            chunks.append(chunk)
        return b"".join(chunks)
    except S3ObjectTooLargeError:
        raise
    except (ClientError, BotoCoreError) as exc:
        logger.error("s3_get_failed", bucket=bucket, key=key, error=str(exc))
        raise
