"""LlamaIndex "Extract" (LlamaCloud) integration for RegEngine.

Extract is a schema-guided document extraction agent: it takes a document
and a JSON Schema and returns the filled object with a citation and a
confidence per field. RegEngine runs the v2.5 line and uses it where the
deterministic parsers stop (supplier PDFs without tables) and for operator
extraction through ``scripts/extract_document.py``. Every decision stays in
code: results are advisory rows that go through the same validate -> persist
evidence path as a CSV upload.

Public surface:

* :class:`DocumentExtractSettings` - environment-driven configuration (optional feature).
* :class:`DocumentExtractor` / :func:`get_document_extractor` - fail-open client wrapper.
* :class:`ExtractionResult`, :class:`ExtractEvidence` - data plus provenance.
* :class:`DocumentExtractUnavailable` - raised whenever the caller must use its
  deterministic path instead.
* :data:`SUPPLIER_DOCUMENT_SCHEMA` / :func:`rows_from_extraction` - the FSMA 204
  supplier schema and its conversion to bulk-upload parser rows.
"""

from .client import (
    DocumentExtractor,
    DocumentExtractUnavailable,
    ExtractEvidence,
    ExtractionResult,
    classify_error,
    get_document_extractor,
    iter_confidences,
    mime_type_for,
    reset_document_extractor,
    summarize_confidences,
)
from .settings import EXTRACTION_TARGETS, TIERS, DocumentExtractSettings
from .supplier_schema import (
    SUPPLIER_DOCUMENT_SCHEMA,
    SUPPLIER_SCHEMA_VERSION,
    rows_from_extraction,
)

__all__ = [
    "EXTRACTION_TARGETS",
    "SUPPLIER_DOCUMENT_SCHEMA",
    "SUPPLIER_SCHEMA_VERSION",
    "TIERS",
    "DocumentExtractSettings",
    "DocumentExtractUnavailable",
    "DocumentExtractor",
    "ExtractEvidence",
    "ExtractionResult",
    "classify_error",
    "get_document_extractor",
    "iter_confidences",
    "mime_type_for",
    "reset_document_extractor",
    "rows_from_extraction",
    "summarize_confidences",
]
