from __future__ import annotations

import asyncio
import hashlib
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests
import structlog
from redis import Redis

from kernel.parser import RegulationParser
from kernel.obligation.regulation_loader import RegulationLoader

logger = structlog.get_logger("regulation-discovery")


class EthicalScraper:
    """
    Crawler that respects robots.txt, implements polite delays,
    and is idempotent via ETag + content-hash deduplication.
    """

    def __init__(self, redis_url: str = "redis://redis:6379/0"):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "RegEngine-Research-Bot/1.0 (+https://regengine.co/bot)"
        })
        self.redis = Redis.from_url(redis_url)

    def can_fetch(self, url: str) -> bool:
        """Check if robots.txt allows fetching this URL."""
        parsed = urlparse(url)
        rp = RobotFileParser()
        rp.set_url(f"{parsed.scheme}://{parsed.netloc}/robots.txt")
        try:
            rp.read()
            return rp.can_fetch("RegEngine-Research-Bot", url)
        except Exception as e:
            logger.warning("robots_txt_unreachable", url=url, error=str(e))
            return True  # Default allow if robots.txt is unreachable

    def _content_hash(self, content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    async def scrape(
        self,
        body: str,
        source_url: str,
        source_type: str = "html",
        jurisdiction: str = "FDA",
        tenant_id: str = "system",
    ) -> Dict[str, Any]:
        """
        Politely scrape a regulatory source and trigger codification.

        Idempotency strategy (two-layer):
        1. ETag / Last-Modified: send conditional GET, skip on HTTP 304.
        2. Content hash: if server doesn't support ETags, compare SHA-256
           of response body against the last stored hash.

        Args:
            tenant_id: Used to namespace the manual_upload_queue in Redis,
                       preventing cross-tenant queue pollution. Defaults to
                       'system' for scheduler-triggered runs.
        """
        if not self.can_fetch(source_url):
            logger.info("scraping_denied_by_robots", body=body, url=source_url)
            queue_key = f"manual_upload_queue:{tenant_id}"
            self.redis.rpush(queue_key, f"{body}:{source_url}")
            return {"status": "queued_manual", "reason": "robots.txt disallowed", "queue": queue_key}

        # Polite delay — avoid hammering official gov sites
        await asyncio.sleep(2)

        # ── Layer 1: ETag conditional GET ────────────────────────────────
        etag_key = f"etag:{source_url}"
        lm_key = f"lm:{source_url}"  # Last-Modified
        hash_key = f"hash:{source_url}"

        stored_etag = self.redis.get(etag_key)
        stored_lm = self.redis.get(lm_key)

        req_headers: Dict[str, str] = {}
        if stored_etag:
            req_headers["If-None-Match"] = stored_etag.decode()
        if stored_lm:
            req_headers["If-Modified-Since"] = stored_lm.decode()

        logger.info("polite_scrape_started", body=body, url=source_url, jurisdiction=jurisdiction)

        try:
            response = self.session.get(source_url, headers=req_headers, timeout=30)

            if response.status_code == 304:
                logger.info("source_unchanged_etag", body=body, url=source_url)
                return {"status": "unchanged", "reason": "304 Not Modified"}

            response.raise_for_status()

            # ── Layer 2: Content-hash fallback ───────────────────────────
            content_hash = self._content_hash(response.content)
            stored_hash = self.redis.get(hash_key)
            if stored_hash and stored_hash.decode() == content_hash:
                logger.info("source_unchanged_hash", body=body, url=source_url)
                return {"status": "unchanged", "reason": "content hash match"}

            # Store new ETag / Last-Modified / hash for next run
            new_etag = response.headers.get("ETag", "")
            new_lm = response.headers.get("Last-Modified", "")
            if new_etag:
                self.redis.set(etag_key, new_etag)
            if new_lm:
                self.redis.set(lm_key, new_lm)
            self.redis.set(hash_key, content_hash)

            # ── Persist raw artifact ─────────────────────────────────────
            ext = source_type if source_type in ("pdf", "html") else "html"
            if "html" in response.headers.get("Content-Type", "").lower():
                ext = "html"
            elif "pdf" in response.headers.get("Content-Type", "").lower():
                ext = "pdf"

            path = f"/tmp/{body}_{int(time.time())}.{ext}"
            with open(path, "wb") as f:
                f.write(response.content)

            # ── Parse + load ─────────────────────────────────────────────
            parse_source_type = "url" if ext == "html" else "pdf"
            parser = RegulationParser()
            sections = await parser.parse(path, parse_source_type)

            loader = RegulationLoader()
            count = await loader.load(path, parse_source_type, body)
            loader.close()

            logger.info(
                "ethical_ingestion_complete",
                body=body,
                jurisdiction=jurisdiction,
                sections=count,
                content_hash=content_hash[:12],
            )
            return {
                "status": "ingested",
                "body": body,
                "jurisdiction": jurisdiction,
                "sections": count,
                "content_hash": content_hash[:12],
            }

        except Exception as e:
            logger.error("ethical_scrape_failed", body=body, url=source_url, error=str(e))
            return {"status": "failed", "body": body, "error": str(e)}


# Singleton for service use
discovery = EthicalScraper()
