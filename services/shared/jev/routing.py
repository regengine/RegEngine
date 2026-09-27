"""Confidence-gated routing for Jev answers.

A Choice answer carries a probability distribution over its options and a
``confidence`` in ``[0, 1]`` describing how concentrated that distribution is
(1.0: all probability on one option; 0.0: spread evenly). The answer says
*what*; confidence says *whether to act*. RegEngine keeps that policy in code
and in one place, following the vendor's guidance that thresholds are risk
dependent and should be reviewed as constants rather than scattered.

Bands
-----
``AUTO_APPLY``  confidence >= ``auto_apply``: the suggestion may be applied
                without a human, subject to the caller's own deterministic
                checks (schema validation still runs).
``REVIEW``      ``review`` <= confidence < ``auto_apply``: surface to a human
                as a suggestion; never apply automatically.
``REJECT``      confidence < ``review``: discard; the model has no clear read.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ConfidenceBand(str, Enum):
    AUTO_APPLY = "auto_apply"
    REVIEW = "review"
    REJECT = "reject"


@dataclass(frozen=True)
class ConfidenceThresholds:
    """Lower bounds for the ``AUTO_APPLY`` and ``REVIEW`` bands."""

    auto_apply: float = 0.90
    review: float = 0.50

    def __post_init__(self) -> None:
        for name in ("auto_apply", "review"):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be within [0, 1], got {value!r}")
        if self.review > self.auto_apply:
            raise ValueError(f"review ({self.review}) must not exceed auto_apply ({self.auto_apply})")


def band_for_confidence(confidence: float, thresholds: ConfidenceThresholds) -> ConfidenceBand:
    """Map a Choice/Score ``confidence`` to the band that governs what code may do with it."""
    if confidence >= thresholds.auto_apply:
        return ConfidenceBand.AUTO_APPLY
    if confidence >= thresholds.review:
        return ConfidenceBand.REVIEW
    return ConfidenceBand.REJECT
