"""Federal Register source adapter."""

import time
from datetime import datetime
from typing import Dict, Iterator, List, Optional
from urllib.parse import urlencode

import httpx
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

from ..models import SourceMetadata
from ..utils import RateLimiter
from .base import SourceAdapter


class FederalRegisterAdapter(SourceAdapter):
    """
    Adapter for Federal Register API.
    
    API Documentation: https://www.federalregister.gov/reader-aids/developer-resources
    """
    
    BASE_URL = "https://www.federalregister.gov/api/v1"
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.rate_limiter = RateLimiter(requests_per_minute=60)
        self.session = httpx.Client()
        self.session.headers.update({"User-Agent": self.user_agent})
    
    def get_source_name(self) -> str:
        return "federal_register"
    
    def fetch_documents(
        self,
        vertical: str,
        max_documents: int = 100,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        agencies: Optional[List[str]] = None,
        **kwargs
    ) -> Iterator[tuple[bytes, SourceMetadata, Dict]]:
        """
        Fetch documents from Federal Register.
        
        Args:
            vertical: Regulatory vertical
            max_documents: Maximum documents to fetch
            date_from: Start date
            date_to: End date
            agencies: List of agency slugs to filter by
            **kwargs: Additional parameters
            
        Yields:
            Tuples of (content, metadata, document_metadata)
        """
        # Build search parameters
        params = {
            "per_page": min(max_documents, 1000),  # API max is 1000
            "order": "newest",
        }
        
        if date_from:
            params["conditions[publication_date][gte]"] = date_from.strftime("%Y-%m-%d")
        
        if date_to:
            params["conditions[publication_date][lte]"] = date_to.strftime("%Y-%m-%d")
        
        if agencies:
            params["conditions[agencies][]"] = agencies
        
        # Search for documents
        search_url = f"{self.BASE_URL}/documents.json"
        
        self.rate_limiter.wait_if_needed("federalregister.gov")
        
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
            response = _get_with_retry(search_url, params=params)
            self.rate_limiter.record_success("federalregister.gov")
            self.log_fetch(search_url, "success", response.status_code)
        except Exception as e:
            self.log_fetch(search_url, "failure", error=str(e))
            backoff = self.rate_limiter.record_error("federalregister.gov")
            if backoff:
                time.sleep(backoff)
            return
        
        data = response.json()
        results = data.get("results", [])
        
        # Fetch full text for each document
        count = 0
        for doc in results:
            if count >= max_documents:
                break
            
            # Get full text URL
            doc_number = doc.get("document_number")
            if not doc_number:
                continue
            
            full_text_url = doc.get("full_text_xml_url") or doc.get("html_url")
            if not full_text_url:
                continue
            
            self.rate_limiter.wait_if_needed("federalregister.gov")
            
            try:
                doc_response = self.session.get(full_text_url)
                doc_response.raise_for_status()
                content = doc_response.content
                self.rate_limiter.record_success("federalregister.gov")
                self.log_fetch(full_text_url, "success", doc_response.status_code)
            except httpx.HTTPError as e:
                self.log_fetch(full_text_url, "failure", error=str(e))
                backoff = self.rate_limiter.record_error("federalregister.gov")
                if backoff:
                    time.sleep(backoff)
                continue
            
            # Build source metadata
            source_metadata = SourceMetadata(
                source_url=full_text_url,
                fetch_timestamp=datetime.utcnow(),
                http_status=doc_response.status_code,
                http_headers=dict(doc_response.headers),
                etag=doc_response.headers.get("ETag"),
                last_modified=self._parse_last_modified(doc_response.headers.get("Last-Modified"))
            )
            
            # Build document metadata
            document_metadata = {
                "title": doc.get("title", ""),
                "document_number": doc_number,
                "publication_date": doc.get("publication_date"),
                "agencies": [agency.get("name") for agency in doc.get("agencies", [])],
                "document_type": doc.get("type", "other"),
                "cfr_references": self._extract_cfr_references(doc),
                "abstract": doc.get("abstract"),
            }
            
            yield content, source_metadata, document_metadata
            count += 1
    
    def _parse_last_modified(self, header_value: Optional[str]) -> Optional[datetime]:
        """Parse Last-Modified header."""
        if not header_value:
            return None
        try:
            return datetime.strptime(header_value, "%a, %d %b %Y %H:%M:%S GMT")
        except ValueError:
            return None
    
    def _extract_cfr_references(self, doc: Dict) -> List[str]:
        """Extract CFR references from document."""
        refs = []
        for ref in doc.get("regulations_dot_gov_info", {}).get("documents", []):
            if "title" in ref and "part" in ref:
                refs.append(f"{ref['title']} CFR {ref['part']}")
        return refs
