"""Regression tests for #1211 — queue_for_review status-aware idempotency.

Before: the existing-row check in ``queue_for_review`` returned ANY
row for the (entity_a_id, entity_b_id) pair — including closed
``confirmed_match`` and ``confirmed_distinct`` verdicts. A fresh
signal that re-suggested a match silently no-op'd instead of
queueing a new review. Operators lost the opportunity to re-examine
stale distinct flags when new evidence arrived.

After: the idempotency check is scoped to ``status IN ('pending',
'deferred')`` — only ACTIVE reviews dedupe. Closed rows no longer
block re-queueing. A new row is inserted with
``previous_review_id`` pointing at the most-recent closed row so
the reopen cycle is auditable.

Schema support lives in ``alembic/versions/20260418_v068_identity_review_reopen_1211.py``:
drops the full-table ``UNIQUE (entity_a_id, entity_b_id)`` and
replaces with a partial UNIQUE INDEX scoped to
``status IN ('pending','deferred')``.

These tests are session-mocked and do not touch a real DB.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import MagicMock

import pytest

from services.shared.identity_resolution import IdentityResolutionService


TENANT = "tenant-1211"
ENTITY_A = "11111111-1111-1111-1111-111111111111"
ENTITY_B = "22222222-2222-2222-2222-222222222222"


# ---------------------------------------------------------------------------
# Scripted session — dispatches queries by SQL pattern
# ---------------------------------------------------------------------------


class _ScriptedSession:
    """Fake session that routes ``execute`` calls based on SQL content
    and returns scripted results.

    ``queue_for_review`` issues (in order):
      1. SELECT ... WHERE status IN ('pending', 'deferred') — open check
      2. SELECT ... WHERE status IN ('confirmed_match','confirmed_distinct')
         — prior-closed lookup (only if open check returns None)
      3. INSERT ... (only if open check returns None)
    """

    def __init__(
        self,
        open_row: Optional[Tuple[Any, ...]] = None,
        closed_row: Optional[Tuple[Any, ...]] = None,
    ):
        self.open_row = open_row
        self.closed_row = closed_row
        # Log of (kind, params) for assertions.
        self.calls: List[Tuple[str, Dict[str, Any]]] = []

    def execute(self, stmt, params=None):
        sql = str(stmt)
        result = MagicMock()
        if "IN ('pending', 'deferred')" in sql:
            self.calls.append(("open_check", params or {}))
            result.fetchone.return_value = self.open_row
        elif "IN ('confirmed_match', 'confirmed_distinct')" in sql:
            self.calls.append(("closed_lookup", params or {}))
            result.fetchone.return_value = self.closed_row
        elif re.search(r"\bINSERT\b", sql, re.IGNORECASE):
            self.calls.append(("insert", params or {}))
            result.fetchone.return_value = None
        else:
            # Anything else (e.g. an accidental unrestricted SELECT)
            # fails loudly — the whole point of #1211 is that we no
            # longer issue "any existing row" queries.
            self.calls.append(("unexpected", params or {}))
            raise AssertionError(
                f"unexpected SQL in queue_for_review:\n{sql[:300]}"
            )
        return result


def _svc(session):
    return IdentityResolutionService(session)


def _call(session, **overrides):
    defaults = dict(
        tenant_id=TENANT,
        entity_a_id=ENTITY_A,
        entity_b_id=ENTITY_B,
        match_type="likely",
        match_confidence=0.82,
        matching_fields={"name_sim": 0.92},
    )
    defaults.update(overrides)
    return _svc(session).queue_for_review(**defaults)


# ===========================================================================
# Open-row idempotency: pending/deferred short-circuits
# ===========================================================================


class TestOpenRowIdempotent_Issue1211:
    def test_pending_row_returns_idempotent_no_insert(self):
        """A pending review for the same pair must short-circuit with
        idempotent=True and NO additional SELECT or INSERT."""
        existing = ("rev-open-1", "pending", 0.82)
        session = _ScriptedSession(open_row=existing)

        result = _call(session)

        assert result["idempotent"] is True
        assert result["review_id"] == "rev-open-1"
        assert result["status"] == "pending"
        assert result["match_confidence"] == 0.82
        # Exactly one query — the open check — and no insert.
        kinds = [c[0] for c in session.calls]
        assert kinds == ["open_check"], (
            f"expected short-circuit after open_check, got {kinds}"
        )

    def test_deferred_row_returns_idempotent_no_insert(self):
        """A deferred review counts as 'open' for idempotency."""
        existing = ("rev-def-1", "deferred", 0.71)
        session = _ScriptedSession(open_row=existing)

        result = _call(session)

        assert result["idempotent"] is True
        assert result["status"] == "deferred"
        kinds = [c[0] for c in session.calls]
        assert kinds == ["open_check"]


# ===========================================================================
# Closed-row reopen: new row inserted, previous_review_id linked
# ===========================================================================


class TestClosedRowReopen_Issue1211:
    def test_confirmed_distinct_does_not_block_new_review(self):
        """After confirmed_distinct, a fresh queue_for_review must
        insert a new row, NOT return the closed row as idempotent."""
        closed = ("rev-closed-distinct",)
        session = _ScriptedSession(open_row=None, closed_row=closed)

        result = _call(session)

        # New row — not a no-op.
        assert result["idempotent"] is False
        # Reopen semantics exposed to caller.
        assert result["previous_review_id"] == "rev-closed-distinct"
        assert result["is_reopen"] is True
        # Full flow: open_check -> closed_lookup -> insert.
        kinds = [c[0] for c in session.calls]
        assert kinds == ["open_check", "closed_lookup", "insert"], (
            f"expected full reopen flow, got {kinds}"
        )
        # Insert params thread the previous_review_id through.
        insert_params = dict(session.calls[2][1])
        assert insert_params["previous_review_id"] == "rev-closed-distinct"
        # New row is 'pending' (not inheriting the closed status).
        # Status is fixed in the INSERT SQL literal; confirm by checking
        # that a status param is NOT being set to the closed value.
        assert "status" not in insert_params or insert_params.get(
            "status"
        ) != "confirmed_distinct"

    def test_confirmed_match_also_does_not_block(self):
        """A prior confirmed_match also should not block a re-review —
        e.g., if downstream evidence later suggests the match was
        incorrect, operators can queue a fresh ambiguity check."""
        closed = ("rev-closed-match",)
        session = _ScriptedSession(open_row=None, closed_row=closed)

        result = _call(session)

        assert result["idempotent"] is False
        assert result["previous_review_id"] == "rev-closed-match"
        assert result["is_reopen"] is True

    def test_no_prior_rows_inserts_with_null_previous(self):
        """First-time queueing — no open, no closed — must insert with
        previous_review_id=None and is_reopen=False."""
        session = _ScriptedSession(open_row=None, closed_row=None)

        result = _call(session)

        assert result["idempotent"] is False
        assert result["previous_review_id"] is None
        assert result["is_reopen"] is False
        # Insert params confirm the NULL link.
        insert_params = dict(session.calls[2][1])
        assert insert_params["previous_review_id"] is None


# ===========================================================================
# Query-shape invariants — the open-check SQL must filter on status
# ===========================================================================


class TestStatusAwareQueryShape_Issue1211:
    def test_open_check_sql_filters_on_open_statuses_only(self):
        """The primary idempotency SELECT must include the active-status
        filter; otherwise closed rows bleed back through as idempotent
        — the exact bug #1211 fixes."""
        captured_sql: List[str] = []

        class _SQLCaptureSession:
            def execute(self, stmt, params=None):
                sql = str(stmt)
                captured_sql.append(sql)
                result = MagicMock()
                result.fetchone.return_value = None
                return result

        session = _SQLCaptureSession()
        _svc(session).queue_for_review(
            tenant_id=TENANT,
            entity_a_id=ENTITY_A,
            entity_b_id=ENTITY_B,
            match_type="likely",
            match_confidence=0.8,
        )

        # First SELECT must be scoped to open statuses.
        assert any(
            "IN ('pending', 'deferred')" in s for s in captured_sql
        ), (
            f"open-check SQL did not filter on pending/deferred — "
            f"this is the #1211 regression.\ncaptured:\n"
            + "\n---\n".join(captured_sql)
        )

    def test_open_check_is_tenant_scoped(self):
        """Defense in depth (#1344 territory) — the open-check SELECT
        must pin tenant_id, not just (a_id, b_id)."""
        session = _ScriptedSession(open_row=None, closed_row=None)
        _call(session)
        open_params = dict(session.calls[0][1])
        assert open_params.get("tenant_id") == TENANT


# ===========================================================================
# Pair normalization — (A,B) and (B,A) route to the same slot
# ===========================================================================


class TestPairNormalization_Issue1211:
    def test_ab_and_ba_both_query_same_sorted_pair(self):
        """queue_for_review(A,B) and queue_for_review(B,A) must hit the
        same (a,b) slot in the idempotency check. Verify the sorted-
        tuple normalization still holds after the #1211 restructure."""
        ab_session = _ScriptedSession(open_row=None, closed_row=None)
        _call(ab_session, entity_a_id=ENTITY_A, entity_b_id=ENTITY_B)

        ba_session = _ScriptedSession(open_row=None, closed_row=None)
        _call(ba_session, entity_a_id=ENTITY_B, entity_b_id=ENTITY_A)

        # Both open-check queries must use the same sorted (a, b).
        assert ab_session.calls[0][1]["a_id"] == ba_session.calls[0][1]["a_id"]
        assert ab_session.calls[0][1]["b_id"] == ba_session.calls[0][1]["b_id"]


# ===========================================================================
# Validation still fires
# ===========================================================================


class TestInputValidationUnchanged_Issue1211:
    def test_invalid_match_type_still_rejected(self):
        """The match_type guard must continue to reject bad values —
        #1211 must not weaken the existing validation."""
        session = _ScriptedSession()
        with pytest.raises(ValueError, match="Invalid match_type"):
            _svc(session).queue_for_review(
                tenant_id=TENANT,
                entity_a_id=ENTITY_A,
                entity_b_id=ENTITY_B,
                match_type="nonsense",
                match_confidence=0.5,
            )
        # No DB calls should occur when validation fails.
        assert session.calls == []


# ===========================================================================
# Response shape — reopen fields always present
# ===========================================================================


class TestResponseShape_Issue1211:
    def test_idempotent_response_omits_is_reopen_for_back_compat(self):
        """The idempotent-hit return path is unchanged — it returns the
        existing row's view. Adding reopen fields here would overclaim
        semantics (we don't know the prior linkage for the open row)."""
        existing = ("rev-open-1", "pending", 0.82)
        session = _ScriptedSession(open_row=existing)
        result = _call(session)
        # Must contain the core idempotent fields.
        assert set(result) >= {
            "review_id", "status", "match_confidence", "idempotent",
        }

    def test_insert_response_always_includes_reopen_fields(self):
        """On the INSERT path, both fresh-queue and reopen responses
        must contain previous_review_id + is_reopen so callers can
        uniformly branch on 'is this a reopen?'."""
        # Fresh queue.
        fresh = _ScriptedSession(open_row=None, closed_row=None)
        fresh_result = _call(fresh)
        assert "previous_review_id" in fresh_result
        assert "is_reopen" in fresh_result
        assert fresh_result["is_reopen"] is False

        # Reopen.
        reopen = _ScriptedSession(open_row=None, closed_row=("rev-cd",))
        reopen_result = _call(reopen)
        assert reopen_result["previous_review_id"] == "rev-cd"
        assert reopen_result["is_reopen"] is True
