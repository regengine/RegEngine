"""LlamaCloud "Extract" document-extraction integration for RegEngine.

Extract v2 turns a document plus a JSON Schema into schema-conforming JSON
with a citation and confidence per field. RegEngine uses it for the
trading-partner paperwork (invoices, bills of lading, receiving logs) whose
KDEs would otherwise be keyed by hand, and keeps validation, tenant scoping
and evidence persistence in code.

Public surface:

* :class:`LlamaExtractSettings` - environment-driven configuration (optional feature).
* :class:`DocumentExtractor` / :func:`get_document_extractor` - fail-open client wrapper.
* :class:`ExtractionResult`, :class:`ExtractionEvidence` - data plus provenance.
* :class:`LlamaExtractUnavailable` - raised whenever the caller must use its
  deterministic path instead.
"""

from .client import (
    DocumentExtractor,
    ExtractionEvidence,
    ExtractionResult,
    LlamaExtractUnavailable,
    classify_error,
    get_document_extractor,
    guard_sdk_logging,
    reset_document_extractor,
    schema_digest,
    schema_from,
)
from .settings import LlamaExtractSettings

__all__ = [
    "DocumentExtractor",
    "ExtractionEvidence",
    "ExtractionResult",
    "LlamaExtractSettings",
    "LlamaExtractUnavailable",
    "classify_error",
    "get_document_extractor",
    "guard_sdk_logging",
    "reset_document_extractor",
    "schema_digest",
    "schema_from",
]
