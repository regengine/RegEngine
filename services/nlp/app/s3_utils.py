import boto3
import structlog
from botocore.exceptions import BotoCoreError, ClientError

from .config import get_settings

logger = structlog.get_logger("s3_utils")


def s3_client():
    settings = get_settings()
    return boto3.client("s3", endpoint_url=settings.aws_endpoint_url)


def get_bytes(bucket: str, key: str) -> bytes:
    try:
        cli = s3_client()
        obj = cli.get_object(Bucket=bucket, Key=key)
        return obj["Body"].read()
    except (ClientError, BotoCoreError) as exc:
        logger.error("s3_get_failed", bucket=bucket, key=key, error=str(exc))
        raise
