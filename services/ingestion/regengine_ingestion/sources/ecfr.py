"""eCFR source adapter."""

import time
from datetime import datetime
from typing import Dict, Iterator, List, Optional

import httpx
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

from ..models import SourceMetadata
from ..utils import RateLimiter
from .base import SourceAdapter


class ECFRAdapter(SourceAdapter):
    """
    Adapter for eCFR (Electronic Code of Federal Regulations) API.
    
    API Documentation: https://www.ecfr.gov/reader-aids/developer-resources/api-versions/v1
    """
    
    BASE_URL = "https://www.ecfr.gov/api/renderer/v1"
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.rate_limiter = RateLimiter(requests_per_minute=30)  # Conservative rate limit
        self.session = httpx.Client()
        self.session.headers.update({"User-Agent": self.user_agent})
    
    def get_source_name(self) -> str:
        return "ecfr"
    
    def fetch_documents(
        self,
        vertical: str,
        cfr_title: Optional[int] = None,
        cfr_part: Optional[int] = None,
        **kwargs
    ) -> Iterator[tuple[bytes, SourceMetadata, Dict]]:
        """
        Fetch documents from eCFR.
        
        Args:
            vertical: Regulatory vertical
            cfr_title: CFR Title number
            cfr_part: CFR Part number
            **kwargs: Additional parameters
            
        Yields:
            Tuples of (content, metadata, document_metadata)
        """
        if not cfr_title or not cfr_part:
            return
            
        # eCFR API endpoint for a specific part
        # URL pattern: /content/v1/full/{date}/title-{title}.xml?part={part}
        date_str = datetime.utcnow().strftime("%Y-%m-%d")
        url = f"{self.BASE_URL}/content/v1/full/{date_str}/title-{cfr_title}.xml"
        params = {"part": str(cfr_part)}
        
        self.rate_limiter.wait_if_needed("ecfr.gov")
        
        @retry(
            wait=wait_exponential(multiplier=1, min=4, max=10),
            stop=stop_after_attempt(3),
            retry=retry_if_exception_type(httpx.HTTPError),
            reraise=True
        )
        def _get_with_retry(url, params=None):
            resp = self.session.get(url, params=params)
            resp.raise_for_status()
            return resp

        try:
            response = _get_with_retry(url, params=params)
            content = response.content
            self.rate_limiter.record_success("ecfr.gov")
            self.log_fetch(url, "success", response.status_code)
        except Exception as e:
            self.log_fetch(url, "failure", error=str(e))
            backoff = self.rate_limiter.record_error("ecfr.gov")
            if backoff:
                time.sleep(backoff)
            return
            
        # Build source metadata
        source_metadata = SourceMetadata(
            source_url=f"{url}?part={cfr_part}",
            fetch_timestamp=datetime.utcnow(),
            http_status=response.status_code,
            http_headers=dict(response.headers),
            etag=response.headers.get("ETag")
        )
        
        # Build document metadata
        document_metadata = {
            "title": f"CFR Title {cfr_title} Part {cfr_part}",
            "cfr_references": [f"{cfr_title} CFR {cfr_part}"],
            "document_type": "regulation",
            "publication_date": date_str,
        }
        
        yield content, source_metadata, document_metadata
