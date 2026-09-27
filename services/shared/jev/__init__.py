"""TypeSafe AI "Jev" integration for RegEngine.

Jev is a System One model: it answers typed questions (``Choice``, ``Score``,
``Noul``) about a piece of state with calibrated probabilities instead of
generating text. RegEngine uses it for narrow, reviewable judgments inside the
ingestion spine (``ingest -> normalize -> validate -> persist evidence ->
export``) and keeps every decision in code, gated by confidence.

Public surface:

* :class:`JevSettings` - environment-driven configuration (optional feature).
* :class:`JevDecider` / :func:`get_jev_decider` - fail-open client wrapper.
* :class:`JevAnswers`, :class:`JevEvidence` - typed answers plus provenance.
* :class:`JevUnavailable` - raised whenever the caller must use its
  deterministic path instead.
* :func:`band_for_confidence` - the confidence policy shared by all callers.
"""

from .client import (
    ChoiceResult,
    JevAnswers,
    JevDecider,
    JevEvidence,
    JevUnavailable,
    NoulResult,
    ScoreResult,
    classify_error,
    get_jev_decider,
    guard_sdk_logging,
    reset_jev_decider,
)
from .routing import ConfidenceBand, ConfidenceThresholds, band_for_confidence
from .settings import JevSettings

__all__ = [
    "ChoiceResult",
    "ConfidenceBand",
    "ConfidenceThresholds",
    "JevAnswers",
    "JevDecider",
    "JevEvidence",
    "JevSettings",
    "JevUnavailable",
    "NoulResult",
    "ScoreResult",
    "band_for_confidence",
    "classify_error",
    "get_jev_decider",
    "guard_sdk_logging",
    "reset_jev_decider",
]
