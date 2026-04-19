"""Regression tests for #1365 — rules-engine relational-evaluator cache.

Problem: each relational evaluator (``temporal_order``,
``identity_consistency``, ``mass_balance``) called
``fetch_related_events`` with identical arguments. An event with all
three relational rules applicable therefore issued the same SELECT
three times. For a batch of 100 events that is 200 extra redundant
round-trips.

Fix: ``RulesEngine`` now pre-fetches the per-event related-events list
ONCE and forwards it into each relational evaluator via a
``related_events`` kwarg. Evaluators short-circuit when the cache is
supplied. When the cache is ``None`` the evaluator falls back to the
old per-call fetch, preserving backward compatibility for callers that
bypass the engine.

These tests are session-mocked — they do not touch a real DB.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import MagicMock

import pytest

from shared.rules.types import RuleDefinition
from shared.rules.engine import RulesEngine
from shared.rules.evaluators.relational import (
    evaluate_identity_consistency,
    evaluate_mass_balance,
    evaluate_temporal_order,
)


# ---------------------------------------------------------------------------
# Session / engine fixtures
# ---------------------------------------------------------------------------


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return list(self._rows)


class _CountingSession:
    """Fake session that counts ``execute`` calls and returns canned
    ``fetch_related_events``-shaped rows.

    Rows have 6 columns in the order
    ``(event_id, event_type, event_timestamp, product_reference,
       quantity, unit_of_measure)`` — matching
    ``fetch_related_events``' unpack.
    """

    def __init__(self, rows: Optional[List[Tuple[Any, ...]]] = None):
        self._rows = rows or []
        self.execute_count = 0
        # Last-seen bind params, for inspection in assertions.
        self.last_params: Optional[Dict[str, Any]] = None

    def execute(self, _stmt, params: Optional[Dict[str, Any]] = None):
        self.execute_count += 1
        self.last_params = params
        return _Rows(self._rows)


def _make_rule(
    rule_id: str,
    eval_type: str,
    cte_type: str = "receiving",
) -> RuleDefinition:
    """Minimal rule whose applicability and evaluation_logic are just
    enough to trip the engine dispatcher."""
    return RuleDefinition(
        rule_id=rule_id,
        rule_version=1,
        title=f"Rule {rule_id}",
        description="",
        severity="critical",
        category="cross_event_integrity",
        applicability_conditions={
            "cte_types": [cte_type],
            "ftl_scope": ["ALL"],
        },
        citation_reference="21 CFR §1.1310",
        effective_date=date(2026, 1, 1),
        retired_date=None,
        evaluation_logic={"type": eval_type},
        failure_reason_template="",
        remediation_suggestion="",
    )


def _make_event(**overrides) -> Dict[str, Any]:
    evt = {
        "event_id": "11111111-1111-1111-1111-111111111111",
        "event_type": "receiving",
        "traceability_lot_code": "TLC-A",
        "product_reference": "Romaine",
        "quantity": 100.0,
        "unit_of_measure": "lbs",
        "event_timestamp": datetime(2026, 4, 10, 12, 0, tzinfo=timezone.utc),
        "ftl_covered": True,
        "ftl_category": "Leafy Greens",
    }
    evt.update(overrides)
    return evt


def _engine(session, rules: List[RuleDefinition]) -> RulesEngine:
    """Build an engine with a pre-seeded fresh cache so tests don't
    hit the DB for rule-definition loading."""
    import time as _time

    engine = RulesEngine.__new__(RulesEngine)
    engine.session = session
    engine._cache_ttl_seconds = 60
    engine._rules_cache = rules
    engine._rules_cache_loaded_at = _time.monotonic()
    return engine


# ===========================================================================
# Core #1365 behavior — one fetch per event, not per rule
# ===========================================================================


class TestPrefetchOncePerEvent_Issue1365:
    def test_three_relational_rules_trigger_one_fetch(self):
        """With 3 applicable relational rules on one event, the engine
        must hit fetch_related_events exactly once — not three times."""
        rules = [
            _make_rule("r-temp", "temporal_order"),
            _make_rule("r-ident", "identity_consistency"),
            _make_rule("r-mass", "mass_balance"),
        ]
        session = _CountingSession(rows=[])  # no related events
        engine = _engine(session, rules)

        summary = engine.evaluate_event(
            _make_event(), persist=False, tenant_id="tenant-a"
        )

        assert summary.total_rules == 3
        # The critical assertion — one SELECT, not three.
        assert session.execute_count == 1, (
            f"expected 1 fetch for 3 relational rules, got "
            f"{session.execute_count} — #1365 pre-fetch not applied"
        )

    def test_two_relational_rules_trigger_one_fetch(self):
        rules = [
            _make_rule("r-temp", "temporal_order"),
            _make_rule("r-ident", "identity_consistency"),
        ]
        session = _CountingSession(rows=[])
        engine = _engine(session, rules)

        engine.evaluate_event(
            _make_event(), persist=False, tenant_id="tenant-a"
        )

        assert session.execute_count == 1

    def test_prefetch_params_include_tenant_and_tlc(self):
        """Pre-fetch must use authenticated tenant_id (not any payload
        value) and the event's TLC — the same invariant #1344 enforces."""
        rules = [_make_rule("r-temp", "temporal_order")]
        session = _CountingSession(rows=[])
        engine = _engine(session, rules)

        evt = _make_event(
            traceability_lot_code="TLC-XYZ",
            tenant_id="ATTACKER-TENANT",  # payload — must be ignored
        )
        engine.evaluate_event(evt, persist=False, tenant_id="REAL-TENANT")

        assert session.last_params is not None
        assert session.last_params["tenant_id"] == "REAL-TENANT"
        assert session.last_params["tlc"] == "TLC-XYZ"

    def test_cached_list_passes_through_to_evaluator(self):
        """The row fetched once must be visible to each evaluator —
        proved by feeding rows that would fail temporal_order and
        asserting the failure fires via the cached list (not a refetch).

        Lifecycle order (services/shared/rules/uom.py): harvesting=0,
        cooling=1, initial_packing=2, first_land_based_receiving=3,
        transformation=4, shipping=5, receiving=6.

        Violation we stage: current=receiving (stage 6) at 2026-04-01,
        related=shipping (stage 5 — earlier stage) at 2026-04-10
        (LATER in time). Earlier-stage shipping happening AFTER the
        later-stage receiving is a chronology paradox.
        """
        related_row = (
            "22222222-2222-2222-2222-222222222222",  # event_id
            "shipping",                              # event_type (earlier stage)
            datetime(2026, 4, 10, 8, 0, tzinfo=timezone.utc),  # LATER ts
            "Romaine",                               # product_reference
            100.0,                                   # quantity
            "lbs",                                   # uom
        )
        session = _CountingSession(rows=[related_row])
        engine = _engine(
            session,
            [
                _make_rule("r-temp", "temporal_order"),
                _make_rule("r-ident", "identity_consistency"),
            ],
        )

        # Current event: receiving (stage 6) at 2026-04-01 (EARLIER ts).
        evt = _make_event(
            event_timestamp=datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc),
        )
        summary = engine.evaluate_event(
            evt, persist=False, tenant_id="tenant-a"
        )

        # One pre-fetch, not two.
        assert session.execute_count == 1
        # Temporal_order must have seen the cached row and failed.
        temporal_result = next(
            r for r in summary.results if r.rule_id == "r-temp"
        )
        assert temporal_result.result == "fail", (
            "temporal_order evaluator must consume the pre-fetched list "
            "and still detect the chronology violation "
            f"(got result={temporal_result.result!r}, "
            f"why_failed={temporal_result.why_failed!r})"
        )


# ===========================================================================
# Skip conditions — precondition misses cause None cache and evaluator skip
# ===========================================================================


class TestPrefetchSkipConditions_Issue1365:
    def test_no_fetch_when_no_relational_rule_applicable(self):
        """A stateless rule set should not trigger any related-events
        fetch — pre-fetch is purely an optimization for the relational
        dispatch path."""
        rules = [_make_rule("r-fp", "field_presence")]
        session = _CountingSession(rows=[])
        engine = _engine(session, rules)

        engine.evaluate_event(
            _make_event(), persist=False, tenant_id="tenant-a"
        )

        assert session.execute_count == 0

    def test_no_fetch_when_no_tenant_id(self):
        """Without a tenant_id the engine must refuse to pre-fetch —
        the relational rule will error at dispatch anyway."""
        rules = [_make_rule("r-temp", "temporal_order")]
        session = _CountingSession(rows=[])
        engine = _engine(session, rules)

        # No tenant_id — relational rule errors, no pre-fetch.
        summary = engine.evaluate_event(
            _make_event(), persist=False, tenant_id=None
        )
        assert session.execute_count == 0
        assert summary.errored == 1
        assert summary.results[0].result == "error"

    def test_no_fetch_when_event_has_no_tlc(self):
        """TLC-less events cause evaluators to skip; no reason to
        pre-fetch."""
        rules = [_make_rule("r-temp", "temporal_order")]
        session = _CountingSession(rows=[])
        engine = _engine(session, rules)

        evt = _make_event(traceability_lot_code="")
        summary = engine.evaluate_event(evt, persist=False, tenant_id="t1")

        assert session.execute_count == 0
        # Evaluator itself still returns skip.
        assert summary.skipped == 1

    def test_prefetch_helper_returns_none_on_missing_preconditions(self):
        """Direct-unit coverage of ``_prefetch_related_events``'s guard
        clauses — each should short-circuit to None without touching
        session.execute."""
        session = _CountingSession(rows=[])
        engine = _engine(session, [])
        relational_rule = _make_rule("r", "temporal_order")

        # No tenant_id
        assert engine._prefetch_related_events(
            _make_event(), [relational_rule], tenant_id=None
        ) is None
        # No TLC
        assert engine._prefetch_related_events(
            _make_event(traceability_lot_code=""),
            [relational_rule], tenant_id="t1",
        ) is None
        # No relational rule
        assert engine._prefetch_related_events(
            _make_event(),
            [_make_rule("r-fp", "field_presence")],
            tenant_id="t1",
        ) is None
        # Empty applicable list
        assert engine._prefetch_related_events(
            _make_event(), [], tenant_id="t1"
        ) is None

        assert session.execute_count == 0

    def test_prefetch_helper_returns_none_when_session_absent(self):
        engine = _engine(None, [])
        assert engine._prefetch_related_events(
            _make_event(),
            [_make_rule("r", "temporal_order")],
            tenant_id="t1",
        ) is None


# ===========================================================================
# Failure handling — pre-fetch error must not crash evaluation
# ===========================================================================


class TestPrefetchFailureFallback_Issue1365:
    def test_prefetch_db_error_does_not_abort_evaluation(self):
        """If the pre-fetch raises, the engine must log and fall back
        to per-evaluator fetch so one DB hiccup doesn't lose the whole
        evaluation."""
        class _BoomThenOK:
            def __init__(self):
                self.calls = 0

            def execute(self, _stmt, params=None):
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("transient DB error on pre-fetch")
                return _Rows([])

        session = _BoomThenOK()
        engine = _engine(session, [_make_rule("r-temp", "temporal_order")])

        # Must NOT raise — eval proceeds, evaluator falls back to self-fetch.
        summary = engine.evaluate_event(
            _make_event(), persist=False, tenant_id="t1"
        )
        # Pre-fetch attempt (1) + evaluator self-fetch (2).
        assert session.calls == 2
        # No crash — temporal_order returned pass (no related events).
        assert summary.results[0].result == "pass"


# ===========================================================================
# Batch path — evaluate_events_batch also caches per event
# ===========================================================================


class TestBatchPrefetch_Issue1365:
    def test_batch_of_n_events_does_n_fetches_not_n_times_k(self):
        """For N events each with K relational rules, fetches must be
        at most N, not N*K. Previously we issued N*K queries."""
        rules = [
            _make_rule("r-temp", "temporal_order"),
            _make_rule("r-ident", "identity_consistency"),
            _make_rule("r-mass", "mass_balance"),
        ]

        class _BatchSession:
            def __init__(self, rule_rows):
                self.rule_rows = rule_rows
                self.calls = []  # list of (sql_substr, params)

            def execute(self, stmt, params=None):
                sql = str(stmt).lower()
                if "rule_definitions" in sql:
                    return _Rows(self.rule_rows)
                # It's a related-events fetch.
                self.calls.append(("related", params))
                return _Rows([])

        # Seed rule-definition load rows so load_active_rules works.
        rule_rows = [
            (
                r.rule_id, r.rule_version, r.title, r.description,
                r.severity, r.category, r.applicability_conditions,
                r.citation_reference, r.effective_date, r.retired_date,
                r.evaluation_logic, r.failure_reason_template,
                r.remediation_suggestion,
            )
            for r in rules
        ]
        session = _BatchSession(rule_rows)
        engine = RulesEngine(session, cache_ttl_seconds=0)  # disable cache

        events = [
            _make_event(
                event_id=f"evt-{i}",
                traceability_lot_code=f"TLC-{i}",
            )
            for i in range(5)
        ]
        engine.evaluate_events_batch(events, tenant_id="t1", persist=False)

        related_fetches = [c for c in session.calls if c[0] == "related"]
        # One fetch per event, not 3 per event.
        assert len(related_fetches) == 5, (
            f"expected 5 fetches (one per event), got "
            f"{len(related_fetches)} — #1365 not applied in batch path"
        )

        # Each fetch's TLC must match its event (no bleed between events).
        tlcs = sorted(c[1]["tlc"] for c in related_fetches)
        assert tlcs == [f"TLC-{i}" for i in range(5)]


# ===========================================================================
# Direct-evaluator backward compatibility
# ===========================================================================


class TestEvaluatorBackwardCompat_Issue1365:
    """Evaluators called directly (no engine) must still self-fetch
    when the ``related_events`` kwarg is omitted. This preserves the
    pre-#1365 contract for callers that bypass RulesEngine."""

    def test_temporal_order_self_fetches_without_kwarg(self):
        session = _CountingSession(rows=[])
        rule = _make_rule("r", "temporal_order")
        evaluate_temporal_order(
            _make_event(), rule.evaluation_logic, rule, session,
            tenant_id="t1",
        )
        assert session.execute_count == 1

    def test_temporal_order_uses_kwarg_when_provided(self):
        """With the cache kwarg present, the evaluator must NOT fetch —
        it must read the list given to it."""
        session = _CountingSession(rows=[])  # would raise if used
        rule = _make_rule("r", "temporal_order")
        evaluate_temporal_order(
            _make_event(), rule.evaluation_logic, rule, session,
            tenant_id="t1",
            related_events=[],  # explicit empty cache
        )
        assert session.execute_count == 0

    def test_identity_consistency_uses_kwarg_when_provided(self):
        session = _CountingSession(rows=[])
        rule = _make_rule("r", "identity_consistency")
        evaluate_identity_consistency(
            _make_event(), rule.evaluation_logic, rule, session,
            tenant_id="t1",
            related_events=[],
        )
        assert session.execute_count == 0

    def test_mass_balance_uses_kwarg_when_provided(self):
        session = _CountingSession(rows=[])
        rule = _make_rule("r", "mass_balance")
        evaluate_mass_balance(
            _make_event(), rule.evaluation_logic, rule, session,
            tenant_id="t1",
            related_events=[],
        )
        assert session.execute_count == 0

    def test_kwarg_empty_list_is_treated_as_no_related(self):
        """An explicit ``[]`` must take the same 'no related events'
        branch the old code took when the fetch returned an empty list
        — result=pass with a "no related events" evidence note."""
        rule = _make_rule("r", "temporal_order")
        result = evaluate_temporal_order(
            _make_event(), rule.evaluation_logic, rule, MagicMock(),
            tenant_id="t1",
            related_events=[],
        )
        assert result.result == "pass"
        # Sanity-check: the evidence note matches the existing copy.
        assert any(
            "No related events" in str(e.get("note", ""))
            for e in (result.evidence_fields_inspected or [])
        )


# ===========================================================================
# Contract: the optimization is observable in call count, not semantics.
# ===========================================================================


class TestSemanticsUnchanged_Issue1365:
    def test_result_identical_with_and_without_cache(self):
        """Running the same rule against the same event must yield the
        same result whether the engine pre-fetched or the evaluator
        self-fetched. The optimization must be behavior-preserving."""
        row = (
            "22222222-2222-2222-2222-222222222222",
            "shipping",
            datetime(2026, 4, 1, 8, 0, tzinfo=timezone.utc),
            "Romaine",
            100.0,
            "lbs",
        )

        # Case A: via engine (pre-fetches).
        session_a = _CountingSession(rows=[row])
        engine_a = _engine(
            session_a, [_make_rule("r-temp", "temporal_order")]
        )
        summary_a = engine_a.evaluate_event(
            _make_event(), persist=False, tenant_id="t1"
        )
        # Case B: direct evaluator (self-fetches).
        session_b = _CountingSession(rows=[row])
        rule = _make_rule("r-temp", "temporal_order")
        result_b = evaluate_temporal_order(
            _make_event(), rule.evaluation_logic, rule, session_b,
            tenant_id="t1",
        )

        assert summary_a.results[0].result == result_b.result
        assert summary_a.results[0].rule_id == result_b.rule_id
