import boto3
from botocore.config import Config
import structlog
from botocore.exceptions import BotoCoreError, ClientError

from .config import get_settings

logger = structlog.get_logger("s3_utils")

_S3_CONFIG = Config(
    connect_timeout=5,
    read_timeout=30,
    retries={"max_attempts": 2},
)


def s3_client():
    settings = get_settings()
    return boto3.client("s3", endpoint_url=settings.object_storage_endpoint_url, config=_S3_CONFIG)


def get_bytes(bucket: str, key: str) -> bytes:
    try:
        cli = s3_client()
        obj = cli.get_object(Bucket=bucket, Key=key)
        return obj["Body"].read()
    except (ClientError, BotoCoreError) as exc:
        logger.error("s3_get_failed", bucket=bucket, key=key, error=str(exc))
        raise
