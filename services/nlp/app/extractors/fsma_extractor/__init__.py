"""
FSMA 204 Extractor package — backward-compatible facade.

This package replaces the former single-module ``fsma_extractor.py``.
Every symbol that was importable from
``services.nlp.app.extractors.fsma_extractor`` is re-exported here so all
existing import paths (and ``unittest.mock.patch`` targets such as
``...fsma_extractor.FSMAExtractor.table_extractor``) keep working unchanged.

Module layout:
    patterns.py           — regex patterns, doc-type indicators, DOC_TO_CTE
    classification.py     — document classification + FTL scoping
    tabular.py            — layout-aware tabular / line-item extraction
    entity_resolution.py  — GLN role mapping, KDE regex extraction, normalizers
    cte_builder.py        — CTE assembly, BOL split, confidence + validation
    serialization.py      — graph-event / FSMAEvent payload conversion
    extractor.py          — the FSMAExtractor class (composes the mixins)
"""

# F-NLP-2 compat: ``redact_pii`` was a module attribute of the old
# fsma_extractor module; keep it importable from the same location.
from shared.pii import redact_pii  # noqa: F401

from ..fsma_types import (  # noqa: F401 — backward compat re-exports
    CTEType,
    DocumentType,
    ExtractionConfidence,
    LineItem,
    KDE,
    CTE,
    FSMAExtractionResult,
    TOPIC_GRAPH_UPDATE,
    TOPIC_NEEDS_REVIEW,
    HITL_CONFIDENCE_THRESHOLD,
)
from .classification import (  # noqa: F401
    FTL_CATEGORIES,
    _ClassificationResult,
    DocumentClassificationMixin,
)
from .cte_builder import CTEBuilderMixin  # noqa: F401
from .entity_resolution import EntityResolutionMixin  # noqa: F401
from .extractor import FSMAExtractor, logger  # noqa: F401
from .patterns import ExtractionPatternsMixin  # noqa: F401
from .serialization import GraphEventSerializationMixin  # noqa: F401
from .tabular import TabularExtractionMixin  # noqa: F401

__all__ = [
    # Primary public API
    "FSMAExtractor",
    # Data types re-exported from fsma_types (legacy import path)
    "CTEType",
    "DocumentType",
    "ExtractionConfidence",
    "LineItem",
    "KDE",
    "CTE",
    "FSMAExtractionResult",
    "TOPIC_GRAPH_UPDATE",
    "TOPIC_NEEDS_REVIEW",
    "HITL_CONFIDENCE_THRESHOLD",
    # Module-level attributes of the former fsma_extractor.py
    "FTL_CATEGORIES",
    "redact_pii",
    "logger",
    # Submodule building blocks (new, for direct use)
    "ExtractionPatternsMixin",
    "DocumentClassificationMixin",
    "TabularExtractionMixin",
    "EntityResolutionMixin",
    "CTEBuilderMixin",
    "GraphEventSerializationMixin",
]
