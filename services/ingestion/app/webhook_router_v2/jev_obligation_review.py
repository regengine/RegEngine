"""Jev second-judgment for the obligation-check path.

Context: the rules-based obligation check in ``validation.py`` can yield no
alerts for two very different reasons — the event genuinely satisfies every
rule, or the rules pass was skipped (DB error) and failed silently (M-5).
This module adds a second, independent judgment built on the established
``shared.jev`` stack: a Jev Noul answering "does this supply-chain event
warrant a human compliance review?" When the rules found nothing but Jev
says yes, the event gets a review flag.

A review flag is observability, NOT a compliance determination:
- it is logged at warning and counted in Prometheus,
- it is returned to the caller in the alerts list,
- it is NEVER written to ``fsma.compliance_alerts``. A model judgment must
  not pollute the compliance record.

Fail-open by design: ``JevUnavailable`` (disabled, no key, transport error)
or a malformed answer means "no review flag". Ingest never blocks on Jev.

Data boundary: the state carries KDE *presence* booleans and the CTE type
only — the same "header row, never whole rows" discipline as the existing
header-mapping integration. Raw KDE values (lot codes, quantities, names,
GLNs) are never transmitted to api.typesafe.ai.
"""

from __future__ import annotations

import logging
from typing import Any

from shared.jev.client import JevUnavailable, get_jev_decider

logger = logging.getLogger(__name__)

QUESTIONS_VERSION = "1"

# Noul probability at or above which an event is flagged for human review.
# Starting point — validate against real import traffic and adjust. Lower =
# more flags (more review load); higher = fewer.
JEV_REVIEW_THRESHOLD = 0.7

# Neutral question wording. Instructions state the exact condition and never
# prime an answer; a Noul has no competing options to load.
_REVIEW_INSTRUCTIONS = (
    "Does this supply-chain event warrant a human compliance review? "
    "Consider whether required traceability data appears to be missing or "
    "inconsistent for its event type, given which KDEs are present in "
    "`kde_present` and how many obligation rules were evaluated in "
    "`rules_evaluated`."
)


def _kde_presence(event: Any) -> dict[str, bool]:
    """KDE presence booleans only — never raw values (data boundary)."""

    def _present(value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return value.strip() != ""
        return True

    presence = {
        "traceability_lot_code": _present(event.traceability_lot_code),
        "product_description": _present(event.product_description),
        "quantity": _present(event.quantity),
        "unit_of_measure": _present(event.unit_of_measure),
        "location_name": _present(event.location_name),
        "location_gln": _present(event.location_gln),
    }
    for key, value in (event.kdes or {}).items():
        presence[str(key)] = _present(value)
    return presence


def review_event_for_alert_worthiness(event: Any, rules_evaluated: int) -> dict | None:
    """Second-judgment review flag for an event the rules passed clean.

    Returns a review-flag dict (severity "info", alert_type
    "jev_review_flag") when Jev's P(review-worthy) meets
    JEV_REVIEW_THRESHOLD, else None. The flag must not be written to
    fsma.compliance_alerts — see module docstring.
    """
    state = {
        "cte_type": event.cte_type.value,
        "kde_present": _kde_presence(event),
        "rules_evaluated": rules_evaluated,
    }
    questions = {"review": {"type": "noul", "instructions": _REVIEW_INSTRUCTIONS}}
    try:
        answers = get_jev_decider().ask(
            state,
            questions,
            purpose="obligation_review",
            questions_version=QUESTIONS_VERSION,
        )
        probability = answers.nouls["review"].probability
    except (JevUnavailable, KeyError, AttributeError, TypeError, ValueError) as exc:
        logger.debug("Jev obligation review unavailable: %s", type(exc).__name__)
        return None
    if probability < JEV_REVIEW_THRESHOLD:
        return None
    return {
        "severity": "info",
        "alert_type": "jev_review_flag",
        "message": (
            "Jev second-judgment: event warrants human compliance review "
            f"(rules found no alerts; review-worthy probability {probability:.2f})"
        ),
        "noul": round(probability, 4),
        "source": "jev-noul",
    }
