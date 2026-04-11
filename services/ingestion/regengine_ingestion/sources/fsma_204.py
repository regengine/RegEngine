"""FSMA 204 source adapter."""

import time
from datetime import datetime, timezone
from typing import Dict, Iterator, List, Optional
import httpx
from bs4 import BeautifulSoup

from ..models import SourceMetadata
from ..utils import RateLimiter
from .base import SourceAdapter


class FSMA204Adapter(SourceAdapter):
    """
    Adapter for FDA FSMA 204 (Food Traceability) guidance and updates.
    
    Targets the specific FDA FSMA 204 resource page to watch for updates.
    """
    
    TARGET_URL = "https://www.fda.gov/food/food-safety-modernization-act-fsma/fsma-final-rule-reporting-and-recordkeeping-additional-traceability-records-certain-foods"
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.rate_limiter = RateLimiter(requests_per_minute=20) # Conservative for non-API scrape
        self.session = httpx.Client(timeout=30.0)
        self.session.headers.update({"User-Agent": self.user_agent})
    
    def get_source_name(self) -> str:
        return "fsma_204"
    
    def fetch_documents(
        self,
        vertical: str = "food_safety",
        max_documents: int = 5,
        **kwargs
    ) -> Iterator[tuple[bytes, SourceMetadata, Dict]]:
        """
        Fetch FSMA 204 guidance and resources.
        
        Args:
            vertical: Regulatory vertical
            max_documents: Maximum documents to fetch
            **kwargs: Additional parameters
            
        Yields:
            Tuples of (content, metadata, document_metadata)
        """
        self.rate_limiter.wait_if_needed("www.fda.gov")
        
        try:
            response = self.session.get(self.TARGET_URL)
            response.raise_for_status()
            self.rate_limiter.record_success("www.fda.gov")
            self.log_fetch(self.TARGET_URL, "success", response.status_code)
        except httpx.HTTPError as e:
            self.log_fetch(self.TARGET_URL, "failure", error=str(e))
            return
            
        soup = BeautifulSoup(response.content, "html.parser")
        
        # In a real FSMA 204 watcher, we would look for specific guide links or FTL updates
        # For this implementation, we ingest the main rule page as a primary document
        content = response.content
        
        source_metadata = SourceMetadata(
            source_url=self.TARGET_URL,
            fetch_timestamp=datetime.now(timezone.utc),
            http_status=response.status_code,
            http_headers=dict(response.headers)
        )
        
        document_metadata = {
            "title": "FSMA Final Rule: Food Traceability",
            "document_type": "regulation",
            "vertical": "food_safety",
            "agencies": ["FDA"],
            "keywords": ["FSMA 204", "Food Traceability", "KDE", "CTE", "FTL"],
            "effective_date": "2023-01-20",  # FSMA 204 effective date
            "compliance_date": "2028-07-20"  # FSMA 204 compliance date
        }
        
        yield content, source_metadata, document_metadata
        
        # Proactively look for the Food Traceability List (FTL) PDF
        ftl_link = soup.find("a", string=lambda s: s and "Food Traceability List" in s)
        if ftl_link and ftl_link.get("href") and max_documents > 1:
            ftl_url = ftl_link.get("href")
            if not ftl_url.startswith("http"):
                ftl_url = f"https://www.fda.gov{ftl_url}"
                
            self.rate_limiter.wait_if_needed("www.fda.gov")
            try:
                ftl_response = self.session.get(ftl_url)
                ftl_response.raise_for_status()
                yield ftl_response.content, SourceMetadata(
                    source_url=ftl_url,
                    fetch_timestamp=datetime.now(timezone.utc),
                    http_status=ftl_response.status_code,
                    http_headers=dict(ftl_response.headers)
                ), {
                    "title": "Food Traceability List (FTL)",
                    "document_type": "guidance",
                    "vertical": "food_safety",
                    "agencies": ["FDA"],
                    "keywords": ["FTL", "High-Risk Foods", "Traceability"]
                }
            except Exception as e:
                self.log_fetch(ftl_url, "failure", error=str(e))
