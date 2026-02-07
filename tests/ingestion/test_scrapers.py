"""Tests for state registry scraper framework.

Covers:
- Base data classes (Source, FetchedItem)
- Abstract scraper interface
- NYDFS scraper implementation
- Generic scraper implementation
- Error handling and retry logic
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestSourceDataClass:
    """Tests for Source data class."""

    def test_source_creation_with_url_only(self):
        """Verify Source can be created with just URL."""
        from services.ingestion.app.scrapers.state_adaptors.base import Source
        
        source = Source(url="https://example.com/doc.pdf")
        
        assert source.url == "https://example.com/doc.pdf"
        assert source.title is None
        assert source.jurisdiction_code is None
        assert source.metadata is None

    def test_source_creation_with_all_fields(self):
        """Verify Source with all fields."""
        from services.ingestion.app.scrapers.state_adaptors.base import Source
        
        source = Source(
            url="https://regulator.gov/rule.pdf",
            title="Important Regulation",
            jurisdiction_code="US-NY",
            metadata={"version": "2024-01"},
        )
        
        assert source.url == "https://regulator.gov/rule.pdf"
        assert source.title == "Important Regulation"
        assert source.jurisdiction_code == "US-NY"
        assert source.metadata["version"] == "2024-01"


class TestFetchedItemDataClass:
    """Tests for FetchedItem data class."""

    def test_fetched_item_creation(self):
        """Verify FetchedItem can be created."""
        from services.ingestion.app.scrapers.state_adaptors.base import Source, FetchedItem
        
        source = Source(url="https://example.com/doc.pdf")
        item = FetchedItem(
            source=source,
            content_bytes=b"PDF content",
            content_type="application/pdf",
        )
        
        assert item.source == source
        assert item.content_bytes == b"PDF content"
        assert item.content_type == "application/pdf"

    def test_fetched_item_optional_content_type(self):
        """Verify content_type is optional."""
        from services.ingestion.app.scrapers.state_adaptors.base import Source, FetchedItem
        
        source = Source(url="https://example.com/doc")
        item = FetchedItem(source=source, content_bytes=b"data")
        
        assert item.content_type is None


class TestStateRegistryScraperInterface:
    """Tests for abstract scraper interface."""

    def test_abstract_methods_defined(self):
        """Verify abstract methods are defined."""
        from services.ingestion.app.scrapers.state_adaptors.base import StateRegistryScraper
        
        # Should have abstract list_sources and fetch methods
        assert hasattr(StateRegistryScraper, "list_sources")
        assert hasattr(StateRegistryScraper, "fetch")

    def test_cannot_instantiate_base_class(self):
        """Verify base class cannot be instantiated."""
        from services.ingestion.app.scrapers.state_adaptors.base import StateRegistryScraper
        
        with pytest.raises(TypeError):
            StateRegistryScraper()


class TestNYDFSScraper:
    """Tests for NYDFS scraper implementation."""

    def test_list_sources_returns_nydfs_sources(self):
        """Verify NYDFS sources are listed."""
        from services.ingestion.app.scrapers.state_adaptors.nydfs import NYDFSScraper
        
        scraper = NYDFSScraper()
        sources = list(scraper.list_sources())
        
        assert len(sources) >= 1
        assert all(s.jurisdiction_code == "US-NY" for s in sources)
        assert any("cybersecurity" in s.url.lower() for s in sources)

    def test_base_url_is_correct(self):
        """Verify NYDFS base URL."""
        from services.ingestion.app.scrapers.state_adaptors.nydfs import NYDFSScraper
        
        assert NYDFSScraper.BASE_URL == "https://www.dfs.ny.gov"

    def test_fetch_with_successful_response(self):
        """Verify successful fetch returns content."""
        from services.ingestion.app.scrapers.state_adaptors.nydfs import NYDFSScraper
        from services.ingestion.app.scrapers.state_adaptors.base import Source
        
        scraper = NYDFSScraper()
        source = Source(url="https://www.dfs.ny.gov/test", jurisdiction_code="US-NY")
        
        with patch("services.ingestion.app.scrapers.state_adaptors.nydfs.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.content = b"<html><body>Regulation text</body></html>"
            mock_response.headers = {"Content-Type": "text/html"}
            mock_get.return_value = mock_response
            
            result = scraper.fetch(source)
            
            assert result.source == source
            assert len(result.content_bytes) > 0

    def test_fetch_handles_rate_limiting(self):
        """Verify 429 responses are handled with retry."""
        from services.ingestion.app.scrapers.state_adaptors.nydfs import NYDFSScraper
        from services.ingestion.app.scrapers.state_adaptors.base import Source
        
        scraper = NYDFSScraper()
        source = Source(url="https://www.dfs.ny.gov/test", jurisdiction_code="US-NY")
        
        with patch("services.ingestion.app.scrapers.state_adaptors.nydfs.requests.get") as mock_get:
            with patch("services.ingestion.app.scrapers.state_adaptors.nydfs.time.sleep"):
                # First call returns 429, second succeeds
                mock_429 = MagicMock()
                mock_429.status_code = 429
                mock_429.headers = {"Retry-After": "1"}
                
                mock_200 = MagicMock()
                mock_200.status_code = 200
                mock_200.content = b"<html><body>Success</body></html>"
                mock_200.headers = {"Content-Type": "text/html"}
                
                mock_get.side_effect = [mock_429, mock_200]
                
                result = scraper.fetch(source)
                
                assert len(result.content_bytes) > 0

    def test_fetch_extracts_text_from_html(self):
        """Verify HTML is parsed and text extracted."""
        from services.ingestion.app.scrapers.state_adaptors.nydfs import NYDFSScraper
        from services.ingestion.app.scrapers.state_adaptors.base import Source
        
        scraper = NYDFSScraper()
        source = Source(url="https://www.dfs.ny.gov/test", jurisdiction_code="US-NY")
        
        html_content = b"""
        <html>
            <head><title>NYDFS</title></head>
            <body>
                <nav>Navigation</nav>
                <main>Important regulatory text here</main>
                <script>console.log('removed')</script>
                <footer>Footer text</footer>
            </body>
        </html>
        """
        
        with patch("services.ingestion.app.scrapers.state_adaptors.nydfs.requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.content = html_content
            mock_response.headers = {"Content-Type": "text/html"}
            mock_get.return_value = mock_response
            
            result = scraper.fetch(source)
            
            text = result.content_bytes.decode("utf-8")
            assert "Important regulatory text" in text
            # Script and nav should be removed
            assert "console.log" not in text

    def test_fetch_handles_timeout(self):
        """Verify timeout is handled with retry."""
        from services.ingestion.app.scrapers.state_adaptors.nydfs import NYDFSScraper
        from services.ingestion.app.scrapers.state_adaptors.base import Source
        import requests
        
        scraper = NYDFSScraper()
        source = Source(url="https://www.dfs.ny.gov/test", jurisdiction_code="US-NY")
        
        with patch("services.ingestion.app.scrapers.state_adaptors.nydfs.requests.get") as mock_get:
            with patch("services.ingestion.app.scrapers.state_adaptors.nydfs.time.sleep"):
                mock_get.side_effect = requests.Timeout("Connection timed out")
                
                with pytest.raises(requests.Timeout):
                    scraper.fetch(source)


class TestGenericScraper:
    """Tests for generic state scraper."""

    def test_generic_scraper_exists(self):
        """Verify generic scraper is importable."""
        from services.ingestion.app.scrapers.state_generic import StateRegistryScraper
        
        assert StateRegistryScraper is not None


class TestScraperConstants:
    """Tests for scraper configuration constants."""

    def test_nydfs_timeout_is_reasonable(self):
        """Verify request timeout is set appropriately."""
        from services.ingestion.app.scrapers.state_adaptors.nydfs import NYDFSScraper
        
        assert NYDFSScraper.REQUEST_TIMEOUT >= 10
        assert NYDFSScraper.REQUEST_TIMEOUT <= 60

    def test_nydfs_max_retries_is_reasonable(self):
        """Verify max retries is set appropriately."""
        from services.ingestion.app.scrapers.state_adaptors.nydfs import NYDFSScraper
        
        assert NYDFSScraper.MAX_RETRIES >= 1
        assert NYDFSScraper.MAX_RETRIES <= 5

    def test_nydfs_retry_delay_is_reasonable(self):
        """Verify retry delay is set appropriately."""
        from services.ingestion.app.scrapers.state_adaptors.nydfs import NYDFSScraper
        
        assert NYDFSScraper.RETRY_DELAY >= 1.0
        assert NYDFSScraper.RETRY_DELAY <= 10.0
