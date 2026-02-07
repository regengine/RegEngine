"""FERC source adapter."""

from datetime import datetime
from typing import Dict, Iterator, Optional
import requests

from ..models import SourceMetadata
from ..utils import RateLimiter
from .base import SourceAdapter


class FERCAdapter(SourceAdapter):
    """
    Adapter for FERC (Federal Energy Regulatory Commission) filings and orders.
    
    API Documentation: https://www.ferc.gov/ferc-online/ferconline/api-documentation (Mocked/Representative)
    """
    
    BASE_URL = "https://elibrary.ferc.gov/eLibrary/search"
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.rate_limiter = RateLimiter(requests_per_minute=30)
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.user_agent})
    
    def get_source_name(self) -> str:
        return "ferc"
    
    def fetch_documents(
        self,
        vertical: str = "energy",
        max_documents: int = 10,
        **kwargs
    ) -> Iterator[tuple[bytes, SourceMetadata, Dict]]:
        """
        Fetch documents from FERC eLibrary.
        """
        self.rate_limiter.wait_if_needed("elibrary.ferc.gov")
        
        # Representative search for recent orders/filings
        try:
            # Note: In a real production system, this would interact with the FERC eLibrary API/Scraper
            response = self.session.get(self.BASE_URL, params={"sort": "date_desc"})
            response.raise_for_status()
            self.rate_limiter.record_success("elibrary.ferc.gov")
        except requests.RequestException as e:
            self.log_fetch(self.BASE_URL, "failure", error=str(e))
            return

        # Mocked ingestion of a FERC order for demonstration
        content = b"FERC ORDER 881: Managing Transmission Line Ratings. This order requires transmission providers to use ambient-adjusted ratings..."
        
        source_metadata = SourceMetadata(
            source_url=self.BASE_URL,
            fetch_timestamp=datetime.utcnow(),
            http_status=200,
            http_headers={}
        )
        
        document_metadata = {
            "title": "FERC Order No. 881",
            "document_type": "order",
            "vertical": "energy",
            "agencies": ["FERC"],
            "document_number": "881",
            "publication_date": "2021-12-16"
        }
        
        yield content, source_metadata, document_metadata
