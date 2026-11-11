"""Review-reason codes for the human-in-the-loop queue.

Split out of the original ``app/consumer.py`` module. The three-tier
``_route_extraction`` producer that lived beside this function was Kafka-only
and was retired with the backbone (WI-05, 2026-11-04); the pg task path in
``server/workers/task_processor.py`` applies the same tiering itself and
calls ``_build_review_reasons`` for the review envelope.
"""

from __future__ import annotations

from shared.schemas import ExtractionPayload


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
    if attributes.get("llm_needs_review"):
        # #2947 — the generative extractor's output-side guardrails (injection
        # markers, ambiguous spans) set this. It was computed and discarded
        # until the LLM bridge landed.
        reasons.append(
            {
                "reason_code": "llm_flagged_for_review",
                "description": (
                    "LLM extraction flagged by output guardrails: "
                    f"{attributes.get('llm_review_reason') or 'unspecified'}"
                ),
                "severity": "error",
            }
        )
    if attributes.get("llm_truncated_input"):
        reasons.append(
            {
                "reason_code": "llm_truncated_input",
                "description": (
                    "LLM extraction was made from a truncated prefix of the "
                    "source document (#1370); the rest of the document was "
                    "never read"
                ),
                "severity": "warning",
            }
        )
    if attributes.get("negation_detected"):
        # #2942 — the obligation direction was derived from a negated reading
        # ("shall not", "not required to"). A reviewer skimming the structured
        # field must be told to check the direction against source_text.
        obligation_type = getattr(
            extraction.obligation_type, "value", extraction.obligation_type
        )
        scope = attributes.get("negation_scope") or "negation"
        reasons.append(
            {
                "reason_code": "negated_obligation",
                "description": (
                    f"Source text reads as a {scope}; modality resolved to "
                    f"{obligation_type} — confirm the direction against source_text"
                ),
                "severity": "warning",
            }
        )
    return reasons
