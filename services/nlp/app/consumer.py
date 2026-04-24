from __future__ import annotations

import json
import os
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def _env_flag(name: str, default: bool = False) -> bool:
    """Parse a boolean env flag ('1', 'true', 'yes' = True)."""

    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}

import structlog
from jsonschema import Draft7Validator, ValidationError
from confluent_kafka.admin import NewTopic
from shared.kafka_compat import (
    KafkaAdminClientCompat as KafkaAdminClient,
    KafkaConsumerCompat as KafkaConsumer,
    KafkaProducerCompat as KafkaProducer,
    KafkaTimeoutError,
    TopicAlreadyExistsError,
)
from opentelemetry import trace, propagate
from prometheus_client import Counter
from structlog.contextvars import get_contextvars

from pathlib import Path
import sys

# Standardized path discovery via shared utility
from shared.paths import ensure_shared_importable
ensure_shared_importable()

from shared.schemas import (
    ExtractionPayload,
    GraphEvent,
    ObligationType,
    ReviewItem,
    Threshold,
)
from shared.observability.kafka_propagation import (
    bind_correlation_context,
    extract_correlation_headers,
    inject_correlation_headers_tuples,
)
from shared.kafka_auth import (
    KafkaAuthError,
    get_allowed_producers,
    sign_event,
    verify_event,
)

# Producer service identity used when this consumer re-emits events to
# downstream topics (graph.update, nlp.needs_review, nlp.extracted).
# Must match the value the downstream consumer expects in its
# KAFKA_ALLOWED_PRODUCERS_<TOPIC> env var (#1078).
NLP_PRODUCER_SERVICE = "nlp-service"

from .classification import SignalClassifier
from .config import settings
from .extractor import extract_entities
from .extractors import FSMAExtractor, LLMGenerativeExtractor
from .extractors.fsma_types import (
    TOPIC_GRAPH_UPDATE as FSMA_TOPIC_GRAPH_UPDATE,
    TOPIC_NEEDS_REVIEW as FSMA_TOPIC_NEEDS_REVIEW,
)
from .resolution import EntityResolver
from .s3_loader import parse_s3_uri
from .s3_utils import get_bytes
from shared.url_validation import PathTraversalError

logger = structlog.get_logger("nlp-consumer")
_audit_logger = structlog.get_logger("nlp-consumer-audit")


# ---------------------------------------------------------------------------
# Structured extractor wiring (#1194)
# ---------------------------------------------------------------------------
#
# Until this wiring landed, FSMAExtractor and LLMGenerativeExtractor were
# imported but never instantiated from the consumer loop. All KDE-gating —
# the core reason the FSMAExtractor exists — was therefore bypassed for
# every inbound document, which meant FSMA 204 documents silently fell
# through to the regex-only pipeline and skipped the HITL gate.
#
# Two feature flags control activation so we can deploy carefully:
#
#   NLP_ENABLE_FSMA_EXTRACTOR (default true)
#     When on, every document passes through FSMAExtractor before the
#     legacy regex extractor. CTEs with both TLC and Event Date are
#     routed to ``graph.update``; everything else is routed to
#     ``nlp.needs_review`` for human-in-the-loop review.
#
#   NLP_ENABLE_LLM_EXTRACTOR (default false)
#     Opt-in — LLM inference has per-token cost and higher latency.
#     When on, documents that produce zero high-confidence FSMA CTEs
#     get an LLM pass as fallback. Results augment (do not replace)
#     the regex-based ExtractionPayload stream.
#
# The legacy regex extractor (extract_entities) remains live as a
# backstop so existing consumers continue to observe nlp.extracted
# events.
NLP_ENABLE_FSMA_EXTRACTOR = os.getenv("NLP_ENABLE_FSMA_EXTRACTOR", "true").lower() in (
    "true", "1", "yes", "on",
)
NLP_ENABLE_LLM_EXTRACTOR = os.getenv("NLP_ENABLE_LLM_EXTRACTOR", "false").lower() in (
    "true", "1", "yes", "on",
)

# Instantiate extractors lazily on first use so test imports don't pay
# the model-download cost and so flag flips at runtime are honored
# (flags are read once at module load — restarts of the consumer pick
# up new values).
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


def _resolve_tenant_id(
    header_tenant_id: Optional[str],
    payload_tenant_id: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    """Determine the authoritative tenant_id for an inbound NLP message (#1176).

    Priority:

    * **Kafka header ``X-RegEngine-Tenant-ID``** — set by an authenticated
      producer via ``inject_correlation_headers``. Trusted because the
      producer is inside a request handler that already ran auth.
    * **Payload ``tenant_id`` field** — legacy path. Lower trust: may have
      been user-controllable at an earlier stage.

    Validation:

    * Must be a well-formed UUID. ``"default"``, empty string, and other
      sentinel values are rejected (they were the root cause of #1268-style
      bypasses).
    * If header AND payload both present and **disagree**, the message is
      treated as hostile (someone's trying to smuggle into another tenant)
      and rejected to the FSMA DLQ.

    Returns ``(resolved_tenant_id, rejection_reason)``. ``resolved`` is the
    validated UUID string when the message should be processed. When
    ``resolved`` is ``None``, ``rejection_reason`` explains why and the
    caller **must** route the message to the DLQ — the consumer **must
    not** continue processing messages without a valid tenant.
    """
    header_tid = str(header_tenant_id).strip() if header_tenant_id else None
    payload_tid = str(payload_tenant_id).strip() if payload_tenant_id else None
    # Treat empty / sentinel strings as absent so they can't satisfy the
    # "present" check further down.
    if not header_tid:
        header_tid = None
    if not payload_tid or payload_tid.lower() in {"default", "none", "null"}:
        payload_tid = None

    # Both missing → producer didn't set tenant context. Fail-fast.
    if not header_tid and not payload_tid:
        return None, "no_tenant_id_in_header_or_payload"

    # Both present but disagree → hostile or broken producer. Reject.
    # Case-insensitive compare because UUIDs are case-insensitive per RFC4122.
    if (
        header_tid
        and payload_tid
        and header_tid.lower() != payload_tid.lower()
    ):
        return None, (
            f"tenant_id_mismatch header={header_tid!r} payload={payload_tid!r}"
        )

    # Prefer the header when present (higher-trust source).
    resolved = header_tid or payload_tid

    # Must be a valid UUID — rejects the "default" sentinel from #1268 and
    # any other non-UUID string that somehow made it past the producer.
    try:
        uuid.UUID(resolved)  # type: ignore[arg-type]
    except (ValueError, AttributeError, TypeError):
        return None, f"invalid_tenant_id_format value={resolved!r}"

    return resolved, None


def _kafka_key_for(tenant_id: Optional[str], doc_id: str) -> str:
    """Build the tenant-scoped Kafka partition key (#1122).

    Format: ``"{tenant_id}:{doc_id}"``. This is used for every
    outbound producer.send() in the NLP consumer so that two
    different tenants publishing documents with identical doc_ids
    cannot:

    * Interleave on the same partition (downstream consumers see
      cross-tenant events ordered by offset with no way to tell
      them apart by key alone).
    * Share a retry-count bucket in :data:`_retry_counts` — that
      cache key used to be the raw doc_id, which meant tenant A's
      3rd retry DLQ'd tenant B's first attempt.

    If ``tenant_id`` is falsy (which should never happen at this
    point — the consumer loop DLQ'd well before this call), we
    still emit a safe sentinel that is GUARANTEED not to match a
    legitimate key, so the message hits the DLQ deterministically
    instead of silently joining tenant A's partition.
    """
    safe_tenant = str(tenant_id).strip() if tenant_id else "NO_TENANT"
    return f"{safe_tenant}:{doc_id}"


def _retry_key_for(tenant_id: Optional[str], doc_id: str) -> str:
    """Build the tenant-scoped ``_retry_counts`` cache key (#1122).

    Before this fix the cache was keyed by raw ``doc_id``, which meant
    that two tenants who happened to emit messages carrying the same
    ``doc_id`` shared a retry bucket. Tenant B's first processing
    attempt could trigger tenant A's DLQ threshold and vice versa.
    This helper centralizes the format so every read and write stays
    in sync — a future refactor that changes the key scheme only
    needs to touch this one function.
    """
    safe_tenant = str(tenant_id).strip() if tenant_id else "NO_TENANT"
    return f"{safe_tenant}:{doc_id}"


def _run_fsma_extractor(
    text: str,
    doc_id: str,
    doc_hash: str,
    producer: KafkaProducer,
    tenant_id: str,
    kafka_headers: list,
) -> dict:
    """
    Run FSMAExtractor and route results to the appropriate Kafka topic.

    ``tenant_id`` is required (#1122) — the extractor and the Kafka key
    both need it, and the consumer-loop caller has already validated
    tenant resolution before we land here. Passing a falsy tenant_id
    indicates a caller bug and raises before any downstream state
    changes.

    Returns a summary dict with counts so the caller can emit a single
    structured log line.
    """
    if not tenant_id:
        # Defense in depth — the caller should have DLQ'd before reaching
        # this function. Surface as an error rather than silently emit.
        logger.error(
            "fsma_extractor_invoked_without_tenant",
            document_id=doc_id,
        )
        return {"status": "error", "cte_count": 0, "routed": None}
    extractor = _get_fsma_extractor()
    try:
        result = extractor.extract(text, doc_id, tenant_id=tenant_id)
    except Exception as exc:
        logger.exception(
            "fsma_extractor_error",
            document_id=doc_id,
            tenant_id=tenant_id,
            error=str(exc),
        )
        return {"status": "error", "cte_count": 0, "routed": None}

    routing = extractor.route_extraction(result)
    topic = routing["topic"]
    payload = {
        "tenant_id": tenant_id,
        "doc_hash": doc_hash,
        **routing["payload"],
    }
    # Sign the event so downstream consumers (graph, review UI) can
    # verify it came from this service and refuse forgeries (#1078).
    try:
        signed_payload, signed_headers = sign_event(
            payload,
            producer_service=NLP_PRODUCER_SERVICE,
            existing_headers=kafka_headers,
        )
    except KafkaAuthError as sign_exc:
        logger.error(
            "fsma_routing_sign_failed",
            document_id=doc_id,
            topic=topic,
            reason=sign_exc.reason,
        )
        return {"status": "error", "cte_count": len(result.ctes), "routed": topic}
    try:
        producer.send(
            topic,
            # #1122 — tenant-scoped partition key ensures two tenants
            # with the same doc_id cannot interleave on the same
            # partition. Prior format ``doc_id`` made cross-tenant
            # ordering collisions silently possible.
            key=_kafka_key_for(tenant_id, doc_id),
            value=signed_payload,
            headers=signed_headers,
        )
        producer.flush(timeout=1.0)
    except (KafkaTimeoutError, ConnectionError, OSError) as exc:
        logger.error(
            "fsma_routing_failed",
            document_id=doc_id,
            topic=topic,
            error=str(exc),
        )
        return {"status": "error", "cte_count": len(result.ctes), "routed": topic}

    logger.info(
        "fsma_extractor_routed",
        document_id=doc_id,
        cte_count=len(result.ctes),
        review_required=result.review_required,
        topic=topic,
    )
    return {
        "status": "ok",
        "cte_count": len(result.ctes),
        "review_required": result.review_required,
        "routed": topic,
        "high_confidence": topic == FSMA_TOPIC_GRAPH_UPDATE,
    }


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

try:
    MESSAGES_COUNTER = Counter("nlp_messages_total", "NLP messages processed", ["status"])
    POISON_PILL_COUNTER = Counter("nlp_poison_pill_total", "Count of malformed Kafka messages")
    # #1176 — surface tenant-resolution outcomes so SRE can spot a
    # spike in messages missing tenant context (producer regression)
    # or with mismatched header vs payload (injection attempt).
    TENANT_RESOLUTION_COUNTER = Counter(
        "nlp_tenant_resolution_total",
        "NLP per-message tenant resolution outcome",
        ["outcome"],
    )
except ValueError:
    # Metric already registered (happens during test re-imports)
    from prometheus_client import REGISTRY
    MESSAGES_COUNTER = REGISTRY._names_to_collectors.get("nlp_messages_total")
    POISON_PILL_COUNTER = REGISTRY._names_to_collectors.get("nlp_poison_pill_total")
    TENANT_RESOLUTION_COUNTER = REGISTRY._names_to_collectors.get(
        "nlp_tenant_resolution_total"
    )

_shutdown_event = threading.Event()

# NOTE: Confidence thresholds are read live from `settings` inside
# ``_route_extraction`` (see issue #1260). A module-level constant captured at
# import time would silently desync from ``config.py`` if settings loading fails
# or if operators rotate env vars at runtime. Always call
# ``_current_thresholds()`` instead.


def _current_thresholds() -> tuple[float, float]:
    """Return the live (high, medium) confidence thresholds from settings.

    Reading per-call (rather than snapshotting at import) ensures:
    - A silent settings-load failure surfaces as a configuration error in logs,
      not a 0.85 fallback that disagrees with the 0.95 production default.
    - Operators can rotate thresholds by restarting the process (or in future,
      via a TTL cache) without editing source constants.
    """

    high_default = 0.95  # Must match config.py extraction_confidence_high default
    medium_default = 0.85  # Must match config.py extraction_confidence_medium default
    if settings is None:
        logger.warning(
            "confidence_thresholds_using_fallback",
            reason="settings_none",
            high=high_default,
            medium=medium_default,
        )
        return high_default, medium_default
    high = getattr(settings, "extraction_confidence_high", high_default)
    medium = getattr(settings, "extraction_confidence_medium", medium_default)
    return float(high), float(medium)


class _ThresholdProxy:
    """Shim that preserves the import name ``CONFIDENCE_THRESHOLD`` while
    still reading the threshold live (#1260).

    Callers that do numeric comparisons (``extraction.confidence_score >=
    CONFIDENCE_THRESHOLD``) see the current value each time because arithmetic
    ops call ``__float__`` / ``__ge__``. Callers that read it as a module
    attribute (``from ... import CONFIDENCE_THRESHOLD``) see the live value via
    ``__float__`` at comparison time. Binding to a name (``x =
    CONFIDENCE_THRESHOLD``) then comparing still works because Python evaluates
    ``__ge__`` with this object as the operand.
    """

    def _value(self) -> float:
        return _current_thresholds()[0]

    def __float__(self) -> float:
        return self._value()

    def __repr__(self) -> str:
        return f"{self._value()}"

    def __eq__(self, other: object) -> bool:
        try:
            return float(other) == self._value()
        except (TypeError, ValueError):
            return NotImplemented

    def __ne__(self, other: object) -> bool:
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    def __lt__(self, other: object) -> bool:
        return self._value() < float(other)

    def __le__(self, other: object) -> bool:
        return self._value() <= float(other)

    def __gt__(self, other: object) -> bool:
        return self._value() > float(other)

    def __ge__(self, other: object) -> bool:
        return self._value() >= float(other)

    def __hash__(self) -> int:
        return hash(self._value())


# Backward-compatible export for tests & legacy callers — live-read (#1260).
CONFIDENCE_THRESHOLD = _ThresholdProxy()

# Topic names for routing
TOPIC_GRAPH_UPDATE = "graph.update"
TOPIC_NEEDS_REVIEW = "nlp.needs_review"
TOPIC_DLQ = "nlp.extracted.dlq"
TOPIC_FSMA_DLQ = "fsma.dead_letter"

# Legacy ``nlp.extracted`` topic feature flag (#1218).
# The legacy publish sent the raw ``entities`` list with no confidence filtering,
# defeating the gating at the ``graph.update`` / ``nlp.needs_review`` boundary.
# Default: OFF. Any operator who flips this on MUST accept that downstream
# subscribers see ungated data.
EMIT_LEGACY_EXTRACTED_TOPIC = _env_flag("NLP_EMIT_LEGACY_TOPIC", default=False)

# Max retries before sending to DLQ
MAX_RETRIES = 3
# Bounded retry tracker — TTL prevents unbounded growth under partial failures (#994)
try:
    from cachetools import TTLCache
    _retry_counts: dict[str, int] = TTLCache(maxsize=50_000, ttl=3600)  # type: ignore[assignment]
except ImportError:
    _retry_counts: dict[str, int] = {}  # type: ignore[no-redef]

RESOLVER = EntityResolver()
CLASSIFIER = SignalClassifier()


def _now_iso() -> str:
    # Match the `Z` suffix contract enforced by the FSMA extractor
    # (see `app/extractors/fsma_extractor.py`) so all NLP-service timestamps
    # share a single UTC serialization. Python's default `isoformat()` emits
    # `+00:00`, which breaks downstream consumers that expect `Z`. -- #1132
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# Heuristic confidence cap for the legacy regex path (#1202).
# The regex pipeline has no calibrated model — every confidence score is an
# invented number. Cap it below the auto-approval gate so nothing from this path
# can bypass HITL. Only the FSMA extractor (calibrated from KDE completeness)
# may exceed this ceiling.
_LEGACY_HEURISTIC_CONFIDENCE_CAP = 0.60


def _convert_entities_to_extraction(
    entities: list, doc_id: str, source_url: str
) -> list[ExtractionPayload]:
    """Convert legacy entity format to canonical ExtractionPayload format.

    Confidence scores from this path are capped at
    :data:`_LEGACY_HEURISTIC_CONFIDENCE_CAP` (#1202) so routed extractions
    cannot clear the auto-approval gate; they always enter HITL.
    """

    extractions = []

    # Group entities to form complete extractions
    obligations = [e for e in entities if e.get("type") == "OBLIGATION"]
    thresholds = [e for e in entities if e.get("type") == "THRESHOLD"]
    jurisdictions = [e for e in entities if e.get("type") == "JURISDICTION"]

    for obl in obligations:
        text = obl.get("text", "")
        start_offset = obl.get("start", 0)

        # Simple subject/action parsing from text
        parts = text.split()
        subject = " ".join(parts[: min(3, len(parts))])
        action_words = ["shall", "must", "required to", "has to", "should", "may"]
        action = next((w for w in action_words if w in text.lower()), "must")

        # Determine obligation type with negation and modality detection (#1299).
        #
        # Negation detection: if a matched keyword is immediately preceded by
        # a negation token ("not", "no", "never", "without") within 3 tokens,
        # the match is skipped — "must not report" should NOT infer MANDATORY.
        # We tokenise on whitespace and check the 3 tokens before the keyword.
        #
        # Modality detection:
        #   MANDATORY  ← "must", "shall", "required"
        #   RECOMMENDED ← "may", "should"
        # We use ObligationType.MUST for MANDATORY and ObligationType.SHOULD for
        # RECOMMENDED; ObligationType.MAY maps to the weakest recommendation.
        _NEGATION_TOKENS = {"not", "no", "never", "without"}

        def _keyword_is_negated(full_text: str, keyword: str) -> bool:
            """Return True if ``keyword`` appears preceded by a negation token
            within 3 whitespace-delimited tokens in ``full_text``."""
            tokens = full_text.lower().split()
            for idx, tok in enumerate(tokens):
                # Strip punctuation from token for comparison.
                clean_tok = tok.strip(".,;:()[]\"'")
                if clean_tok == keyword:
                    preceding = tokens[max(0, idx - 3): idx]
                    preceding_clean = {t.strip(".,;:()[]\"'") for t in preceding}
                    if preceding_clean & _NEGATION_TOKENS:
                        return True
            return False

        text_lower = text.lower()

        # MANDATORY keywords — "must", "shall", "required", "mandatory" (#1299)
        _MANDATORY_KEYWORDS = ["must", "shall", "required", "mandatory"]
        # RECOMMENDED keywords — "may", "should", "can", "recommend" (#1299)
        _RECOMMENDED_KEYWORDS = ["should", "can", "may", "recommend"]

        obl_type = None
        # Check MANDATORY first (higher precedence).
        for kw in _MANDATORY_KEYWORDS:
            if kw in text_lower and not _keyword_is_negated(text, kw):
                obl_type = ObligationType.MUST
                break

        if obl_type is None:
            for kw in _RECOMMENDED_KEYWORDS:
                if kw in text_lower and not _keyword_is_negated(text, kw):
                    # "should"/"can"/"recommend" → RECOMMENDED (SHOULD);
                    # "may" → weakest recommendation (MAY).
                    obl_type = ObligationType.MAY if kw == "may" else ObligationType.SHOULD
                    break

        if obl_type is None:
            # Default when no keyword matched or all were negated.
            obl_type = ObligationType.MUST

        # Find associated thresholds (within proximity)
        associated_thresholds = []
        for thresh in thresholds:
            if abs(thresh.get("start", 0) - start_offset) < 200:
                attrs = thresh.get("attrs", {})
                threshold = Threshold(
                    value=attrs.get("value", 0),
                    unit=attrs.get("unit_normalized", "units"),
                    operator="gte",  # Default operator
                    context=None,
                )
                associated_thresholds.append(threshold)

        # Find jurisdiction
        jurisdiction = None
        for jur in jurisdictions:
            if abs(jur.get("start", 0) - start_offset) < 500:
                jurisdiction = jur.get("attrs", {}).get("name")
                break

        # Heuristic confidence — capped below auto-approval gate (#1202).
        # Every weight here is an uncalibrated guess; the cap ensures this path
        # can never auto-approve, regardless of magic-number drift.
        base_confidence = 0.55
        if associated_thresholds:
            base_confidence += 0.03
        if jurisdiction:
            base_confidence += 0.02
        if len(text) > 50:
            base_confidence += 0.02

        # Check for related Organizations and resolve them. Entity resolution
        # is recorded but does NOT boost confidence (#1269 — substring
        # matching previously let an attacker launder confidence with
        # lookalike names).
        organizations = [e for e in entities if e.get("type") == "ORGANIZATION"]
        resolved_entities = []
        for org in organizations:
            # Proximity check
            if abs(org.get("start", 0) - start_offset) < 500:
                raw_name = org.get("attrs", {}).get("name")
                resolution = RESOLVER.resolve_organization(raw_name)

                entity_info = {
                    "raw_name": raw_name,
                    "type": "ORGANIZATION",
                    "start": org.get("start"),
                    "end": org.get("end"),
                }

                if resolution:
                    entity_info["entity_id"] = resolution["id"]
                    entity_info["normalized_name"] = resolution["name"]
                    entity_info["entity_type"] = resolution["type"]
                    entity_info["match_strategy"] = resolution.get(
                        "match_strategy", "unknown"
                    )
                    entity_info["match_score"] = resolution.get("match_score")

                resolved_entities.append(entity_info)

        # Apply cap BEFORE emitting so downstream cannot see >0.60
        confidence = min(base_confidence, _LEGACY_HEURISTIC_CONFIDENCE_CAP)

        # Categorize Signal
        category, risk, risk_conf = CLASSIFIER.classify_signal(text)

        attributes = {
            "document_id": doc_id,
            "source_url": source_url,
            "signal_category": category,
            "risk_level": risk,
            "extractor": "legacy_regex_v1",
            "confidence_capped_at": _LEGACY_HEURISTIC_CONFIDENCE_CAP,
        }
        if resolved_entities:
            attributes["resolved_entities"] = resolved_entities

        extraction = ExtractionPayload(
            subject=subject,
            action=action,
            object=None,
            obligation_type=obl_type,
            thresholds=associated_thresholds,
            jurisdiction=jurisdiction,
            confidence_score=confidence,
            source_text=text,
            source_offset=start_offset,
            attributes=attributes,
        )
        extractions.append(extraction)

    # Handle FSMA Regulatory Dates (#1206): no more 0.99 hardcode.
    # Score based on regex-group quality signals; route to HITL below the
    # medium threshold by default so a supplier-controlled date cannot
    # auto-approve into the calendar.
    reg_dates = [e for e in entities if e.get("type") == "REGULATORY_DATE"]
    for rd in reg_dates:
        attrs = rd.get("attrs", {})
        date_value = attrs.get("value")
        date_text = rd.get("text", "")

        reg_date_confidence = _score_regulatory_date(date_value, attrs)

        extraction = ExtractionPayload(
            subject="covered entities",
            action="must comply by",
            object="FSMA 204 requirements",
            obligation_type=ObligationType.MUST,
            effective_date=date_value,
            confidence_score=reg_date_confidence,
            source_text=date_text,
            source_offset=rd.get("start", 0),
            attributes={
                "document_id": doc_id,
                "source_url": source_url,
                "fact_type": "compliance_date",
                "provenance": attrs.get("provenance"),
                "signal_category": "regulatory_change",
                "risk_level": "high",
                "entities": [rd],
                "extractor": "regulatory_date_regex_v2",
                "context_window_chars": attrs.get("context_distance"),
            },
        )
        extractions.append(extraction)

    return extractions


def _score_regulatory_date(date_value: Optional[str], attrs: dict) -> float:
    """Score a REGULATORY_DATE match by signal quality (#1206).

    Previously hardcoded to 0.99, letting adversarial documents auto-approve
    regulatory-date changes. Now the score reflects ISO parseability,
    proximity to the 'compliance'/'enforcement' cue, and whether the source
    provenance is from trusted metadata.

    All scores are capped at :data:`_LEGACY_HEURISTIC_CONFIDENCE_CAP` —
    regulatory dates must go through HITL regardless of regex quality because
    of their high compliance impact.
    """

    # Start low; each positive signal contributes.
    score = 0.30

    # Signal: date is ISO-parseable
    if date_value:
        try:
            from datetime import datetime as _dt

            # Try several common formats
            parsed = None
            for fmt in ("%B %d, %Y", "%Y-%m-%d", "%m/%d/%Y"):
                try:
                    parsed = _dt.strptime(date_value, fmt)
                    break
                except ValueError:
                    continue
            if parsed is not None:
                score += 0.10
                # Signal: date is within a plausible range for FSMA compliance
                if 2020 <= parsed.year <= 2040:
                    score += 0.05
        except (TypeError, ValueError):
            pass

    # Signal: narrow context match (within 20 chars vs previously 100)
    ctx_dist = attrs.get("context_distance")
    if isinstance(ctx_dist, (int, float)) and ctx_dist < 20:
        score += 0.05

    # Signal: trusted provenance tag
    if attrs.get("provenance") in {"FSMA Rule Text", "FDA Official Publication"}:
        score += 0.05

    # Cap: even "perfect" regex matches never auto-approve regulatory dates.
    return min(score, _LEGACY_HEURISTIC_CONFIDENCE_CAP)


def _load_schema() -> Draft7Validator:
    """Load JSON schema using standardized project path discovery."""
    from shared.paths import project_root

    repo_root = project_root()
    schema_path = repo_root / "data-schemas" / "events" / "nlp.extracted.schema.json"

    if not schema_path.exists():
        logger.error("schema_not_found", path=str(schema_path))
        raise FileNotFoundError(f"Could not find schema at {schema_path}")

    schema = json.loads(schema_path.read_text())
    return Draft7Validator(schema)


def _load_inbound_schema() -> Draft7Validator:
    """Load inbound event schema for validating Kafka messages from ingestion.

    Addresses OWASP API10:2023 — Unsafe Consumption of APIs.
    """
    from shared.paths import project_root

    repo_root = project_root()
    schema_path = repo_root / "data-schemas" / "events" / "ingest.normalized.schema.json"

    if not schema_path.exists():
        logger.error("inbound_schema_not_found", path=str(schema_path))
        raise FileNotFoundError(f"Could not find inbound schema at {schema_path}")

    schema = json.loads(schema_path.read_text())
    return Draft7Validator(schema)


# Eagerly load inbound schema at module level so validation is fast per-message
try:
    _INBOUND_VALIDATOR = _load_inbound_schema()
except (FileNotFoundError, json.JSONDecodeError) as _schema_err:
    logger.error("inbound_schema_load_failed", error=str(_schema_err))
    _INBOUND_VALIDATOR = None


def _ensure_topic(topic: str) -> None:
    admin = None
    try:
        admin = KafkaAdminClient(bootstrap_servers=settings.kafka_bootstrap)
        admin.create_topics([NewTopic(topic, num_partitions=1, replication_factor=1)])
    except TopicAlreadyExistsError:
        pass
    except (ConnectionError, TimeoutError, RuntimeError, OSError) as exc:  # pragma: no cover - infra dependent
        logger.warning("topic_creation_failed", topic=topic, error=str(exc))
    finally:
        if admin is not None:
            try:
                admin.close()
            except (RuntimeError, OSError):  # pragma: no cover
                pass


def _build_review_reasons(extraction: ExtractionPayload, tier: str) -> list[dict]:
    """Build structured review-reason codes for the ReviewItem envelope (#1368).

    Reviewers need to know WHY an item landed in the queue, not just its raw
    confidence. Each reason is a ``{reason_code, description, severity}`` tuple
    that the UI can surface and analytics can aggregate.
    """

    reasons: list[dict] = []
    reasons.append(
        {
            "reason_code": f"confidence_tier_{tier}",
            "description": (
                f"Extraction confidence {extraction.confidence_score:.2f} "
                f"falls in the {tier} tier"
            ),
            "severity": "info" if tier == "medium" else "warning",
        }
    )
    attributes = extraction.attributes or {}
    if attributes.get("hallucination_demoted"):
        reasons.append(
            {
                "reason_code": "hallucination_demoted",
                "description": "LLM output contained text not found in source document",
                "severity": "error",
            }
        )
    if attributes.get("fact_type") == "compliance_date":
        reasons.append(
            {
                "reason_code": "regulatory_date_needs_review",
                "description": (
                    "Regulatory date extractions are high-impact and default to HITL"
                ),
                "severity": "warning",
            }
        )
    if not extraction.source_text:
        reasons.append(
            {
                "reason_code": "missing_source_span",
                "description": "Extraction missing provenance span (source_text empty)",
                "severity": "error",
            }
        )
    return reasons


def _route_extraction(
    extraction: ExtractionPayload,
    doc_id: str,
    doc_hash: str,
    source_url: str,
    producer: KafkaProducer,
    tenant_id: Optional[str],
    reviewer_id: str = "nlp_model_v1",
) -> None:
    """Route extraction using a three-tier confidence model (#1258).

    - ``>= high`` (default 0.95): auto-approve to ``graph.update``.
    - ``>= medium`` (default 0.85) and ``< high``: ``nlp.needs_review``
      with ``priority=low`` — reviewer confirms, no re-extraction.
    - ``< medium``: ``nlp.needs_review`` with ``priority=high`` — treat as
      a possible extractor failure, flag for policy review.

    Provenance contract (#1368): every emitted payload carries
    ``source_document_id``, ``source_offset``, and ``confidence`` so the
    KDE→span link survives through Kafka boundaries.
    """

    # Capture correlation id from structured logging context if present
    ctx = get_contextvars()
    request_id = ctx.get("request_id")

    high_threshold, medium_threshold = _current_thresholds()
    confidence = extraction.confidence_score

    # Determine tier
    if confidence >= high_threshold:
        tier = "high"
        priority = None  # N/A for auto-approved
    elif confidence >= medium_threshold:
        tier = "medium"
        priority = "low"
    else:
        tier = "low"
        priority = "high"

    base_headers = [
        ("X-Request-ID", str(request_id or "").encode("utf-8")),
        ("X-Tenant-ID", str(tenant_id or "").encode("utf-8")),
        ("X-Confidence-Tier", tier.encode("utf-8")),
    ]

    if tier == "high":
        # Auto-approved path: straight to graph
        graph_event = GraphEvent(
            event_type="create_provision",
            tenant_id=tenant_id,
            doc_hash=doc_hash,
            document_id=doc_id,
            text_clean=extraction.source_text,
            extraction=extraction,
            provenance={
                "source_url": source_url,
                "offset": extraction.source_offset,
                "source_document_id": doc_id,
                "confidence": confidence,
                "confidence_tier": tier,
                "request_id": request_id,
            },
            embedding=None,
            status="APPROVED",
            reviewer_id=reviewer_id,
        )
        payload = graph_event.model_dump(mode="json")
        logger.info(
            "producing_graph_event",
            entity_count=len(payload.get("extraction", {}).get("entities", [])),
            document_id=doc_id,
        )
        # Sign the event so the graph consumer can verify it came
        # from a trusted producer before routing by tenant_id (#1078).
        signed_payload, signed_headers = sign_event(
            payload,
            producer_service=NLP_PRODUCER_SERVICE,
            existing_headers=base_headers,
        )
        producer.send(
            TOPIC_GRAPH_UPDATE,
            # #1122 — tenant-scoped Kafka key.
            key=_kafka_key_for(tenant_id, doc_id),
            value=signed_payload,
            headers=signed_headers,
        )
        logger.info(
            "high_confidence_extraction",
            document_id=doc_id,
            confidence=confidence,
            tier=tier,
            routed_to="graph",
        )
        return

    # Medium or low tier → review queue with priority + reason codes (#1368)
    reasons = _build_review_reasons(extraction, tier)
    review_payload = {
        "id": None,  # filled downstream on persist
        "tenant_id": str(tenant_id) if tenant_id else None,
        "document_id": doc_id,
        "extraction": extraction.model_dump(mode="json"),
        "status": "pending",
        "priority": priority,
        "confidence_tier": tier,
        "review_reasons": reasons,
        "provenance": {
            "source_url": source_url,
            "source_document_id": doc_id,
            "source_offset": extraction.source_offset,
            "confidence": confidence,
        },
    }
    review_headers = base_headers + [
        ("X-Review-Priority", priority.encode("utf-8")),
    ]
    signed_review_payload, signed_review_headers = sign_event(
        review_payload,
        producer_service=NLP_PRODUCER_SERVICE,
        existing_headers=review_headers,
    )
    producer.send(
        TOPIC_NEEDS_REVIEW,
        # #1122 — tenant-scoped Kafka key.
        key=_kafka_key_for(tenant_id, doc_id),
        value=signed_review_payload,
        headers=signed_review_headers,
    )
    logger.info(
        "low_or_medium_confidence_extraction",
        document_id=doc_id,
        confidence=confidence,
        tier=tier,
        priority=priority,
        reasons=[r["reason_code"] for r in reasons],
        routed_to="review_queue",
    )


def _send_to_dlq(
    producer: KafkaProducer,
    event: any,
    error: str,
    doc_id: str | None = None,
    headers: list | None = None,
    tenant_id: str | None = None,
) -> None:
    """Send a failed message to the dead letter queue for manual inspection.

    ``tenant_id`` is optional because this path is hit on poison-pill
    and pre-auth failures where tenant resolution has not yet occurred.
    When present it scopes the retry-count lookup (#1122) and the
    Kafka partition key so DLQ'd messages do not collide with healthy
    messages from other tenants.
    """
    try:
        retry_key = _retry_key_for(tenant_id, doc_id or "unknown")
        # If event is already a dict, use it. If it's bytes (poison pill), wrap it.
        if isinstance(event, dict):
            payload = {
                "original_event": event,
                "error": error,
                "failed_at": _now_iso(),
                "source_topic": settings.topic_in if settings else "ingest.normalized",
                "retry_count": _retry_counts.get(retry_key, 0),
            }
        else:
            payload = {
                "raw_payload": str(event),
                "error": error,
                "failed_at": _now_iso(),
                "is_poison_pill": True,
            }

        producer.send(
            TOPIC_DLQ,
            key=_kafka_key_for(tenant_id, doc_id or "unknown"),
            value=payload,
            headers=headers or [],
        )
        producer.flush(timeout=1.0)
        logger.info(
            "message_sent_to_dlq",
            document_id=doc_id,
            tenant_id=tenant_id,
            error=error,
        )
    except (KafkaTimeoutError, ConnectionError, TimeoutError, OSError, RuntimeError) as dlq_exc:
        logger.error(
            "dlq_send_failed",
            document_id=doc_id,
            tenant_id=tenant_id,
            error=str(dlq_exc),
        )


def _is_fsma_event(evt: dict) -> bool:
    """Does this event relate to FSMA traceability?

    Three-layer signal (#1116):

    1. **Explicit FTL classification** — if the extractor stamped
       ``is_ftl_covered`` on any KDE (set by ``_classify_ftl`` against
       the shared FTL catalog), trust that directly. ``True`` means
       the product is on the FTL and the event is in scope; ``False``
       means a verified non-FTL food. This is the reliable signal.
    2. **URL / doc-id substring** — legacy heuristic kept as a
       fallback for events where extraction failed or the extractor
       couldn't classify (``is_ftl_covered`` is ``None``). Good enough
       to route to the FSMA DLQ so operators see the failure.
    3. Otherwise default to non-FSMA.
    """
    ftl_flags = _collect_ftl_flags(evt)
    if True in ftl_flags:
        return True
    # Everything we found was explicitly False — trust that.
    if ftl_flags and False in ftl_flags and True not in ftl_flags:
        return False

    source = str(evt.get("source_url", ""))
    doc_id = str(evt.get("document_id", ""))
    return (
        "fsma" in source.lower()
        or "fsma" in doc_id.lower()
        or "204" in source
    )


def _collect_ftl_flags(evt: dict) -> list:
    """Walk an event payload and collect every ``is_ftl_covered`` flag
    the extractor may have set on KDEs / CTEs. Returns a list of the
    values seen (``True`` / ``False``) — ``None`` entries are skipped
    so they don't tip the caller's tri-state gate to False."""
    flags: list = []
    ctes = evt.get("ctes") or []
    if isinstance(ctes, list):
        for cte in ctes:
            kdes = (cte or {}).get("kdes") if isinstance(cte, dict) else None
            if isinstance(kdes, dict) and kdes.get("is_ftl_covered") is not None:
                flags.append(kdes["is_ftl_covered"])
    top_kdes = evt.get("kdes")
    if isinstance(top_kdes, dict) and top_kdes.get("is_ftl_covered") is not None:
        flags.append(top_kdes["is_ftl_covered"])
    return flags


def _send_to_fsma_dlq(
    producer: KafkaProducer,
    event: any,
    error: str,
    doc_id: str | None = None,
    headers: list | None = None,
    tenant_id: str | None = None,
) -> None:
    """Route failed message to fsma.dead_letter if FSMA-related, else standard DLQ.

    ``tenant_id`` (#1122) is optional — callers hitting this pre-tenant
    (poison pill / auth failure) pass ``None`` and the Kafka key falls
    back to an unambiguous sentinel that cannot shadow any legitimate
    tenant's partition.
    """
    topic = TOPIC_FSMA_DLQ if isinstance(event, dict) and _is_fsma_event(event) else TOPIC_DLQ
    try:
        payload = {
            "original_event": event if isinstance(event, dict) else str(event),
            "error": error,
            "failed_at": _now_iso(),
            "source_topic": settings.topic_in if settings else "ingest.normalized",
            "dlq_topic": topic,
        }
        producer.send(
            topic,
            key=_kafka_key_for(tenant_id, doc_id or "unknown"),
            value=payload,
            headers=headers or [],
        )
        producer.flush(timeout=1.0)
        logger.info(
            "message_routed_to_dlq",
            topic=topic,
            document_id=doc_id,
            tenant_id=tenant_id,
            error=error,
        )
    except (ConnectionError, TimeoutError, OSError, RuntimeError) as dlq_exc:
        logger.error(
            "dlq_routing_failed",
            topic=topic,
            document_id=doc_id,
            tenant_id=tenant_id,
            error=str(dlq_exc),
        )


def stop_consumer() -> None:
    _shutdown_event.set()


# ---------------------------------------------------------------------------
# Issue #1231 — HTTP health endpoint for the Kafka consumer
# ---------------------------------------------------------------------------
#
# Orchestrators (Railway, Kubernetes, ECS) need a way to determine whether
# the consumer process is alive. Without this, the only liveness signal is
# "process still running", which misses stuck consumers that have stopped
# polling. A background thread exposes GET /health on port 8099; it returns
# 200 {"status":"ok"} as long as _shutdown_event is not set.
#
# Uses only Python stdlib (http.server) — no new dependencies.
# ---------------------------------------------------------------------------

import http.server
import socket


_HEALTH_PORT = int(os.getenv("NLP_HEALTH_PORT", "8099"))


class _HealthHandler(http.server.BaseHTTPRequestHandler):
    """Minimal HTTP handler for the consumer liveness probe."""

    def do_GET(self) -> None:  # noqa: N802
        if self.path in ("/health", "/healthz"):
            if _shutdown_event.is_set():
                self.send_response(503)
                body = b'{"status":"stopping"}'
            else:
                self.send_response(200)
                body = b'{"status":"ok"}'
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt: str, *args: object) -> None:  # noqa: N802
        # Suppress noisy access logs; structlog handles observability.
        pass


def _start_health_server() -> None:
    """Start a background thread serving the health endpoint on _HEALTH_PORT.

    The server uses SO_REUSEADDR so a fast restart doesn't hit EADDRINUSE.
    Binds to 0.0.0.0 so container health-check probes from the host can
    reach it without loopback-only restrictions.

    Called once from run_consumer() before the Kafka consumer loop starts so
    the probe is available from process startup (before the first Kafka poll).
    """
    try:
        server = http.server.HTTPServer(("0.0.0.0", _HEALTH_PORT), _HealthHandler)
        server.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    except OSError as exc:
        logger.warning(
            "health_server_bind_failed",
            port=_HEALTH_PORT,
            error=str(exc),
        )
        return

    thread = threading.Thread(
        target=server.serve_forever,
        name="nlp-health-server",
        daemon=True,  # exits when the main process exits
    )
    thread.start()
    logger.info("health_server_started", port=_HEALTH_PORT, path="/health")


from shared.observability import setup_standalone_observability
tracer = setup_standalone_observability("nlp-consumer")

def run_consumer() -> None:
    # Start health endpoint before first Kafka poll so probes succeed at startup
    _start_health_server()

    # Ensure topics exist
    _ensure_topic(TOPIC_GRAPH_UPDATE)
    _ensure_topic(TOPIC_NEEDS_REVIEW)
    _ensure_topic(TOPIC_FSMA_DLQ)
    _ensure_topic(TOPIC_DLQ)

    # Use raw consumer to handle poison pills manually
    consumer = KafkaConsumer(
        settings.topic_in,
        bootstrap_servers=settings.kafka_bootstrap,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
        group_id=settings.consumer_group_id,
    )
    producer = KafkaProducer(
        bootstrap_servers=settings.kafka_bootstrap,
        key_serializer=lambda v: v.encode("utf-8") if isinstance(v, str) else v,
        value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
        acks="all",
    )

    try:
        _run_consumer_loop(consumer, producer)
    finally:
        # #1220 — explicitly flush the producer before close so buffered
        # DLQ messages are persisted on SIGTERM. librdkafka's internal
        # buffer is asynchronous; without flush, in-flight dead-letters
        # (including FSMA extraction failures we keep for forensic
        # analysis) can be silently dropped when the process exits.
        _graceful_producer_shutdown(producer)
        try:
            consumer.close()
        except (RuntimeError, OSError) as exc:  # pragma: no cover - infra
            logger.warning("consumer_close_error", error=str(exc))


def _graceful_producer_shutdown(producer: KafkaProducer) -> None:
    """Flush buffered messages then close the producer (#1220).

    Called from ``run_consumer``'s ``finally`` block on graceful shutdown.
    The flush happens BEFORE close so any in-flight DLQ events — which
    carry forensic context for failed FSMA extractions — are delivered
    to the broker before the process exits. Exceptions are logged but
    never re-raised: we still want ``close()`` to run even if the broker
    is unreachable during shutdown.
    """
    try:
        producer.flush(timeout=5.0)
        logger.info("nlp_producer_flushed_on_shutdown")
    except Exception as exc:  # pragma: no cover - infra dependent
        logger.exception("dlq_flush_on_shutdown_failed", error=str(exc))
    try:
        producer.close(timeout=5.0)
    except (RuntimeError, OSError) as exc:  # pragma: no cover - infra
        logger.warning("producer_close_error", error=str(exc))


def _run_consumer_loop(consumer: KafkaConsumer, producer: KafkaProducer) -> None:
    while not _shutdown_event.is_set():
        messages = consumer.poll(timeout_ms=500)
        if not messages:
            continue
        for records in messages.values():
            for record in records:
                # Re-hydrate correlation_id (and tenant_id) from the inbound
                # message's Kafka headers so every log record inside this
                # iteration carries the originator's trace ID (#1318).
                with bind_correlation_context(record.headers or []):
                    # #1176 — explicit header-tenant extraction separate from
                    # the contextvar bind so the raw value survives the
                    # `bind_correlation_context` exit and can be compared
                    # against the payload tenant_id below (injection check).
                    _, header_tenant_id = extract_correlation_headers(
                        record.headers or []
                    )
                    # Standardized Trace Injection
                    with tracer.start_as_current_span(
                        "nlp.process_message",
                        attributes={"kafka.topic": record.topic, "kafka.offset": record.offset}
                    ) as span:
                        # Capture trace context for DLQ headers (OTel W3C)
                        otel_headers: list = []
                        propagate.inject(otel_headers)
                        # Merge OTel headers + correlation headers for DLQ so
                        # dead-lettered messages can still be traced back.
                        merged_otel = [(k, v.encode("utf-8")) for k, v in otel_headers]
                        kafka_headers = inject_correlation_headers_tuples(existing=merged_otel)

                        raw_value = record.value
                        try:
                            evt = json.loads(raw_value.decode("utf-8")) if raw_value else {}
                        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
                            logger.error("poison_pill_detected", error=str(exc), offset=record.offset)
                            POISON_PILL_COUNTER.inc()
                            _send_to_dlq(producer, raw_value, f"Deserialization failed: {str(exc)}", headers=kafka_headers)
                            # #1085 — flush DLQ producer BEFORE committing the
                            # inbound offset. producer.send() only buffers; a
                            # crash between buffer and broker-ack would advance
                            # the offset while the DLQ record is still sitting
                            # in the producer buffer — silent data loss and an
                            # FSMA 204 audit-trail gap. On timeout, refuse to
                            # commit so Kafka redelivers the message.
                            try:
                                producer.flush(timeout=5.0)
                            except KafkaTimeoutError:
                                logger.error(
                                    "dlq_flush_timeout",
                                    offset=record.offset,
                                    topic=record.topic,
                                    stage="poison_pill",
                                )
                                continue  # do NOT commit — force redelivery
                            consumer.commit()
                            continue

                        if not evt: continue

                        # --- HMAC producer authentication (#1078) ---
                        # Before routing by ``tenant_id``, verify that
                        # the message was signed by a service we trust
                        # to publish to this topic. Without this, any
                        # actor that can publish to ingest.normalized
                        # can tag a forged event with any tenant_id
                        # they choose — the audit log records the
                        # *claimed* tenant, so cross-tenant injection
                        # has no audit signal. On failure the message
                        # is DLQ'd and the offset is committed so the
                        # partition is not blocked by retries that
                        # will never succeed.
                        try:
                            evt, _verified_producer = verify_event(
                                evt,
                                record.headers,
                                topic=settings.topic_in,
                                allowed_producers=get_allowed_producers(settings.topic_in),
                            )
                        except KafkaAuthError as auth_exc:
                            logger.error(
                                "kafka_auth_failed",
                                reason=auth_exc.reason,
                                topic=settings.topic_in,
                                offset=record.offset,
                                **auth_exc.fields,
                            )
                            POISON_PILL_COUNTER.inc()
                            doc_id_for_dlq = (
                                evt.get("document_id") if isinstance(evt, dict) else None
                            ) or "unknown"
                            _send_to_fsma_dlq(
                                producer,
                                evt if isinstance(evt, dict) else raw_value,
                                f"kafka_auth_failed: {auth_exc}",
                                doc_id_for_dlq,
                                kafka_headers,
                            )
                            MESSAGES_COUNTER.labels(status="unauthorized").inc()
                            # #1085 — flush DLQ producer before committing.
                            try:
                                producer.flush(timeout=5.0)
                            except KafkaTimeoutError:
                                logger.error(
                                    "dlq_flush_timeout",
                                    offset=record.offset,
                                    topic=record.topic,
                                    stage="kafka_auth_failed",
                                )
                                continue  # do NOT commit — force redelivery
                            consumer.commit()
                            continue

                        # Extract doc_id early for logging (before validation)
                        doc_id = evt.get("document_id") or evt.get("doc_id") or "unknown"
                        span.set_attribute("document_id", doc_id)

                        # --- Inbound schema validation (OWASP API10:2023) ---
                        if _INBOUND_VALIDATOR is not None:
                            errors = list(_INBOUND_VALIDATOR.iter_errors(evt))
                            if errors:
                                error_msg = "; ".join(e.message for e in errors[:5])
                                logger.error(
                                    "inbound_schema_invalid",
                                    document_id=doc_id,
                                    error=error_msg,
                                    offset=record.offset,
                                )
                                # tenant_id has not been resolved yet — this
                                # reject may or may not have a usable tenant
                                # context; pass the raw payload value as a
                                # best-effort hint for DLQ partitioning
                                # (#1122). ``None`` is safe — _send_to_fsma_dlq
                                # falls back to the NO_TENANT sentinel key.
                                _send_to_fsma_dlq(
                                    producer, evt,
                                    f"Inbound schema invalid: {error_msg}",
                                    doc_id, headers=kafka_headers,
                                    tenant_id=evt.get("tenant_id") if isinstance(evt, dict) else None,
                                )
                                MESSAGES_COUNTER.labels(status="rejected").inc()
                                # #1085 — flush DLQ producer before committing.
                                try:
                                    producer.flush(timeout=5.0)
                                except KafkaTimeoutError:
                                    logger.error(
                                        "dlq_flush_timeout",
                                        offset=record.offset,
                                        topic=record.topic,
                                        stage="inbound_schema_invalid",
                                    )
                                    continue  # do NOT commit — force redelivery
                                consumer.commit()
                                continue

                        try:
                            doc_hash = evt.get("document_hash") or evt.get("content_hash") or doc_id
                            norm_path = evt.get("normalized_s3_path")
                            inline_text = evt.get("text_clean")
                            # #1176 — resolve tenant_id from header (preferred)
                            # or payload. Fail-fast DLQ on missing / invalid /
                            # mismatched values so downstream writes can never
                            # happen without tenant context.
                            tenant_id, _tenant_reject_reason = _resolve_tenant_id(
                                header_tenant_id=header_tenant_id,
                                payload_tenant_id=evt.get("tenant_id"),
                            )
                            provenance = evt.get("provenance") or {}
                        except (KeyError, TypeError, ValueError, AttributeError) as field_exc:
                            logger.error(
                                "malformed_event_fields",
                                error=str(field_exc),
                                offset=record.offset,
                            )
                            _send_to_fsma_dlq(
                                producer, evt, f"Field extraction failed: {field_exc}",
                                doc_id, kafka_headers,
                                tenant_id=evt.get("tenant_id") if isinstance(evt, dict) else None,
                            )
                            MESSAGES_COUNTER.labels(status="error").inc()
                            # #1085 — flush DLQ producer before committing.
                            try:
                                producer.flush(timeout=5.0)
                            except KafkaTimeoutError:
                                logger.error(
                                    "dlq_flush_timeout",
                                    offset=record.offset,
                                    topic=record.topic,
                                    stage="malformed_event_fields_pre_tenant",
                                )
                                continue  # do NOT commit — force redelivery
                            consumer.commit()
                            continue

                        # #1176/#1122 — if tenant resolution failed, send to FSMA
                        # DLQ and skip processing. An NLP extraction with no
                        # tenant context cannot safely reach the graph / review
                        # queue because downstream stores all assume tenant
                        # scoping. The sentinel ``E_MISSING_TENANT_ID`` is
                        # included in the DLQ reason so SRE can grep across
                        # services for a consistent signal.
                        if tenant_id is None:
                            logger.error(
                                "nlp_message_rejected_missing_tenant",
                                document_id=doc_id,
                                reason=_tenant_reject_reason,
                                error_code="E_MISSING_TENANT_ID",
                                offset=record.offset,
                            )
                            TENANT_RESOLUTION_COUNTER.labels(outcome="rejected").inc()
                            _send_to_fsma_dlq(
                                producer,
                                evt,
                                f"E_MISSING_TENANT_ID: {_tenant_reject_reason}",
                                doc_id,
                                headers=kafka_headers,
                                tenant_id=None,
                            )
                            MESSAGES_COUNTER.labels(status="rejected").inc()
                            # #1085 — flush DLQ producer before committing.
                            try:
                                producer.flush(timeout=5.0)
                            except KafkaTimeoutError:
                                logger.error(
                                    "dlq_flush_timeout",
                                    offset=record.offset,
                                    topic=record.topic,
                                    stage="tenant_resolution_failed",
                                )
                                continue  # do NOT commit — force redelivery
                            consumer.commit()
                            continue

                        TENANT_RESOLUTION_COUNTER.labels(
                            outcome="from_header" if header_tenant_id else "from_payload"
                        ).inc()

                    try:
                        doc_hash = evt.get("document_hash") or evt.get("content_hash") or doc_id
                        norm_path = evt.get("normalized_s3_path")
                        inline_text = evt.get("text_clean")
                        # #1176 — resolver already ran above; reuse the
                        # validated tenant_id. Do not re-read from payload
                        # here because that would defeat the header-priority
                        # and mismatch-rejection checks.
                        provenance = evt.get("provenance") or {}
                    except (KeyError, TypeError, ValueError, AttributeError) as field_exc:
                        logger.error(
                            "malformed_event_fields",
                            error=str(field_exc),
                            tenant_id=tenant_id,
                            offset=record.offset,
                        )
                        _send_to_fsma_dlq(
                            producer, evt, f"Field extraction failed: {field_exc}",
                            doc_id, kafka_headers,
                            tenant_id=tenant_id,
                        )
                        MESSAGES_COUNTER.labels(status="error").inc()
                        # #1085 — flush DLQ producer before committing.
                        try:
                            producer.flush(timeout=5.0)
                        except KafkaTimeoutError:
                            logger.error(
                                "dlq_flush_timeout",
                                offset=record.offset,
                                topic=record.topic,
                                stage="malformed_event_fields_post_tenant",
                            )
                            continue  # do NOT commit — force redelivery
                        consumer.commit()
                        continue

                    if not doc_id or (not norm_path and not inline_text):
                        logger.warning("skipping_event_missing_keys", event=evt)
                        MESSAGES_COUNTER.labels(status="skipped").inc()
                        consumer.commit()
                        continue

                    try:
                        if inline_text:
                            text = str(inline_text)[:2_000_000]
                            source_url = provenance.get(
                                "source_url", evt.get("source_url", "unknown")
                            )
                        else:
                            # #1127 — use validated parse instead of inline
                            # partition(). parse_s3_uri() → validate_s3_uri()
                            # rejects path traversal and malformed URIs.
                            try:
                                bucket, key = parse_s3_uri(norm_path)
                            except (ValueError, PathTraversalError) as parse_err:
                                logger.warning(
                                    "s3_uri_rejected",
                                    norm_path=norm_path,
                                    doc_id=doc_id,
                                    tenant_id=tenant_id,
                                    err=str(parse_err),
                                )
                                MESSAGES_COUNTER.labels(status="skipped").inc()
                                consumer.commit()
                                continue
                            payload = json.loads(get_bytes(bucket, key))
                            text = payload.get("text", "")[:2_000_000]
                            source_url = payload.get("source_url", "unknown")

                        # --- Structured extractor pass (#1194) ---
                        # FSMAExtractor runs first for every document when the
                        # feature flag is on. It owns KDE-minimum gating for
                        # FSMA 204 and routes qualifying CTEs to
                        # ``graph.update`` or ``nlp.needs_review``. When the
                        # flag is off, this block is a no-op and the legacy
                        # regex pipeline below is the only path.
                        fsma_summary: Optional[dict] = None
                        if NLP_ENABLE_FSMA_EXTRACTOR:
                            fsma_summary = _run_fsma_extractor(
                                text=text,
                                doc_id=doc_id,
                                doc_hash=doc_hash,
                                producer=producer,
                                tenant_id=tenant_id,
                                kafka_headers=kafka_headers,
                            )

                        # --- Legacy regex extractor (backstop) ---
                        entities = extract_entities(text)

                        # Convert to canonical ExtractionPayload format
                        extractions = _convert_entities_to_extraction(
                            entities, doc_id, source_url
                        )

                        # --- LLM fallback pass (#1194) ---
                        # Only invoked when the regex+FSMA passes yielded
                        # NO high-confidence extractions and the operator
                        # has explicitly opted in to LLM spend.
                        if NLP_ENABLE_LLM_EXTRACTOR:
                            produced_high_conf = (
                                fsma_summary is not None
                                and fsma_summary.get("high_confidence")
                            ) or any(
                                e.confidence_score >= settings.extraction_confidence_high
                                for e in extractions
                            )
                            if not produced_high_conf:
                                jurisdiction = "US-FDA" if _is_fsma_event(evt) else "unknown"
                                llm_results = _run_llm_extractor(
                                    text=text,
                                    doc_id=doc_id,
                                    jurisdiction=jurisdiction,
                                )
                                logger.info(
                                    "llm_extractor_run",
                                    document_id=doc_id,
                                    result_count=len(llm_results),
                                )
                                # LLM results currently augment the log and
                                # feed the review queue via extractions
                                # below; bridging to the legacy entity
                                # schema is handled by a follow-up PR.

                        # Route each extraction based on confidence
                        for extraction in extractions:
                            _route_extraction(
                                extraction,
                                doc_id,
                                doc_hash,
                                source_url,
                                producer,
                                tenant_id,
                            )

                        # Legacy ``nlp.extracted`` topic — OFF by default (#1218).
                        # The legacy publish sent the raw ``entities`` list with
                        # zero confidence filtering, defeating the gating at the
                        # Kafka boundary. Operators may re-enable via env
                        # ``NLP_EMIT_LEGACY_TOPIC=1`` during a migration window;
                        # each emit logs a deprecation warning so migration
                        # progress is observable.
                        if EMIT_LEGACY_EXTRACTED_TOPIC:
                            # Annotate each entity with its (capped) confidence
                            # so downstream subscribers at minimum see the tier.
                            high_t, medium_t = _current_thresholds()
                            annotated_entities = []
                            for ent in entities:
                                # Attach a placeholder confidence if absent;
                                # the regex path has no per-entity score.
                                annotated = dict(ent)
                                annotated.setdefault(
                                    "confidence_score",
                                    min(0.50, _LEGACY_HEURISTIC_CONFIDENCE_CAP),
                                )
                                annotated_entities.append(annotated)
                            legacy_out = {
                                "event_id": str(uuid.uuid4()),
                                "document_id": doc_id,
                                "tenant_id": tenant_id,
                                "source_url": source_url,
                                "timestamp": _now_iso(),
                                "entities": annotated_entities,
                                "deprecated": True,
                                "deprecation_notice": (
                                    "nlp.extracted is deprecated; migrate to "
                                    "graph.update / nlp.needs_review. Set "
                                    "NLP_EMIT_LEGACY_TOPIC=0 to disable."
                                ),
                            }
                            try:
                                _load_schema().validate(legacy_out)
                                # Sign the legacy emit too — subscribers
                                # that have verification wired on will
                                # refuse to accept unsigned messages on
                                # any topic (#1078).
                                signed_legacy, signed_legacy_headers = sign_event(
                                    legacy_out,
                                    producer_service=NLP_PRODUCER_SERVICE,
                                )
                                producer.send(
                                    settings.topic_out,
                                    # #1122 — tenant-scoped Kafka key.
                                    key=_kafka_key_for(tenant_id, doc_id),
                                    value=signed_legacy,
                                    headers=signed_legacy_headers,
                                )
                                logger.warning(
                                    "nlp_legacy_topic_emitted",
                                    document_id=doc_id,
                                    topic=settings.topic_out,
                                    reason="NLP_EMIT_LEGACY_TOPIC=1 set",
                                )
                            except ValidationError as legacy_exc:
                                logger.error(
                                    "nlp_legacy_topic_schema_invalid",
                                    document_id=doc_id,
                                    error=str(legacy_exc),
                                )

                        producer.flush(timeout=1.0)

                        # Use live thresholds for logging counts so metrics
                        # agree with _route_extraction behavior (#1260).
                        high_t_log, medium_t_log = _current_thresholds()
                        logger.info(
                            "nlp_extraction_complete",
                            document_id=doc_id,
                            tenant_id=tenant_id,
                            extraction_count=len(extractions),
                            high_confidence=sum(
                                1 for e in extractions
                                if e.confidence_score >= high_t_log
                            ),
                            medium_confidence=sum(
                                1 for e in extractions
                                if medium_t_log <= e.confidence_score < high_t_log
                            ),
                            low_confidence=sum(
                                1 for e in extractions
                                if e.confidence_score < medium_t_log
                            ),
                        )
                        MESSAGES_COUNTER.labels(status="success").inc()

                        # Synchronous audit logging for FSMA compliance (#982)
                        try:
                            _audit_logger.info(
                                "nlp_extraction_audited",
                                extra={
                                    "document_id": doc_id,
                                    "tenant_id": tenant_id,
                                    "source_url": source_url,
                                    "extraction_count": len(extractions),
                                    "timestamp": _now_iso(),
                                },
                            )
                        except Exception as _audit_exc:
                            logger.error("nlp_audit_logging_failed", document_id=doc_id, error=str(_audit_exc))

                        consumer.commit()
                    except (ValidationError, KafkaTimeoutError) as exc:
                        # #1122 — tenant-scoped retry-count key. Prior code
                        # keyed only by doc_id which meant two tenants with
                        # the same doc_id shared a retry bucket (e.g.
                        # tenant A's 3rd retry DLQ'd tenant B's first
                        # attempt).
                        retry_key = _retry_key_for(tenant_id, doc_id or "unknown")
                        _retry_counts[retry_key] = _retry_counts.get(retry_key, 0) + 1

                        if _retry_counts[retry_key] >= MAX_RETRIES:
                            logger.error(
                                "nlp_max_retries_exceeded_sending_to_dlq",
                                document_id=doc_id,
                                tenant_id=tenant_id,
                                retries=_retry_counts[retry_key],
                                error=str(exc),
                            )
                            _send_to_fsma_dlq(
                                producer,
                                evt,
                                str(exc),
                                doc_id,
                                headers=kafka_headers,
                                tenant_id=tenant_id,
                            )
                            _retry_counts.pop(retry_key, None)
                            # #1085 — flush DLQ producer before committing.
                            try:
                                producer.flush(timeout=5.0)
                            except KafkaTimeoutError:
                                logger.error(
                                    "dlq_flush_timeout",
                                    offset=record.offset,
                                    topic=record.topic,
                                    stage="max_retries_exceeded",
                                )
                                # Restore retry counter so redelivery doesn't
                                # reset the retry budget on this message.
                                _retry_counts[retry_key] = MAX_RETRIES
                                continue  # do NOT commit — force redelivery
                            consumer.commit()
                        else:
                            logger.warning(
                                "nlp_validation_or_kafka_error_will_retry",
                                document_id=doc_id,
                                tenant_id=tenant_id,
                                retry=_retry_counts[retry_key],
                                error=str(exc),
                            )
                        MESSAGES_COUNTER.labels(status="error").inc()
                    except Exception as exc:  # pragma: no cover - requires infra
                        logger.exception(
                            "nlp_processing_error_sending_to_dlq",
                            document_id=doc_id,
                            tenant_id=tenant_id,
                            error=str(exc),
                        )
                        _send_to_fsma_dlq(
                            producer,
                            evt,
                            str(exc),
                            doc_id,
                            headers=kafka_headers,
                            tenant_id=tenant_id,
                        )
                        try:
                            producer.flush(timeout=5.0)
                        except KafkaTimeoutError:
                            logger.error(
                                "dlq_flush_timeout",
                                offset=record.offset,
                                topic=record.topic,
                                stage="processing_error",
                            )
                            continue  # do NOT commit — force redelivery
                        consumer.commit()
                        MESSAGES_COUNTER.labels(status="error").inc()
