from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterable, Optional


@dataclass
class Source:
    """Represents a single registry source item to fetch."""

    url: str
    title: Optional[str] = None
    jurisdiction_code: Optional[str] = None  # e.g., "US-NY", "US-CA"
    metadata: Optional[dict] = None  # Additional source-specific metadata


@dataclass
class FetchedItem:
    """Fetched payload with minimal metadata."""

    source: Source
    content_bytes: bytes
    content_type: Optional[str] = None  # e.g., application/pdf, text/html


class StateRegistryScraper(ABC):
    """Base interface for state/municipal registry scrapers."""

    @abstractmethod
    def list_sources(self) -> Iterable[Source]:
        """List available sources to fetch (e.g., RSS entries, index pages)."""

    @abstractmethod
    def fetch(self, source: Source) -> FetchedItem:
        """Fetch the content for a given source."""
