import asyncio
import datetime as dt
import os
import uuid
from typing import Optional

import requests
from shared.url_validation import validate_url, SSRFError


# Stubs for S3 and Kafka integrations; replace with actual clients
class S3Client:
    def upload_bytes(self, bucket: str, key: str, data: bytes, content_type: str):
        # Placeholder: integrate with real S3 client in production
        _ = (data, content_type)
        return f"s3://{bucket}/{key}"


class KafkaProducer:
    def emit(self, topic: str, payload: dict):
        # Placeholder: integrate with real Kafka producer in production
        _ = (topic, payload)
        return True


class StateRegistryScraper:
    """
    Generic scraper for State Register sites (often simple HTML lists).
    Fetches PDF/HTML and metadata, and stores raw artifact to S3.
    """

    def __init__(
        self,
        s3_bucket: Optional[str] = None,
        s3_client: Optional[S3Client] = None,
        kafka: Optional[KafkaProducer] = None,
    ):
        self.s3_bucket = s3_bucket or os.getenv("RAW_INGEST_BUCKET", "regengine-raw")
        self.s3 = s3_client or S3Client()
        self.kafka = kafka or KafkaProducer()

    async def fetch_document(
        self, url: str, jurisdiction_code: str, tenant_id: Optional[str] = None
    ) -> dict:
        # SSRF protection: validate URL before fetching
        try:
            url = validate_url(url)
        except SSRFError as e:
            raise ValueError(f"URL validation failed: {str(e)}") from e

        loop = asyncio.get_running_loop()

        def _fetch():
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            return resp

        resp = await loop.run_in_executor(None, _fetch)
        content_type = resp.headers.get("Content-Type", "application/octet-stream")

        now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
        doc_id = str(uuid.uuid4())
        key = f"raw/{jurisdiction_code}/{now}/{doc_id}"

        # S3 upload might also be blocking if the client is sync.
        # Assuming S3Client.upload_bytes is sync for now, we should wrap it too if we want full async.
        # But the audit focused on requests.get. Let's wrap the whole sync operation or just the fetch.
        # The S3 upload is also I/O bound.

        def _upload_and_emit():
            s3_uri = self.s3.upload_bytes(
                self.s3_bucket, key, resp.content, content_type
            )
            return s3_uri

        s3_uri = await loop.run_in_executor(None, _upload_and_emit)

        event = {
            "type": "ingest.raw_collected",
            "jurisdiction_code": jurisdiction_code,
            "source_url": url,
            "s3_uri": s3_uri,
            "doc_id": doc_id,
            "content_type": content_type,
            "tenant_id": tenant_id,
        }
        self.kafka.emit("ingest.raw_collected", event)
        return event
