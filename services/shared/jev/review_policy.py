"""Preview evidence/diagnostic policy. No record changes or automatic assignments."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .client import JevAnswers, JevDecider, JevUnavailable, get_jev_decider
from .review_validation import validate_review_answers

QUESTIONS_VERSION = "review-2026-10-29-v1"
QUESTION_SETS = json.loads(Path(__file__).with_name("review_questions.json").read_text())
# Provisional thresholds: neither control agreement nor owner accuracy is approved.
YES, NO, POLARITY_PROBABILITY, MARGIN = 0.70, 0.30, 0.75, 0.20
OWNER_LABELS = {
    "upstream_supplier_or_grower_rep": "Upstream Supplier Rep",
    "warehouse_receiving_or_shipping_clerk": "Warehouse Receiving or Shipping Clerk",
    "erp_or_spreadsheet_report_owner": "ERP Report Owner",
    "fsqa_or_item_declaration_owner": "FSQA Lead",
    "needs_founder_manual_triage": "Triage on 15-min Review Call",
}


def _signal(probability: float) -> str:
    return "present" if probability >= YES else "absent" if probability <= NO else "uncertain"


def _ranked(answer: dict) -> list[tuple[str, float]]:
    return sorted(answer["probabilities"].items(), key=lambda item: (-item[1], item[0]))


def _decisive(answer: dict, threshold: float = POLARITY_PROBABILITY) -> bool:
    ranked = _ranked(answer)
    return ranked[0][1] >= threshold and ranked[0][1] - ranked[1][1] >= MARGIN


def adjudicate_evidence(raw_answers: dict, *, authoritative_scope_verified: bool = False) -> dict:
    """Preserve technical polarity and source conflict as independent observations."""
    validate_review_answers(raw_answers, QUESTION_SETS["mode_b"])
    presence = _signal(raw_answers["q1_topic_presence"]["noul"])
    conflict = _signal(raw_answers["q2_cross_source_conflict"]["noul"])
    polarity = raw_answers["q3_evidence_polarity"]
    verdict = "insufficient"
    reasons = []
    if authoritative_scope_verified is not True:
        reasons.append("authoritative_scope_unverified")
    if presence != "present":
        reasons.append(f"topic_{presence}")
    if not _decisive(polarity):
        reasons.append("polarity_uncertain")
    if presence == "present" and authoritative_scope_verified is True and _decisive(polarity):
        verdict = {"explicitly_supported": "supported", "explicitly_contradicted": "contradicted"}.get(
            polarity["choice"], "insufficient"
        )
        if verdict == "insufficient":
            reasons.append(polarity["choice"])
    if conflict != "absent":
        reasons.append(f"source_conflict_{conflict}")
    label = "insufficient"
    if presence == "present":
        label = "conflicting" if conflict == "present" else verdict if conflict == "absent" else "insufficient"
    return {
        "label": label,
        "claim_verdict": verdict,
        "source_conflict": conflict,
        "reason_codes": reasons,
        "review_required": True,
    }


def summarize_diagnostic(
    raw_answers: dict,
    *,
    evidence_flags: dict | None = None,
) -> dict:
    """Verified flags must come from trusted records, never uploaded/model-supplied flags."""
    validate_review_answers(raw_answers, QUESTION_SETS["mode_a"])
    flags = evidence_flags or {}
    source, origin = raw_answers["tlc_source_assessment"], raw_answers["data_gap_origin"]
    owner = raw_answers["correction_owner_role"]
    effort = raw_answers["customer_review_effort"]
    sufficient = raw_answers["effort_basis_sufficient"]["noul"] >= YES
    supported_effort = (
        flags.get("effort_basis_verified") is True and sufficient and max(effort["probabilities"].values()) >= 0.75
    )
    candidates = [
        {"role": role, "label": OWNER_LABELS[role], "probability": probability}
        for role, probability in _ranked(owner)
        if role != "needs_founder_manual_triage" and probability > 0
    ][:2]
    return {
        "tlc_source_suggestion": source["choice"]
        if flags.get("tlc_source_verified") is True and _decisive(source)
        else "requires_confirmation",
        "data_gap_origin_suggestion": origin["choice"]
        if flags.get("gap_origin_verified") is True and _decisive(origin)
        else "ambiguous_requires_customer_confirmation",
        "effort": {
            "status": "provisional",
            "zero_based_expected_score": effort["score"],
            "probabilities": effort["probabilities"],
        }
        if supported_effort
        else {"status": "unknown"},
        "external_followup": _signal(raw_answers["external_followup_required"]["noul"])
        if flags.get("external_followup_verified") is True
        else "uncertain",
        "correction_owner": {
            "status": "triage",
            "owner_role": None,
            "display_label": OWNER_LABELS["needs_founder_manual_triage"],
            "candidates": candidates,
            "reason_codes": ["calibration_not_approved", "ownership_unverified"],
        },
        "review_required": True,
    }


def _raw_answers(answers: JevAnswers) -> dict[str, Any]:
    """Reconstruct JSON form only after the transport's raw strict validation."""
    raw = {
        key: {
            "type": "choice",
            "choice": item.choice,
            "confidence": item.confidence,
            "probabilities": item.probabilities,
        }
        for key, item in answers.choices.items()
    }
    raw.update({key: {"type": "noul", "noul": item.probability} for key, item in answers.nouls.items()})
    raw.update(
        {
            key: {
                "type": "score",
                "score": item.score,
                "confidence": item.confidence,
                "probabilities": {str(i): p for i, p in item.probabilities.items()},
                "legend": {str(i): text for i, text in item.legend.items()},
            }
            for key, item in answers.scores.items()
        }
    )
    return raw


async def review_pilot_diagnostic(state: dict, decider: JevDecider | None = None) -> dict:
    """Review caller-sanitized aggregate state; no evidence flags or assignment authorization."""
    selected = decider if decider is not None else get_jev_decider()
    try:
        answers = await selected.ask_async(
            state,
            QUESTION_SETS["mode_a"],
            purpose="pilot_diagnostic",
            questions_version=QUESTIONS_VERSION,
            strict_answers=True,
        )
    except JevUnavailable as exc:
        return {
            "status": "unavailable",
            "reason": exc.reason,
            "suggestions": None,
            "evidence": None,
            "automatic_assignment_enabled": False,
        }
    return {
        "status": "review",
        "suggestions": summarize_diagnostic(_raw_answers(answers)),
        "evidence": answers.evidence.to_dict(),
        "automatic_assignment_enabled": False,
    }
