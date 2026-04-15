"""
Abstract base for ingestion adapters.

Every data format entering RegEngine should follow this contract:
    parse → normalize → validate → map_to_canonical

This ensures a second similar customer is materially easier than the first.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class AdapterResult:
    """Result of running an adapter pipeline on raw input."""

    events: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    record_count: int = 0
    source_format: str = ""

    @property
    def success(self) -> bool:
        return len(self.events) > 0 and len(self.errors) == 0


class IngestAdapter(ABC):
    """Base class for all ingestion format adapters.

    Subclasses implement four steps that transform raw input into
    canonical traceability events ready for persistence.

    Each step is isolated so it can be tested independently:
        parse()           — raw bytes/string → structured data (format-specific)
        normalize()       — structured data → common intermediate dict
        validate()        — check FSMA KDE requirements, return errors/warnings
        map_to_canonical() — intermediate dict → canonical event dict(s)
    """

    #: Short identifier for this format (e.g., "epcis", "edi", "csv")
    format_id: str = ""

    @abstractmethod
    def parse(self, raw_input: Any, **kwargs) -> List[Dict[str, Any]]:
        """Parse raw input into a list of structured records.

        Args:
            raw_input: Format-specific input (bytes, string, dict, UploadFile)

        Returns:
            List of parsed records (format-specific structure).
        """

    @abstractmethod
    def normalize(self, parsed_records: List[Dict[str, Any]],
                  **kwargs) -> List[Dict[str, Any]]:
        """Normalize parsed records into a common intermediate schema.

        Maps format-specific fields to the shared field names used by
        the validation and canonical mapping steps.
        """

    @abstractmethod
    def validate(self, normalized_records: List[Dict[str, Any]],
                 **kwargs) -> tuple[List[Dict[str, Any]], List[str]]:
        """Validate normalized records against FSMA KDE requirements.

        Returns:
            Tuple of (valid_records, error_messages).
            Records that fail validation are excluded from valid_records.
        """

    @abstractmethod
    def map_to_canonical(self, validated_records: List[Dict[str, Any]],
                         tenant_id: str, **kwargs) -> List[Dict[str, Any]]:
        """Map validated records to canonical traceability event dicts.

        The output should be ready for CanonicalEventStore.persist_event()
        or CTEPersistence.store_event().
        """

    def ingest(self, raw_input: Any, tenant_id: str,
               **kwargs) -> AdapterResult:
        """Run the full pipeline: parse → normalize → validate → map.

        This is the standard entry point. Override individual steps,
        not this method, unless you need custom orchestration.
        """
        result = AdapterResult(source_format=self.format_id)

        # 1. Parse
        try:
            parsed = self.parse(raw_input, **kwargs)
        except Exception as exc:
            result.errors.append(f"Parse error: {exc}")
            return result

        # 2. Normalize
        try:
            normalized = self.normalize(parsed, **kwargs)
        except Exception as exc:
            result.errors.append(f"Normalization error: {exc}")
            return result

        # 3. Validate
        valid_records, validation_errors = self.validate(normalized, **kwargs)
        result.errors.extend(validation_errors)
        if not valid_records:
            return result

        # 4. Map to canonical
        try:
            canonical_events = self.map_to_canonical(
                valid_records, tenant_id, **kwargs
            )
        except Exception as exc:
            result.errors.append(f"Canonical mapping error: {exc}")
            return result

        result.events = canonical_events
        result.record_count = len(canonical_events)
        return result


# Registry of available adapters by format ID.
# Populated by adapter modules at import time.
ADAPTER_REGISTRY: Dict[str, type[IngestAdapter]] = {}


def register_adapter(cls: type[IngestAdapter]) -> type[IngestAdapter]:
    """Decorator to register an adapter class in the global registry."""
    if cls.format_id:
        ADAPTER_REGISTRY[cls.format_id] = cls
    return cls
