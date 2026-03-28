import logging
import re
import requests
import defusedxml.ElementTree as ET
from urllib.parse import urljoin
from typing import Iterable, Optional
from datetime import datetime, timezone

from .base import StateRegistryScraper, Source, FetchedItem
from ...shared.url_validation import validate_url, SSRFError

logger = logging.getLogger("ingestion.scrapers.fda_enforcement")

class FDAEnforcementScraper(StateRegistryScraper):
    """
    Scraper for FDA Enforcement Actions (Warning Letters).
    Uses the Official FDA RSS Feed to discover new warning letters.
    """
    
    RSS_URL = "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/warning-letters/rss.xml"
    
    def list_sources(self) -> Iterable[Source]:
        """
        Fetch RSS feed, parse items, and return Source objects for each Warning Letter.
        """
        try:
            resp = requests.get(self.RSS_URL, timeout=30, headers={"User-Agent": "RegEngine/1.0"})
            resp.raise_for_status()
            
            # Parse XML
            root = ET.fromstring(resp.content)
            
            # Iterate over items
            # Structure: <rss><channel><item><link>...</link><title>...</title>...</item>...
            count = 0
            for item in root.findall(".//item"):
                link = item.find("link")
                title = item.find("title")
                pub_date = item.find("pubDate")
                
                if link is not None and link.text:
                    url = link.text.strip()
                    # SSRF protection: validate extracted URL before yielding
                    try:
                        validated_url = validate_url(url)
                    except SSRFError as e:
                        logger.debug("ssrf_validation_failed_fda_rss", url=url, error=str(e))
                        # Skip this URL, continue to next
                        continue

                    title_text = title.text.strip() if title is not None else "Unknown Warning Letter"
                    date_text = pub_date.text.strip() if pub_date is not None else None

                    yield Source(
                        url=validated_url,
                        title=title_text,
                        jurisdiction_code="US-FDA",
                        metadata={
                            "type": "warning_letter",
                            "published_date": date_text,
                            "discovery_date": datetime.now(timezone.utc).isoformat()
                        }
                    )
                    count += 1
            
            logger.info("fda_rss_parsed", items_found=count)
            
        except Exception as e:
            logger.error("fda_rss_failed", error=str(e))
            # Yield nothing if feed fails, but don't crash scheduler
            return []

    def fetch(self, source: Source) -> FetchedItem:
        """
        Fetch the full text of the Warning Letter.
        Deep Fetch: If the HTML contains a link to a PDF version, fetch that instead.
        """
        try:
            # SSRF protection: validate source URL before fetching
            try:
                validated_url = validate_url(source.url)
            except SSRFError as e:
                logger.warning("ssrf_validation_failed_fda_fetch", url=source.url, error=str(e))
                return FetchedItem(source=source, content_bytes=b"", content_type=None)

            # 1. Fetch Landing Page
            resp = requests.get(validated_url, timeout=30, headers={"User-Agent": "RegEngine/1.0"})
            resp.raise_for_status()

            content = resp.content
            content_type = resp.headers.get("Content-Type", "text/html; charset=utf-8")

            # 2. Check for PDF Link (Deep Fetch)
            # Regex for <a href="...pdf">
            pdf_match = re.search(r'href="([^"]+\.pdf)"', resp.text, re.IGNORECASE)

            if pdf_match:
                pdf_rel_url = pdf_match.group(1)
                pdf_url = urljoin(validated_url, pdf_rel_url)
                logger.info("fda_deep_fetch_pdf_found", base=validated_url, pdf=pdf_url)

                # SSRF protection: validate PDF URL before fetching
                try:
                    validated_pdf_url = validate_url(pdf_url)
                except SSRFError as e:
                    logger.debug("ssrf_validation_failed_fda_pdf", url=pdf_url, error=str(e))
                    # Fallback to original HTML content if PDF URL fails validation
                    return FetchedItem(
                        source=source,
                        content_bytes=content,
                        content_type=content_type
                    )

                try:
                    pdf_resp = requests.get(validated_pdf_url, timeout=45, headers={"User-Agent": "RegEngine/1.0"})
                    pdf_resp.raise_for_status()
                    content = pdf_resp.content
                    content_type = "application/pdf"
                except Exception as pdf_err:
                    logger.warning("fda_deep_fetch_failed", error=str(pdf_err))
                    # Fallback to original HTML content if PDF fetch fails

            return FetchedItem(
                source=source,
                content_bytes=content,
                content_type=content_type
            )
        except Exception as e:
            logger.error("fda_fetch_failed", url=source.url, error=str(e))
            return FetchedItem(source=source, content_bytes=b"", content_type=None)
