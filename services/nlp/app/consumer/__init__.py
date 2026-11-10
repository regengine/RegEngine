"""NLP extraction helpers shared by the PostgreSQL task path.

This package began as the NLP Kafka consumer. The consumer loop, the Kafka
runner, the dead-letter producers and the liveness probe were retired on
2026-11-04 (tech-debt work item WI-05) and now live under
``docs/archive/retired-topology/kafka/services/nlp/app/consumer/``. What
remains is the extraction logic that the pg backbone still runs from
``server/workers/task_processor.py``:

- ``constants``          — producer identity, routing labels, confidence caps
- ``tenancy``            — tenant resolution from a signed payload
- ``conversion``         — legacy entity → ExtractionPayload conversion
- ``thresholds``         — live confidence thresholds + CONFIDENCE_THRESHOLD proxy
- ``schema_validation``  — JSON-schema loading + eager inbound validator
- ``review_routing``     — review-reason codes for the HITL queue
- ``events``             — FSMA-event detection (FTL flags + URL heuristic)

The extractor wiring (feature flags + lazy getters) stays here because
``importlib.reload(services.nlp.app.consumer)`` must re-read the
``NLP_ENABLE_*`` env flags (test_extractor_wiring.py) and tests patch
``_get_fsma_extractor`` / ``_get_llm_extractor`` on this module.
"""

from __future__ import annotations

import os
from typing import Optional

import structlog

from ..extractors import FSMAExtractor, LLMGenerativeExtractor

# ---------------------------------------------------------------------------
# Re-exports from the package submodules. Every name below was importable
# from ``app.consumer`` before the split and still is.
# ---------------------------------------------------------------------------
from .constants import (
    MAX_RETRIES,
    NLP_PRODUCER_SERVICE,
    TOPIC_DLQ,
    TOPIC_FSMA_DLQ,
    TOPIC_GRAPH_UPDATE,
    TOPIC_NEEDS_REVIEW,
    _LEGACY_HEURISTIC_CONFIDENCE_CAP,
    _LLM_EXTRACTION_CONFIDENCE_CAP,
)
from .conversion import (
    CLASSIFIER,
    RESOLVER,
    _convert_entities_to_extraction,
    _convert_llm_results_to_extractions,
    _now_iso,
    _score_regulatory_date,
)
from .events import _collect_ftl_flags, _is_fsma_event
from .review_routing import _build_review_reasons
from .schema_validation import (
    _INBOUND_VALIDATOR,
    _load_inbound_schema,
    _load_schema,
)
from .tenancy import _kafka_key_for, _resolve_tenant_id, _retry_key_for
from .thresholds import CONFIDENCE_THRESHOLD, _ThresholdProxy, _current_thresholds

__all__ = [
    "CLASSIFIER",
    "CONFIDENCE_THRESHOLD",
    "FSMAExtractor",
    "LLMGenerativeExtractor",
    "MAX_RETRIES",
    "NLP_ENABLE_FSMA_EXTRACTOR",
    "NLP_ENABLE_LLM_EXTRACTOR",
    "NLP_PRODUCER_SERVICE",
    "RESOLVER",
    "TOPIC_DLQ",
    "TOPIC_FSMA_DLQ",
    "TOPIC_GRAPH_UPDATE",
    "TOPIC_NEEDS_REVIEW",
    "_INBOUND_VALIDATOR",
    "_LEGACY_HEURISTIC_CONFIDENCE_CAP",
    "_LLM_EXTRACTION_CONFIDENCE_CAP",
    "_ThresholdProxy",
    "_build_review_reasons",
    "_collect_ftl_flags",
    "_convert_entities_to_extraction",
    "_convert_llm_results_to_extractions",
    "_current_thresholds",
    "_get_fsma_extractor",
    "_get_llm_extractor",
    "_is_fsma_event",
    "_kafka_key_for",
    "_load_inbound_schema",
    "_load_schema",
    "_now_iso",
    "_resolve_tenant_id",
    "_retry_key_for",
    "_run_llm_extractor",
    "_score_regulatory_date",
]

logger = structlog.get_logger("nlp-consumer")


# ---------------------------------------------------------------------------
# Structured extractor wiring (#1194)
# ---------------------------------------------------------------------------
#
# Two feature flags control activation so deployments can roll out carefully:
#
#   NLP_ENABLE_FSMA_EXTRACTOR (default true)
#     When on, every document passes through FSMAExtractor before the
#     legacy regex extractor. CTEs with both TLC and Event Date are
#     auto-approved; everything else goes to human-in-the-loop review.
#
#   NLP_ENABLE_LLM_EXTRACTOR (default false)
#     Opt-in — LLM inference has per-token cost and higher latency.
#     When on, documents that produce zero high-confidence FSMA CTEs
#     get an LLM pass as fallback. Results augment (do not replace)
#     the regex-based ExtractionPayload stream.
#
# The legacy regex extractor (extract_entities) remains live as a backstop.
NLP_ENABLE_FSMA_EXTRACTOR = os.getenv("NLP_ENABLE_FSMA_EXTRACTOR", "true").lower() in (
    "true", "1", "yes", "on",
)
NLP_ENABLE_LLM_EXTRACTOR = os.getenv("NLP_ENABLE_LLM_EXTRACTOR", "false").lower() in (
    "true", "1", "yes", "on",
)

# Instantiate extractors lazily on first use so test imports don't pay
# the model-download cost and so flag flips at runtime are honored
# (flags are read once at module load — restarts pick up new values).
_FSMA_EXTRACTOR: Optional[FSMAExtractor] = None
_LLM_EXTRACTOR: Optional[LLMGenerativeExtractor] = None


def _get_fsma_extractor() -> FSMAExtractor:
    global _FSMA_EXTRACTOR
    if _FSMA_EXTRACTOR is None:
        _FSMA_EXTRACTOR = FSMAExtractor()
    return _FSMA_EXTRACTOR


def _get_llm_extractor() -> LLMGenerativeExtractor:
    global _LLM_EXTRACTOR
    if _LLM_EXTRACTOR is None:
        _LLM_EXTRACTOR = LLMGenerativeExtractor()
    return _LLM_EXTRACTOR


def _run_llm_extractor(
    text: str,
    doc_id: str,
    jurisdiction: str,
) -> list:
    """Run LLMGenerativeExtractor; return its structured results."""
    try:
        extractor = _get_llm_extractor()
        return extractor.extract(
            text=text,
            jurisdiction=jurisdiction,
            correlation_id=doc_id,
        )
    except Exception as exc:
        logger.exception(
            "llm_extractor_error",
            document_id=doc_id,
            error=str(exc),
        )
        return []
