"""Live confidence-threshold access for the NLP consumer (#1260).

Split out of the original ``app/consumer.py`` module. All names are
re-exported from ``app.consumer`` for backward compatibility.
"""

from __future__ import annotations

import structlog

from ..config import settings

logger = structlog.get_logger("nlp-consumer")

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
