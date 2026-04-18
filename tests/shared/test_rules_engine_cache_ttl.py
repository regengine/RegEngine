"""Tests for #1371 — rules-engine cache TTL + explicit invalidation.

Before: ``RulesEngine._rules_cache`` was populated once per instance
and never invalidated. A long-lived instance (e.g. a worker holding
one engine across many events) would continue serving stale rules
after an admin edit until process restart.

After: cache carries a monotonic-clock load timestamp and is
considered fresh only within ``cache_ttl_seconds`` (default 60).
Stale cache is transparently reloaded. Callers that mutate
``rule_definitions`` may call ``invalidate_cache()`` to force an
immediate reload on the next ``get_applicable_rules``.

These tests are session-mocked and do not touch a real DB.
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any, Dict, List, Tuple
from unittest.mock import MagicMock

import pytest

from shared.rules.engine import RulesEngine


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return list(self._rows)


class _RecordingSession:
    """Minimal fake session that counts ``execute`` calls and returns
    pre-programmed rows shaped like ``load_active_rules`` expects."""

    def __init__(self, row_sets: List[List[Tuple[Any, ...]]]):
        self._row_sets = row_sets
        self.call_count = 0

    def execute(self, _stmt):
        idx = min(self.call_count, len(self._row_sets) - 1)
        rows = self._row_sets[idx]
        self.call_count += 1
        return _Rows(rows)


_RULE_ROW = (
    "rule-001",  # rule_id
    1,           # rule_version
    "Test Rule", # title
    "desc",      # description
    "critical",  # severity
    "kde_presence",
    {"cte_types": ["receiving"], "ftl_scope": ["ALL"]},
    "21 CFR x.x",
    None,
    None,
    {"type": "field_presence", "field": "kdes.test"},
    "fail",
    "fix it",
)


class TestCacheFreshness_Issue1371:
    def test_first_call_populates_cache(self):
        session = _RecordingSession([[_RULE_ROW]])
        engine = RulesEngine(session)
        assert engine._rules_cache is None

        rules = engine.get_applicable_rules(
            event_type="receiving", event_is_ftl=True,
        )
        assert len(rules) == 1
        assert session.call_count == 1
        assert engine._rules_cache is not None

    def test_second_call_within_ttl_hits_cache(self):
        """Within TTL, repeated calls must not hit the DB again."""
        session = _RecordingSession([[_RULE_ROW]])
        engine = RulesEngine(session, cache_ttl_seconds=60)

        engine.get_applicable_rules(event_type="receiving", event_is_ftl=True)
        engine.get_applicable_rules(event_type="receiving", event_is_ftl=True)
        engine.get_applicable_rules(event_type="receiving", event_is_ftl=True)

        assert session.call_count == 1, (
            "cache must satisfy the 2nd and 3rd calls; DB was hit "
            f"{session.call_count} times"
        )

    def test_expired_cache_triggers_reload(self, monkeypatch):
        """After ``cache_ttl_seconds`` elapses, the next call reloads
        from the DB (#1371 — no more stale-until-restart)."""
        # First load returns one rule; simulated second load returns
        # a different count so the test can prove the reload happened.
        session = _RecordingSession([[_RULE_ROW], [_RULE_ROW, _RULE_ROW]])
        engine = RulesEngine(session, cache_ttl_seconds=1)

        # Freeze "now" for deterministic aging.
        t = [100.0]

        def _fake_monotonic():
            return t[0]

        monkeypatch.setattr("time.monotonic", _fake_monotonic)

        engine.get_applicable_rules(event_type="receiving", event_is_ftl=True)
        assert session.call_count == 1

        # Within TTL — still cached.
        t[0] = 100.5
        engine.get_applicable_rules(event_type="receiving", event_is_ftl=True)
        assert session.call_count == 1

        # Past TTL — reload fires.
        t[0] = 101.6
        rules = engine.get_applicable_rules(event_type="receiving", event_is_ftl=True)
        assert session.call_count == 2
        assert len(rules) == 2  # second load's payload

    def test_ttl_zero_disables_cache(self):
        """``cache_ttl_seconds=0`` is an escape hatch for tests/tools
        that want every call to reload — the cache is effectively off."""
        session = _RecordingSession([[_RULE_ROW]] * 5)
        engine = RulesEngine(session, cache_ttl_seconds=0)

        for _ in range(3):
            engine.get_applicable_rules(
                event_type="receiving", event_is_ftl=True,
            )
        assert session.call_count == 3

    def test_empty_rule_set_is_cached_not_treated_as_miss(self):
        """A tenant with zero seeded rules should not re-hit the DB on
        every call. Freshness — not non-None — is the gate."""
        session = _RecordingSession([[]])
        engine = RulesEngine(session, cache_ttl_seconds=60)

        engine.get_applicable_rules(event_type="receiving", event_is_ftl=True)
        engine.get_applicable_rules(event_type="receiving", event_is_ftl=True)
        assert session.call_count == 1, (
            "empty-list cache must be treated as populated, not as miss"
        )


class TestInvalidateCache_Issue1371:
    def test_invalidate_forces_next_reload(self):
        """``invalidate_cache`` clears the load timestamp so the next
        ``get_applicable_rules`` call re-hits the DB."""
        session = _RecordingSession([[_RULE_ROW], [_RULE_ROW, _RULE_ROW]])
        engine = RulesEngine(session, cache_ttl_seconds=60)

        engine.get_applicable_rules(event_type="receiving", event_is_ftl=True)
        assert session.call_count == 1

        engine.invalidate_cache()
        assert engine._rules_cache is None
        assert engine._rules_cache_loaded_at is None

        # Same TTL window — without invalidation would have hit cache.
        rules = engine.get_applicable_rules(event_type="receiving", event_is_ftl=True)
        assert session.call_count == 2
        assert len(rules) == 2

    def test_invalidate_on_cold_instance_is_noop(self):
        """Calling invalidate before any load is harmless."""
        session = _RecordingSession([[_RULE_ROW]])
        engine = RulesEngine(session)
        engine.invalidate_cache()  # no exception
        assert engine._rules_cache is None
        assert session.call_count == 0
