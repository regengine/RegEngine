"""NERC source adapter."""

from datetime import datetime
from typing import Dict, Iterator, Optional
import requests

from ..models import SourceMetadata
from ..utils import RateLimiter
from .base import SourceAdapter


class NERCAdapter(SourceAdapter):
    """
    Adapter for NERC (North American Electric Reliability Corporation) standards and reliability updates.
    
    Targets the NERC Standards portal.
    """
    
    BASE_URL = "https://www.nerc.com/pa/Stand/Pages/default.aspx"
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.rate_limiter = RateLimiter(requests_per_minute=20)
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.user_agent})
    
    def get_source_name(self) -> str:
        return "nerc"
    
    def fetch_documents(
        self,
        vertical: str = "energy",
        max_documents: int = 5,
        **kwargs
    ) -> Iterator[tuple[bytes, SourceMetadata, Dict]]:
        """
        Fetch documents from NERC Standards Portal.
        """
        self.rate_limiter.wait_if_needed("www.nerc.com")
        
        try:
            response = self.session.get(self.BASE_URL)
            response.raise_for_status()
            self.rate_limiter.record_success("www.nerc.com")
        except requests.RequestException as e:
            self.log_fetch(self.BASE_URL, "failure", error=str(e))
            return

        # Mocked ingestion of a NERC standard (e.g., CIP-003-9)
        content = b"NERC CIP-003-9: Cyber Security - Security Management Controls. This standard specifies the minimum cyber security controls..."
        
        source_metadata = SourceMetadata(
            source_url=self.BASE_URL,
            fetch_timestamp=datetime.utcnow(),
            http_status=200,
            http_headers={}
        )
        
        document_metadata = {
            "title": "NERC Standard CIP-003-9",
            "document_type": "standard",
            "vertical": "energy",
            "agencies": ["NERC"],
            "document_number": "CIP-003-9",
            "publication_date": "2023-01-01"
        }
        
        yield content, source_metadata, document_metadata
