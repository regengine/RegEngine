"""24-hour SLA timer for FDA recall drills."""

from __future__ import annotations

import time
from enum import Enum


FDA_SLA_SECONDS = 86400  # 24 hours


class SLAStatus(str, Enum):
    MET = "met"
    AT_RISK = "at_risk"
    BREACHED = "breached"


class SLATimer:
    """Track elapsed time against the FDA 24-hour SLA."""

    def __init__(self):
        self._start: float | None = None
        self._end: float | None = None

    def start(self) -> None:
        self._start = time.perf_counter()
        self._end = None

    def stop(self) -> float:
        if self._start is None:
            raise RuntimeError("Timer not started")
        self._end = time.perf_counter()
        return self.elapsed

    @property
    def elapsed(self) -> float:
        if self._start is None:
            return 0.0
        end = self._end or time.perf_counter()
        return end - self._start

    @property
    def status(self) -> SLAStatus:
        e = self.elapsed
        if e <= FDA_SLA_SECONDS * 0.8:
            return SLAStatus.MET
        if e <= FDA_SLA_SECONDS:
            return SLAStatus.AT_RISK
        return SLAStatus.BREACHED

    def to_dict(self) -> dict:
        return {
            "elapsed_seconds": round(self.elapsed, 3),
            "sla_limit_seconds": FDA_SLA_SECONDS,
            "sla_status": self.status.value,
            "sla_compliant": self.elapsed <= FDA_SLA_SECONDS,
        }
