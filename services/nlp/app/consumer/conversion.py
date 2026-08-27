"""Legacy entity → ExtractionPayload conversion for the NLP consumer.

Split out of the original ``app/consumer.py`` module. All names are
re-exported from ``app.consumer`` for backward compatibility.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import structlog

from shared.schemas import (
    ExtractionPayload,
    ObligationType,
    Threshold,
)

from ..classification import SignalClassifier
from ..extractor import infer_obligation_type
from ..resolution import MASTER_DATA_SOURCE, EntityResolver

from .constants import (
    _LEGACY_HEURISTIC_CONFIDENCE_CAP,
    _LLM_EXTRACTION_CONFIDENCE_CAP,
)

logger = structlog.get_logger("nlp-consumer")

RESOLVER = EntityResolver()
CLASSIFIER = SignalClassifier()

# The single legal mapping from the extractor's modality vocabulary onto the
# canonical ObligationType (#2942). This module used to re-derive modality with
# a backward-only negation window that could never see the "not" in "shall
# not", so every prohibition was persisted as MUST — the inversion of the rule.
# Modality is owned by ``extractor.infer_obligation_type``; this table is the
# only thing that stands between its verdict and the canonical enum.
#
# PROHIBITED deliberately splits by ``negation_scope``: a ban is MUST_NOT,
# while a lifted duty ("small farms are not required to file") is a permission.
# Typing an exemption MUST_NOT would forbid conduct the regulation merely
# stopped mandating — the same inversion, pointed the other way.
_MODALITY_TO_OBLIGATION_TYPE = {
    ("MANDATORY", None): ObligationType.MUST,
    ("PERMITTED", None): ObligationType.MAY,
    ("CONDITIONAL", None): ObligationType.SHOULD,
    ("PROHIBITED", "prohibition"): ObligationType.MUST_NOT,
    ("PROHIBITED", "exemption"): ObligationType.MAY,
}

_MODALITIES_WITH_SCOPE = {"PROHIBITED"}


def _modality_verdict(entity: dict) -> dict:
    """Return the extractor's modality verdict for an OBLIGATION *entity*.

    ``extract_entities`` already stamps the verdict onto ``attrs`` (#1299), so
    the normal path is a read. Entities hand-built by other producers carry no
    ``attrs``; those are re-scored by calling the same function rather than by
    re-implementing it here.
    """

    attrs = entity.get("attrs") or {}
    modality = attrs.get("obligation")
    scope = attrs.get("negation_scope")
    if (modality, scope if modality in _MODALITIES_WITH_SCOPE else None) in (
        _MODALITY_TO_OBLIGATION_TYPE
    ):
        return {
            "obligation": modality,
            "negation_detected": bool(attrs.get("negation_detected")),
            "negation_scope": scope,
        }
    return infer_obligation_type(entity.get("text") or "")


def _obligation_type_for(verdict: dict) -> ObligationType:
    """Map a modality verdict onto the canonical ObligationType."""

    modality = verdict.get("obligation")
    scope = verdict.get("negation_scope") if modality in _MODALITIES_WITH_SCOPE else None
    try:
        return _MODALITY_TO_OBLIGATION_TYPE[(modality, scope)]
    except KeyError:
        # An unmapped verdict must not silently become a mandate. SHOULD
        # asserts neither a duty nor a ban, and the review reason below makes
        # the gap visible to the reviewer.
        logger.warning(
            "obligation_modality_unmapped",
            modality=modality,
            negation_scope=scope,
        )
        return ObligationType.SHOULD


def _now_iso() -> str:
    # Match the `Z` suffix contract enforced by the FSMA extractor
    # (see `app/extractors/fsma_extractor.py`) so all NLP-service timestamps
    # share a single UTC serialization. Python's default `isoformat()` emits
    # `+00:00`, which breaks downstream consumers that expect `Z`. -- #1132
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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

        # Obligation modality (#1299, #2942). Read the verdict the extractor
        # already computed instead of re-deriving it; see
        # ``_MODALITY_TO_OBLIGATION_TYPE`` above for why there is exactly one
        # implementation of this.
        verdict = _modality_verdict(obl)
        obl_type = _obligation_type_for(verdict)

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
                    entity_info["normalized_name"] = resolution["name"]
                    entity_info["entity_type"] = resolution["type"]
                    entity_info["match_strategy"] = resolution.get(
                        "match_strategy", "unknown"
                    )
                    entity_info["match_score"] = resolution.get("match_score")
                    source = resolution.get("source")
                    entity_info["resolution_source"] = source or "unknown"
                    if source and source != MASTER_DATA_SOURCE:
                        # A real master-data lookup: the identifier is
                        # authoritative and belongs in the audit trail.
                        entity_info["entity_id"] = resolution["id"]
                    else:
                        # #2944 — the id would be a repository literal
                        # (``duns:007874200``). Persisting it into FSMA
                        # compliance evidence fabricates provenance that looks
                        # like an MDM resolution, so the field is omitted
                        # rather than stubbed. The raw name, the candidate
                        # name and the match score still reach the reviewer.
                        entity_info["entity_id_withheld_reason"] = (
                            "stub_master_data_is_not_an_authoritative_identifier"
                        )

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
            # Modality provenance (#2942) so a reviewer can see that the
            # obligation direction came from a negated reading, and so an
            # inverted value is detectable in stored data.
            "obligation_modality": verdict.get("obligation"),
            "negation_detected": bool(verdict.get("negation_detected")),
        }
        if verdict.get("negation_scope"):
            attributes["negation_scope"] = verdict["negation_scope"]
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


# ---------------------------------------------------------------------------
# Generative-LLM results → canonical ExtractionPayload (#2947)
# ---------------------------------------------------------------------------

# LLMExtraction.obligation_type vocabulary → canonical enum. PROHIBITION maps
# to MUST_NOT for the same reason the regex path does (#2942): a ban stored as
# a mandate is the inversion of the rule. EXEMPTION lifts a duty, so it is a
# permission, not a ban. UNKNOWN asserts neither and is flagged for the
# reviewer instead of defaulting to a mandate.
_LLM_OBLIGATION_TYPE = {
    "REQUIREMENT": ObligationType.MUST,
    "PROHIBITION": ObligationType.MUST_NOT,
    "REPORTING": ObligationType.REPORTING,
    "EXEMPTION": ObligationType.MAY,
    "UNKNOWN": ObligationType.SHOULD,
}

_LLM_ACTION = {
    ObligationType.MUST: "must",
    ObligationType.MUST_NOT: "must not",
    ObligationType.REPORTING: "must report",
    ObligationType.MAY: "may",
    ObligationType.SHOULD: "should",
}


def _llm_field(item, name: str, default=None):
    """Read *name* off an LLMExtraction or an equivalent mapping."""

    if isinstance(item, dict):
        value = item.get(name, default)
    else:
        value = getattr(item, name, default)
    return default if value is None else value


def _convert_llm_results_to_extractions(
    llm_results: list, doc_id: str, source_url: str
) -> list[ExtractionPayload]:
    """Bridge ``LLMGenerativeExtractor`` output into canonical extractions.

    Before this existed the consumer called the extractor, logged
    ``result_count``, and dropped the list on the floor: the routing loop
    iterated only the regex path's ``extractions``, so an operator who enabled
    ``NLP_ENABLE_LLM_EXTRACTOR`` paid a third-party provider per document for
    output nothing read, and the hallucination, provenance, injection-marker
    and truncation guardrails in ``llm_extractor.py`` protected nothing (#2947).

    Fail-closed by construction:

    * confidence is capped at :data:`_LLM_EXTRACTION_CONFIDENCE_CAP`, below the
      medium routing threshold, so nothing here can auto-publish to the graph
      on an LLM's self-reported score;
    * an item with no ``provision_text`` is dropped, because there is no span a
      reviewer could check against the source document;
    * ``needs_review`` / ``review_reason`` / ``truncated_input`` ride along in
      ``attributes`` and become review-reason codes.
    """

    extractions: list[ExtractionPayload] = []
    dropped = 0

    for item in llm_results or []:
        provision_text = str(_llm_field(item, "provision_text", "")).strip()
        if not provision_text:
            dropped += 1
            continue

        raw_type = str(_llm_field(item, "obligation_type", "UNKNOWN"))
        obl_type = _LLM_OBLIGATION_TYPE.get(raw_type, ObligationType.SHOULD)

        try:
            reported_confidence = float(_llm_field(item, "confidence", 0.0))
        except (TypeError, ValueError):
            reported_confidence = 0.0
        confidence = max(
            0.0, min(reported_confidence, _LLM_EXTRACTION_CONFIDENCE_CAP)
        )

        span_start = _llm_field(item, "source_span_start", 0)
        parts = provision_text.split()
        attributes = {
            "document_id": doc_id,
            "source_url": source_url,
            "extractor": "llm_generative_v1",
            "confidence_capped_at": _LLM_EXTRACTION_CONFIDENCE_CAP,
            "llm_reported_confidence": reported_confidence,
            "llm_obligation_type": raw_type,
            "llm_source_document_id": _llm_field(item, "source_document_id"),
            "llm_source_span_end": _llm_field(item, "source_span_end"),
            "llm_needs_review": bool(_llm_field(item, "needs_review", False)),
            "llm_review_reason": _llm_field(item, "review_reason"),
            "llm_truncated_input": bool(_llm_field(item, "truncated_input", False)),
        }
        if raw_type not in _LLM_OBLIGATION_TYPE:
            attributes["llm_obligation_type_unmapped"] = True

        extractions.append(
            ExtractionPayload(
                subject=" ".join(parts[: min(3, len(parts))]),
                action=_LLM_ACTION.get(obl_type, "must"),
                object=None,
                obligation_type=obl_type,
                confidence_score=confidence,
                source_text=provision_text,
                source_offset=int(span_start or 0),
                attributes=attributes,
            )
        )

    if dropped:
        logger.warning(
            "llm_results_dropped_no_provenance_span",
            document_id=doc_id,
            dropped=dropped,
        )

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

    # F-NLP-5: removed provenance bonus. The producer at
    # ``extractor.py:_extract_regulatory_dates`` hardcodes
    # ``provenance="FSMA Rule Text"`` on every match, so the bonus fired
    # tautologically on every extracted regulatory date. The check was
    # dead weight bounded by ``_LEGACY_HEURISTIC_CONFIDENCE_CAP`` — not
    # exploitable, but a future patch could mistake it for a real signal.

    # Cap: even "perfect" regex matches never auto-approve regulatory dates.
    return min(score, _LEGACY_HEURISTIC_CONFIDENCE_CAP)
