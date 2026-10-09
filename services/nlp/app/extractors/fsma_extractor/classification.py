"""Document-type classification and FTL scoping for the FSMA extractor."""

import re
from typing import Optional, Tuple

import structlog

from ..fsma_types import DocumentType

# #1116 — Food Traceability List scoping. The rules engine already
# owns the authoritative catalog; the extractor classifies each
# product against it so non-FTL foods can be marked up-front and
# skipped downstream instead of generating spurious "missing TLC"
# warnings. The import is lazy-tolerant: a missing FTL module should
# not fail extraction (we degrade to ``is_ftl_covered=None`` which
# the downstream pipeline treats as a classification gap, not a
# positive compliance stamp — see #1346).
try:
    from shared.rules.ftl import FTL_CATEGORIES  # type: ignore[import]
except Exception:  # pragma: no cover - defense-in-depth for import paths
    FTL_CATEGORIES = frozenset()

logger = structlog.get_logger("fsma-extractor")


class _ClassificationResult(tuple):
    """Tuple-compatible classification result that also compares to DocumentType."""

    def __new__(cls, document_type: DocumentType, warning: Optional[str]):
        return tuple.__new__(cls, (document_type, warning))

    @property
    def document_type(self) -> DocumentType:
        return self[0]

    @property
    def warning(self) -> Optional[str]:
        return self[1]

    def __eq__(self, other: object) -> bool:
        if isinstance(other, DocumentType):
            return self.document_type == other
        return tuple.__eq__(self, other)

    def __repr__(self) -> str:
        return repr(self.document_type)


def _indicator_present(text_lower: str, indicator: str) -> bool:
    """Match an indicator on word boundaries.

    Plain substring matching fires inside unrelated words (``bol`` in
    ``symbol``, ``inv`` in ``inventory``, ``qc`` in random tokens), which
    inflates scores and misclassifies documents. Anchoring on ``\\b`` keeps
    short tokens and multi-word phrases matching whole words only.
    """
    return re.search(r"\b" + re.escape(indicator) + r"\b", text_lower) is not None


class DocumentClassificationMixin:
    """Pass 1: document type classification and FTL category scoping."""

    def _classify_document(self, text: str) -> Tuple[DocumentType, Optional[str]]:
        """Classify document type based on content indicators.

        Returns a tuple-compatible result. On a tie between two or more
        document types, returns UNKNOWN and a warning string so callers can
        surface the ambiguity in ``result.warnings`` (#1288).
        """
        text_lower = text.lower()

        scores = {}
        for doc_type, indicators in self.DOC_TYPE_INDICATORS.items():
            score = sum(1 for ind in indicators if _indicator_present(text_lower, ind))
            scores[doc_type] = score

        max_score = max(scores.values())
        if max_score == 0:
            return _ClassificationResult(DocumentType.UNKNOWN, None)

        top_types = [dt for dt, sc in scores.items() if sc == max_score]
        if len(top_types) > 1:
            tie_warning = "Document type could not be determined from ambiguous CTE indicators"
            logger.warning(
                "ambiguous_document_type_tie",
                message=tie_warning,
                tied_types=[dt.value for dt in top_types],
                score=max_score,
            )
            return _ClassificationResult(DocumentType.UNKNOWN, tie_warning)

        return _ClassificationResult(top_types[0], None)

    def _classify_ftl(self, product_description: Optional[str]) -> Tuple[Optional[bool], Optional[str]]:
        """Classify a free-text product description against the FDA FTL.

        Returns ``(is_ftl_covered, ftl_category)``:

          - ``(True, category)``  — product matches an FTL category; the
            matching category name is returned for downstream consumers.
          - ``(False, None)``     — a non-empty description was supplied
            but no FTL category matched. Treat as non-FTL and route
            accordingly (#1116).
          - ``(None, None)``      — no description supplied, or the FTL
            catalog import failed. Caller should surface as a
            classification gap, not a compliance verdict (#1346).
        """
        if not product_description or not product_description.strip():
            return None, None
        if not FTL_CATEGORIES:
            return None, None
        desc = product_description.lower()
        # Match is substring-based so "fresh romaine lettuce" maps to
        # "leafy greens" via the rules catalog's entries. Order is
        # deterministic (sorted) so unit tests are stable.
        for category in sorted(FTL_CATEGORIES):
            # Each catalog category is already lower-cased.
            for token in category.split():
                # Avoid spurious single-letter matches by requiring
                # tokens of at least 4 chars. Still handles "nuts" /
                # "eggs" / "fish" but excludes unhelpful prefixes.
                if len(token) < 4:
                    continue
                if token in desc:
                    return True, category
        return False, None
