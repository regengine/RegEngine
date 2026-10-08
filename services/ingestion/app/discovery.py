from __future__ import annotations

import asyncio
import hashlib
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import structlog
from redis import Redis
from shared.safe_http import DEFAULT_MAX_RESPONSE_BYTES, ResponseTooLargeError, safe_httpx_get_sync
from shared.url_validation import SSRFError

from services.ingestion.app.regulation_loader import RegulationLoader
from services.ingestion.app.regulation_parser import RegulationParser

logger = structlog.get_logger("regulation-discovery")

DISCOVERY_USER_AGENT = "RegEngine-Research-Bot/1.0 (+https://regengine.co/bot)"
DISCOVERY_MAX_BYTES = DEFAULT_MAX_RESPONSE_BYTES
ROBOTS_TXT_MAX_BYTES = 256 * 1024


class EthicalScraper:
    """
    Crawler that respects robots.txt, implements polite delays,
    and is idempotent via ETag + content-hash deduplication.

    All outbound HTTP goes through :func:`shared.safe_http.safe_httpx_get_sync`
    so private or link-local targets are refused before connecting and every
    redirect hop is re-validated, with response bodies capped at
    ``DISCOVERY_MAX_BYTES``.
    """

    def __init__(self, redis_url: str | None = None):
        self.headers = {"User-Agent": DISCOVERY_USER_AGENT}
        # #2505: read REDIS_URL like every other Redis consumer
        # (server/main.py readiness probe, shared.idempotency,
        # shared.circuit_breaker_store, shared.api_key_store). The old
        # hardcoded "redis://redis:6379/0" default only resolves on
        # docker-compose; on Railway it points at a non-existent host, so
        # every nightly FSMA-sync dedup op failed silently. Reading the env
        # var also inherits the correct scheme (e.g. rediss:// for TLS).
        self.redis = Redis.from_url(redis_url or os.getenv("REDIS_URL", "redis://redis:6379/0"))

    def can_fetch(self, url: str) -> bool:
        """Check if robots.txt allows fetching this URL.

        Raises :class:`SSRFError` when the URL or its robots.txt target is
        not a public destination. Callers must refuse the scrape outright
        in that case (never queue it for manual upload).
        """
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        rp = RobotFileParser()
        rp.set_url(robots_url)
        try:
            resp = safe_httpx_get_sync(
                robots_url,
                headers=self.headers,
                timeout=10,
                max_bytes=ROBOTS_TXT_MAX_BYTES,
            )
            if resp.status_code in (401, 403):
                logger.info("robots_txt_forbidden", url=url, status_code=resp.status_code)
                return False
            resp.raise_for_status()
            lines = resp.text.splitlines()
            rp.parse(lines)
            return rp.can_fetch("RegEngine-Research-Bot", url)
        except SSRFError:
            raise
        except ResponseTooLargeError as e:
            logger.warning("robots_txt_too_large", url=url, error=str(e))
            return False
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
        try:
            robots_allowed = self.can_fetch(source_url)
        except SSRFError as e:
            logger.warning("scrape_refused_unsafe_url", body=body, url=source_url, error=str(e))
            return {"status": "failed", "body": body, "error": f"URL refused: {e}"}

        if not robots_allowed:
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
            headers = dict(self.headers)
            headers.update(req_headers)
            response = safe_httpx_get_sync(
                source_url,
                headers=headers,
                timeout=30,
                max_bytes=DISCOVERY_MAX_BYTES,
            )

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

            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix="regengine-discovery-",
                suffix=f".{ext}",
                delete=False,
            ) as artifact:
                path = artifact.name
                artifact.write(response.content)

            try:
                # ── Parse + load ─────────────────────────────────────────────
                parse_source_type = "html" if ext == "html" else "pdf"
                parser = RegulationParser()
                await parser.parse(path, parse_source_type)

                loader = RegulationLoader()
                try:
                    count = await loader.load(path, parse_source_type, body)
                finally:
                    loader.close()
            finally:
                try:
                    Path(path).unlink(missing_ok=True)
                except Exception as cleanup_error:
                    logger.warning(
                        "temporary_artifact_cleanup_failed",
                        path=path,
                        error=str(cleanup_error),
                    )

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
