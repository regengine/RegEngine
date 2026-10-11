"""Break test: an open breaker must recover on a monotonic clock.

``_opened_at`` was a wall-clock reading. A step backward (NTP, a VM
resume, a manual correction) makes ``time.time() - _opened_at`` negative,
so the recovery timeout never elapses and the breaker stays open.
"""

from __future__ import annotations

from app.circuit_breaker import CircuitBreaker, CircuitState


def test_wall_clock_step_back_does_not_stick_breaker_open(monkeypatch):
    mono = {"t": 1000.0}
    wall = {"t": 1_700_000_000.0}
    monkeypatch.setattr("app.circuit_breaker.time.monotonic", lambda: mono["t"])
    monkeypatch.setattr("app.circuit_breaker.time.time", lambda: wall["t"])

    breaker = CircuitBreaker(name="fda_recalls", failure_threshold=1, recovery_timeout=30)
    breaker.record_failure()
    assert breaker.state == CircuitState.OPEN

    # Wall clock jumps back an hour. The monotonic clock moves forward
    # by exactly the recovery timeout.
    wall["t"] -= 3600
    mono["t"] += 30

    assert breaker.can_execute() is True
    assert breaker.state == CircuitState.HALF_OPEN


def test_recovery_still_works_when_monotonic_open_time_is_zero(monkeypatch):
    mono = {"t": 0.0}
    monkeypatch.setattr("app.circuit_breaker.time.monotonic", lambda: mono["t"])

    breaker = CircuitBreaker(name="fda_recalls", failure_threshold=1, recovery_timeout=5)
    breaker.record_failure()
    assert breaker.state == CircuitState.OPEN

    mono["t"] = 5.0
    assert breaker.can_execute() is True
    assert breaker.state == CircuitState.HALF_OPEN
