"""
Regression coverage for ``app/audit.py`` — closes the 98% gap that survived
the EPIC-K hygiene tests in ``test_epic_k_audit_hygiene.py``.

The audit logger is the FSMA 204 tamper-evidence backbone (21 CFR Part 1,
Subpart S) and the ISO 27001 12.4.1/2/3 anchor. Any silent failure in
``log_event`` — the user-agent truncation branch (storage bloat) or the
exception swallow branch (tamper-proofing) — erodes the chain we sell as
audit-ready.

These tests pin two branches with mocked SQLAlchemy sessions so they run
without a live DB:

* Line 156 — ``actor_ua`` longer than 512 chars is truncated before insert.
* Lines 192-199 — exception fallthrough logs and returns ``None`` instead
  of leaking the raw SQLAlchemy error to the caller.

Tracks GitHub issue #1342.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock
from uuid import UUID

import pytest

service_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("sqlalchemy")

from app.audit import AuditLogger  # noqa: E402


TENANT = UUID("00000000-0000-0000-0000-000000000099")
ACTOR = UUID("00000000-0000-0000-0000-000000000001")


def _mk_session(*, prev_hash: str | None = None, add_side_effect=None):
    """Build a mock SQLAlchemy session that behaves like a real session."""
    session = MagicMock()
    # _get_prev_hash path: session.execute(...).scalar_one_or_none() -> prev_hash
    session.execute.return_value.scalar_one_or_none.return_value = prev_hash
    if add_side_effect is not None:
        session.add.side_effect = add_side_effect
    # flush() must assign an id onto the added entry so log_event can return it.
    # We hook flush by having session.add capture the entry, then flush set id=17.
    added: list = []

    def _capture(entry):
        added.append(entry)
        if add_side_effect is not None:
            raise add_side_effect

    def _assign_id():
        if added:
            added[0].id = 17

    # Only override if no custom side_effect
    if add_side_effect is None:
        session.add.side_effect = _capture
        session.flush.side_effect = _assign_id
    session._added = added  # for test assertions
    return session


# ---------------------------------------------------------------------------
# Line 156 — user agent truncation
# ---------------------------------------------------------------------------


class TestUserAgentTruncation:

    def test_long_user_agent_truncated_to_512(self):
        """A user-agent > 512 chars must be truncated before DB insert
        to prevent storage bloat (line 155-156)."""
        session = _mk_session(prev_hash=None)
        oversized = "x" * 5000

        new_id = AuditLogger.log_event(
            db=session,
            tenant_id=TENANT,
            event_type="auth.login",
            action="login",
            event_category="security",
            actor_id=ACTOR,
            actor_ua=oversized,
        )

        assert new_id == 17
        entry = session._added[0]
        assert len(entry.actor_ua) == 512
        assert entry.actor_ua == "x" * 512

    def test_short_user_agent_preserved_untruncated(self):
        """A user-agent ≤ 512 chars must NOT be truncated — pins that
        the guard is ``> 512`` and not ``>= 512``."""
        session = _mk_session(prev_hash=None)
        short_ua = "Mozilla/5.0 (normal browser UA)"

        AuditLogger.log_event(
            db=session,
            tenant_id=TENANT,
            event_type="auth.login",
            action="login",
            event_category="security",
            actor_ua=short_ua,
        )

        entry = session._added[0]
        assert entry.actor_ua == short_ua

    def test_user_agent_exactly_512_preserved(self):
        """Boundary: exactly 512 chars should NOT be truncated."""
        session = _mk_session(prev_hash=None)
        ua = "y" * 512

        AuditLogger.log_event(
            db=session,
            tenant_id=TENANT,
            event_type="auth.login",
            action="login",
            event_category="security",
            actor_ua=ua,
        )
        entry = session._added[0]
        assert len(entry.actor_ua) == 512
        assert entry.actor_ua == ua

    def test_user_agent_513_chars_truncated(self):
        """Boundary: exactly one char over the limit must be truncated."""
        session = _mk_session(prev_hash=None)
        ua = "z" * 513

        AuditLogger.log_event(
            db=session,
            tenant_id=TENANT,
            event_type="auth.login",
            action="login",
            event_category="security",
            actor_ua=ua,
        )
        entry = session._added[0]
        assert len(entry.actor_ua) == 512

    def test_none_user_agent_preserved(self):
        """``actor_ua=None`` must bypass the truncation branch cleanly."""
        session = _mk_session(prev_hash=None)

        AuditLogger.log_event(
            db=session,
            tenant_id=TENANT,
            event_type="auth.login",
            action="login",
            event_category="security",
            actor_ua=None,
        )
        entry = session._added[0]
        assert entry.actor_ua is None


# ---------------------------------------------------------------------------
# Lines 192-199 — exception fallthrough returns None
# ---------------------------------------------------------------------------


class TestLogEventExceptionFallthrough:

    @pytest.mark.parametrize(
        "exc",
        [
            ValueError("bad value"),
            RuntimeError("sqlalchemy boom"),
            OSError("disk full"),
            AttributeError("missing attr"),
            TypeError("wrong type"),
            KeyError("missing key"),
        ],
    )
    def test_handled_exceptions_return_none(self, exc):
        """Each caught exception type must log-and-swallow, returning None
        so callers don't mask real user-visible errors behind audit bugs
        (lines 192-199)."""
        session = _mk_session(add_side_effect=exc)
        # With add_side_effect set, flush is not patched, so session.add raising
        # aborts before flush. But we need to make sure the flow hits the except.

        result = AuditLogger.log_event(
            db=session,
            tenant_id=TENANT,
            event_type="auth.login",
            action="login",
            event_category="security",
        )

        assert result is None

    def test_unhandled_exception_propagates(self):
        """Exceptions NOT in the catch list must propagate — pins that
        we didn't accidentally widen the catch to a bare ``except``."""
        class _BespokeError(Exception):
            pass

        session = _mk_session(add_side_effect=_BespokeError("surprise"))

        with pytest.raises(_BespokeError):
            AuditLogger.log_event(
                db=session,
                tenant_id=TENANT,
                event_type="auth.login",
                action="login",
                event_category="security",
            )


# ---------------------------------------------------------------------------
# happy-path smoke — ensures _get_prev_hash and hash-chain wiring stay live
# ---------------------------------------------------------------------------


class TestLogEventHappyPath:

    def test_returns_new_entry_id(self):
        session = _mk_session(prev_hash=None)
        new_id = AuditLogger.log_event(
            db=session,
            tenant_id=TENANT,
            event_type="auth.login",
            action="login",
            event_category="security",
            actor_id=ACTOR,
        )
        assert new_id == 17

    def test_chains_to_previous_hash(self):
        prev = "a" * 64
        session = _mk_session(prev_hash=prev)

        AuditLogger.log_event(
            db=session,
            tenant_id=TENANT,
            event_type="auth.login",
            action="login",
            event_category="security",
        )

        entry = session._added[0]
        assert entry.prev_hash == prev
        # integrity_hash is a 64-char SHA-256 hex, NOT equal to prev
        assert len(entry.integrity_hash) == 64
        assert entry.integrity_hash != prev

    def test_metadata_defaults_to_empty_dict(self):
        """When metadata is None, stored value is {} (line 129: ``meta = metadata or {}``)."""
        session = _mk_session(prev_hash=None)

        AuditLogger.log_event(
            db=session,
            tenant_id=TENANT,
            event_type="auth.login",
            action="login",
            event_category="security",
            metadata=None,
        )
        entry = session._added[0]
        assert entry.metadata_ == {}
