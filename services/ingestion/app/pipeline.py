"""
Ingestion Pipeline for Scraper Data.

Standardizes the flow of:
1. Validating fetched content
2. Uploading raw artifacts to S3
3. Emitting 'ingest.raw_collected' events to Kafka
"""

import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any

import structlog
from .config import get_settings
from .scrapers.state_generic import S3Client, KafkaProducer, StateRegistryScraper

logger = structlog.get_logger("ingestion.pipeline")

# Use singletons from generic scraper for now (Phase 2), 
# can be injected properly in Phase 3
_SHARED_S3 = S3Client()
_SHARED_KAFKA = KafkaProducer()

class ScraperPipeline:
    """Orchestrates persistent storage and messaging for scraped content."""

    def __init__(self, s3_client: Optional[S3Client] = None, kafka_producer: Optional[KafkaProducer] = None):
        self.settings = get_settings()
        self.s3 = s3_client or _SHARED_S3
        self.kafka = kafka_producer or _SHARED_KAFKA

    def process_content(
        self,
        content: bytes,
        content_type: str,
        jurisdiction_code: str,
        source_url: str,
        tenant_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Upload content to S3 and emit Kafka event.

        Returns:
            The emitted event dictionary.
        """
        if not content:
            logger.warning("pipeline_empty_content", url=source_url, jurisdiction=jurisdiction_code)
            return {}

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        doc_id = str(uuid.uuid4())
        
        # Consistent key structure: raw/<jurisdiction>/<date>/<uuid>
        key = f"raw/{jurisdiction_code}/{now}/{doc_id}"
        
        try:
            # 1. Upload to S3
            s3_uri = self.s3.upload_bytes(
                self.settings.raw_bucket, 
                key, 
                content, 
                content_type or "application/octet-stream"
            )
            
            # 2. Construct Event
            event = {
                "type": "ingest.raw_collected",
                "jurisdiction_code": jurisdiction_code,
                "source_url": source_url,
                "s3_uri": s3_uri,
                "doc_id": doc_id,
                "content_type": content_type,
                "tenant_id": tenant_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "pipeline_version": "2.0"
            }
            
            if metadata:
                event["metadata"] = metadata

            # 3. Emit to Kafka
            self.kafka.emit("ingest.raw_collected", event)
            
            logger.info(
                "pipeline_content_processed", 
                doc_id=doc_id, 
                jurisdiction=jurisdiction_code,
                bytes=len(content)
            )
            return event

        except Exception as e:
            logger.error(
                "pipeline_processing_failed", 
                url=source_url, 
                error=str(e)
            )
            raise e
