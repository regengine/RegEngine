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
from ..resolution import EntityResolver

from .constants import _LEGACY_HEURISTIC_CONFIDENCE_CAP

logger = structlog.get_logger("nlp-consumer")

RESOLVER = EntityResolver()
CLASSIFIER = SignalClassifier()


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

    # F-NLP-5: removed provenance bonus. The producer at
    # ``extractor.py:_extract_regulatory_dates`` hardcodes
    # ``provenance="FSMA Rule Text"`` on every match, so the bonus fired
    # tautologically on every extracted regulatory date. The check was
    # dead weight bounded by ``_LEGACY_HEURISTIC_CONFIDENCE_CAP`` — not
    # exploitable, but a future patch could mistake it for a real signal.

    # Cap: even "perfect" regex matches never auto-approve regulatory dates.
    return min(score, _LEGACY_HEURISTIC_CONFIDENCE_CAP)
