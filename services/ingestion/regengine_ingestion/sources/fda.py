"""FDA source adapter."""

import json
import time
from datetime import datetime
from typing import Dict, Iterator, List, Optional

import requests
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

from ..models import SourceMetadata
from ..utils import RateLimiter
from .base import SourceAdapter


class FDAAdapter(SourceAdapter):
    """
    Adapter for openFDA API.
    
    API Documentation: https://open.fda.gov/apis/
    """
    
    BASE_URL = "https://api.fda.gov"
    
    def __init__(self, api_key: Optional[str] = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Without key: 40 requests/min. With key: 240 requests/min.
        rpm = 240 if api_key else 40
        self.rate_limiter = RateLimiter(requests_per_minute=rpm)
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.user_agent})
        self.api_key = api_key
    
    def get_source_name(self) -> str:
        return "fda"
    
    def fetch_documents(
        self,
        vertical: str,
        max_documents: int = 100,
        **kwargs
    ) -> Iterator[tuple[bytes, SourceMetadata, Dict]]:
        """
        Fetch documents from openFDA (Warning Letters).
        
        Args:
            vertical: Regulatory vertical
            max_documents: Maximum documents to fetch
            **kwargs: Additional parameters
            
        Yields:
            Tuples of (content, metadata, document_metadata)
        """
        # Fetch food enforcement records (recalls, market withdrawals)
        url = f"{self.BASE_URL}/food/enforcement.json"
        params = {
            "limit": min(max_documents, 99),  # openFDA limit
            "sort": "posted_date:desc"
        }
        if self.api_key:
            params["api_key"] = self.api_key
            
        self.rate_limiter.wait_if_needed("api.fda.gov")
        
        @retry(
            wait=wait_exponential(multiplier=1, min=4, max=10),
            stop=stop_after_attempt(3),
            retry=retry_if_exception_type(requests.RequestException),
            reraise=True
        )
        def _get_with_retry(url, params=None):
            resp = self.session.get(url, params=params)
            resp.raise_for_status()
            return resp

        try:
            response = _get_with_retry(url, params=params)
            self.rate_limiter.record_success("api.fda.gov")
            self.log_fetch(url, "success", response.status_code)
        except Exception as e:
            self.log_fetch(url, "failure", error=str(e))
            backoff = self.rate_limiter.record_error("api.fda.gov")
            if backoff:
                time.sleep(backoff)
            return
            
        data = response.json()
        results = data.get("results", [])
        
        for doc in results:
            # openFDA returns JSON objects. Serialize to valid JSON for the parser registry.
            content = json.dumps(doc).encode("utf-8")
            
            # Build source metadata
            source_metadata = SourceMetadata(
                source_url=url, # openFDA search URL
                fetch_timestamp=datetime.utcnow(),
                http_status=response.status_code,
                http_headers=dict(response.headers)
            )
            
            # Build document metadata
            document_metadata = {
                "title": f"FDA Warning Letter: {doc.get('company_name', 'Unknown')}",
                "document_number": doc.get("letter_id", ""),
                "publication_date": doc.get("posted_date"),
                "agencies": ["FDA"],
                "document_type": "warning_letter",
                "abstract": doc.get("subject", ""),
            }
            
            yield content, source_metadata, document_metadata
