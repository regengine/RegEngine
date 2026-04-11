"""Robots.txt parsing and compliance utilities."""

import logging
import urllib.robotparser
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger("robots-checker")


class RobotsChecker:
    """
    Check robots.txt compliance for URLs.
    
    Caches robots.txt parsers per domain for efficiency.
    """
    
    def __init__(self, user_agent: str = "RegEngine Ingestion Bot/1.0"):
        """
        Initialize robots checker.
        
        Args:
            user_agent: User agent string to identify as
        """
        self.user_agent = user_agent
        self._parsers = {}
    
    def can_fetch(self, url: str) -> bool:
        """
        Check if URL can be fetched according to robots.txt.
        
        Args:
            url: URL to check
            
        Returns:
            True if allowed, False if disallowed
        """
        parsed = urlparse(url)
        domain = f"{parsed.scheme}://{parsed.netloc}"
        robots_url = f"{domain}/robots.txt"
        
        # Get or create parser for this domain
        if domain not in self._parsers:
            parser = urllib.robotparser.RobotFileParser()
            parser.set_url(robots_url)
            try:
                parser.read()
                self._parsers[domain] = parser
            except Exception:
                # If robots.txt can't be read, assume allowed
                logger.debug("Robots.txt check failed, allowing crawl", exc_info=True)
                return True
        
        parser = self._parsers[domain]
        return parser.can_fetch(self.user_agent, url)
    
    def get_crawl_delay(self, url: str) -> Optional[float]:
        """
        Get crawl delay from robots.txt if specified.
        
        Args:
            url: URL to check
            
        Returns:
            Crawl delay in seconds, or None if not specified
        """
        parsed = urlparse(url)
        domain = f"{parsed.scheme}://{parsed.netloc}"
        
        if domain not in self._parsers:
            self.can_fetch(url)  # Load parser
        
        parser = self._parsers.get(domain)
        if parser:
            delay = parser.crawl_delay(self.user_agent)
            return float(delay) if delay else None
        return None
