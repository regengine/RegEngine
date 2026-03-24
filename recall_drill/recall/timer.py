"""24-hour SLA timer for FDA recall drills.

Per FSMA 204, firms must provide traceability information to the FDA
within 24 hours of a request.  This timer tracks elapsed wall-clock
time and fires threshold warnings at 50%, 75%, and 90%.
"""

from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Callable

logger = logging.getLogger(__name__)

FDA_SLA_SECONDS = 86_400  # 24 hours

# Warning thresholds expressed as fraction of the SLA
_THRESHOLDS: list[tuple[float, str]] = [
    (0.50, "50% of 24-hour SLA elapsed"),
    (0.75, "75% of 24-hour SLA elapsed — accelerate recall activities"),
    (0.90, "90% of 24-hour SLA elapsed — CRITICAL, near breach"),
]


class SLAStatus(str, Enum):
    NOT_STARTED = "not_started"
    MET = "met"
    AT_RISK = "at_risk"
    BREACHED = "breached"


class SLATimer:
    """Track elapsed time against the FDA 24-hour SLA.

    Parameters
    ----------
    sla_seconds:
        Override the SLA limit (default 86 400 = 24 h).  Useful for
        integration tests that cannot wait a full day.
    on_threshold:
        Optional callback invoked each time a threshold is crossed.
        Receives ``(fraction: float, message: str, elapsed: float)``.
    """

    def __init__(
        self,
        sla_seconds: float = FDA_SLA_SECONDS,
        on_threshold: Callable[[float, str, float], None] | None = None,
    ):
        self._sla = sla_seconds
        self._start: float | None = None
        self._end: float | None = None
        self._on_threshold = on_threshold
        self._fired_thresholds: set[float] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Begin timing."""
        self._start = time.perf_counter()
        self._end = None
        self._fired_thresholds.clear()
        logger.info("SLA timer started (limit=%ss)", self._sla)

    def stop(self) -> float:
        """Stop timing and return elapsed seconds."""
        if self._start is None:
            raise RuntimeError("Timer was never started")
        self._end = time.perf_counter()
        self._check_thresholds()
        logger.info(
            "SLA timer stopped: elapsed=%.3fs  status=%s",
            self.elapsed,
            self.status.value,
        )
        return self.elapsed

    def check(self) -> SLAStatus:
        """Check the current status and fire any threshold warnings.

        Call this periodically during long-running drills to get
        proactive warnings before the 24-hour window closes.
        """
        self._check_thresholds()
        return self.status

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def elapsed(self) -> float:
        """Seconds elapsed since ``start()``."""
        if self._start is None:
            return 0.0
        end = self._end or time.perf_counter()
        return end - self._start

    @property
    def remaining(self) -> float:
        """Seconds remaining until SLA breach (can go negative)."""
        return self._sla - self.elapsed

    @property
    def pct_elapsed(self) -> float:
        """Fraction of SLA consumed (0.0 – 1.0+)."""
        if self._sla <= 0:
            return 1.0
        return self.elapsed / self._sla

    @property
    def status(self) -> SLAStatus:
        if self._start is None:
            return SLAStatus.NOT_STARTED
        pct = self.pct_elapsed
        if pct > 1.0:
            return SLAStatus.BREACHED
        if pct >= 0.75:
            return SLAStatus.AT_RISK
        return SLAStatus.MET

    @property
    def sla_compliant(self) -> bool:
        return self.elapsed <= self._sla

    # ------------------------------------------------------------------
    # Threshold warnings
    # ------------------------------------------------------------------

    def _check_thresholds(self) -> None:
        pct = self.pct_elapsed
        for fraction, message in _THRESHOLDS:
            if pct >= fraction and fraction not in self._fired_thresholds:
                self._fired_thresholds.add(fraction)
                logger.warning(
                    "SLA THRESHOLD: %s (%.1f%% elapsed, %.1fs remaining)",
                    message,
                    pct * 100,
                    self.remaining,
                )
                if self._on_threshold:
                    self._on_threshold(fraction, message, self.elapsed)

        if pct >= 1.0 and 1.0 not in self._fired_thresholds:
            self._fired_thresholds.add(1.0)
            breach_msg = "24-hour SLA BREACHED — recall drill failed compliance window"
            logger.error(breach_msg)
            if self._on_threshold:
                self._on_threshold(1.0, breach_msg, self.elapsed)

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "elapsed_seconds": round(self.elapsed, 3),
            "remaining_seconds": round(max(0.0, self.remaining), 3),
            "pct_elapsed": round(self.pct_elapsed * 100, 2),
            "sla_limit_seconds": self._sla,
            "sla_status": self.status.value,
            "sla_compliant": self.sla_compliant,
            "thresholds_fired": sorted(self._fired_thresholds),
        }
