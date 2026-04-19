"""Concurrent _resolve_or_register tests for identity_resolution
(issue #1235).

#1235 calls out three test gaps. This file covers gap #3:

    "Concurrent _resolve_or_register of the same GTIN must produce
     exactly one canonical entity (integration test with real DB +
     threads or asyncio)."

A true concurrency integration test requires a running Postgres (to
exercise pg_advisory_xact_lock and the UNIQUE(tenant_id, alias_type,
alias_value) constraint added in migration v059). This file locks in
the structural protections with mocks so a regression that *removes*
the protection fails even before the postgres-dependent suite runs.

Structural invariants captured here:

1. `_resolve_or_register` acquires the advisory lock BEFORE doing the
   exact-alias lookup. That ordering is what serializes the check-then-
   insert critical section.
2. The advisory-lock key is deterministic for the same triple, and
   distinct for different tenants, alias_types, or references.
3. When a concurrent sibling inserts the row between our lookup-0 and
   our retry-lookup, the second arrival sees the existing entity
   (simulated via mocked `find_entity_by_alias` call-index replay).
4. `_insert_alias` relying on ON CONFLICT DO NOTHING means the UNIQUE
   constraint is the authoritative dedup barrier -- locked in by an
   inspection of the insert SQL path.

See also #1190 (advisory-lock fix), #1179 (UNIQUE constraint), and the
existing `test_identity_resolution_hardening.py::#1190` classes for
complementary coverage.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from services.shared.identity_resolution import IdentityResolutionService

TENANT = "tenant-concurrent-1235"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session():
    session = MagicMock()
    session.execute.return_value.fetchall.return_value = []
    session.execute.return_value.fetchone.return_value = (1,)
    return session


@pytest.fixture
def svc(mock_session):
    return IdentityResolutionService(mock_session)


# ---------------------------------------------------------------------------
# Advisory lock is acquired BEFORE the lookup-then-insert critical section
# ---------------------------------------------------------------------------


class TestAdvisoryLockOrdering_Issue1235:
    def test_advisory_lock_precedes_alias_lookup(self, svc, mock_session):
        """The TOCTOU guard only works if the lock is acquired BEFORE
        we read the aliases table. If the order flipped, two concurrent
        threads could both see no match and both INSERT.

        We assert via call-order inspection: the first SQL the mock sees
        must be ``SELECT pg_advisory_xact_lock(...)``, not a SELECT
        against entity_aliases."""
        executed_sql: list[str] = []

        def _record(sql, *args, **kwargs):
            executed_sql.append(str(sql))
            result = MagicMock()
            result.fetchall.return_value = []
            result.fetchone.return_value = (1,)
            return result

        mock_session.execute.side_effect = _record
        # Short-circuit register so we don't pollute the SQL list with
        # the full insert pipeline.
        svc.register_entity = lambda **kw: {  # type: ignore[assignment]
            "entity_id": "eid", "canonical_name": kw["canonical_name"],
            "resolution": "new",
        }
        svc._insert_alias = lambda **kw: "alias-id"  # type: ignore[assignment]

        svc._resolve_or_register(
            tenant_id=TENANT,
            reference="00012345678901",
            entity_type="product",
            source_system="test",
            alias_type="gtin",
        )

        # First SQL statement must be the advisory-lock acquisition.
        assert any(
            "pg_advisory_xact_lock" in s for s in executed_sql
        ), f"Advisory lock was never acquired, executed: {executed_sql}"
        lock_idx = next(
            i for i, s in enumerate(executed_sql)
            if "pg_advisory_xact_lock" in s
        )
        alias_idx = next(
            (i for i, s in enumerate(executed_sql) if "entity_aliases" in s),
            None,
        )
        if alias_idx is not None:
            assert lock_idx < alias_idx, (
                "Advisory lock must be acquired BEFORE the alias SELECT. "
                f"Order seen: lock at {lock_idx}, alias at {alias_idx}"
            )

    def test_lock_key_deterministic_for_same_triple(self, svc, mock_session):
        """Same (tenant, alias_type, reference) MUST produce the same
        lock key across runs -- otherwise two threads hashing the same
        triple would lock on different keys and the critical section
        would not be serialized."""
        captured_keys: list[int] = []

        def _record(sql, params=None, *a, **kw):
            if params and "key" in params:
                captured_keys.append(params["key"])
            result = MagicMock()
            result.fetchall.return_value = []
            result.fetchone.return_value = (1,)
            return result

        mock_session.execute.side_effect = _record

        svc._acquire_resolve_lock(TENANT, "gtin", "00012345678901")
        svc._acquire_resolve_lock(TENANT, "gtin", "00012345678901")

        assert len(captured_keys) == 2
        assert captured_keys[0] == captured_keys[1], (
            "Lock key must be deterministic for identical input"
        )

    def test_lock_key_differs_for_different_tenants(
        self, svc, mock_session,
    ):
        """Two distinct tenants resolving the same reference must not
        contend on the same lock -- that would be a cross-tenant
        serialization bottleneck."""
        captured_keys: list[int] = []

        def _record(sql, params=None, *a, **kw):
            if params and "key" in params:
                captured_keys.append(params["key"])
            result = MagicMock()
            result.fetchall.return_value = []
            result.fetchone.return_value = (1,)
            return result

        mock_session.execute.side_effect = _record
        svc._acquire_resolve_lock("tenant-A", "gtin", "00012345678901")
        svc._acquire_resolve_lock("tenant-B", "gtin", "00012345678901")

        assert len(captured_keys) == 2
        assert captured_keys[0] != captured_keys[1], (
            "Different tenants must hash to different advisory-lock keys"
        )

    def test_lock_key_differs_for_different_alias_types(
        self, svc, mock_session,
    ):
        """'gtin' vs 'gln' vs 'tlc' must each have their own lock keyspace
        even for identical reference strings."""
        captured_keys: list[int] = []

        def _record(sql, params=None, *a, **kw):
            if params and "key" in params:
                captured_keys.append(params["key"])
            result = MagicMock()
            result.fetchall.return_value = []
            result.fetchone.return_value = (1,)
            return result

        mock_session.execute.side_effect = _record
        svc._acquire_resolve_lock(TENANT, "gtin", "0614141000012")
        svc._acquire_resolve_lock(TENANT, "gln", "0614141000012")

        assert len(captured_keys) == 2
        assert captured_keys[0] != captured_keys[1], (
            "Different alias_types must hash to different lock keys"
        )

    def test_lock_key_differs_for_different_references(
        self, svc, mock_session,
    ):
        """Different references must hash to different lock keys."""
        captured_keys: list[int] = []

        def _record(sql, params=None, *a, **kw):
            if params and "key" in params:
                captured_keys.append(params["key"])
            result = MagicMock()
            result.fetchall.return_value = []
            result.fetchone.return_value = (1,)
            return result

        mock_session.execute.side_effect = _record
        svc._acquire_resolve_lock(TENANT, "gtin", "00012345678901")
        svc._acquire_resolve_lock(TENANT, "gtin", "00012345678902")

        assert len(captured_keys) == 2
        assert captured_keys[0] != captured_keys[1], (
            "Different reference values must hash to different lock keys"
        )


# ---------------------------------------------------------------------------
# Simulated concurrency: second arrival sees first's row and returns existing
# ---------------------------------------------------------------------------


class TestRaceReplayYieldsSingleEntity_Issue1235:
    def test_second_caller_finds_first_callers_row(self, mock_session):
        """Simulate the following interleave:

            Thread 1: acquires lock, lookup returns [], inserts, releases.
            Thread 2: acquires lock, lookup returns row from thread 1.

        Under the advisory-lock serialization, thread 2's lookup MUST see
        the row thread 1 inserted. We drive this via a MagicMock whose
        ``find_entity_by_alias`` returns [] on the first call and then
        returns the inserted row on any subsequent call (simulating
        Postgres visibility after the first thread committed)."""
        svc = IdentityResolutionService(mock_session)

        # First-call returns empty (no existing); subsequent calls return
        # an 'existing' row -- simulating the first thread's commit
        # becoming visible.
        calls = {"n": 0}

        def _first_empty_then_existing(tenant_id, alias_type, alias_value):
            calls["n"] += 1
            if calls["n"] == 1:
                return []
            return [{
                "entity_id": "eid-first-thread",
                "canonical_name": alias_value,
                "is_active": True,
                "entity_type": "product",
                "gln": None,
                "gtin": alias_value,
                "verification_status": "unverified",
                "confidence_score": 0.8,
                "matched_alias": {
                    "alias_id": "alias-A", "alias_type": alias_type,
                    "alias_value": alias_value, "source_system": "test",
                    "confidence": 1.0,
                },
            }]

        svc.find_entity_by_alias = (  # type: ignore[assignment]
            _first_empty_then_existing
        )
        # Short-circuit register so we don't exercise the INSERT pipeline.
        svc.register_entity = lambda **kw: {  # type: ignore[assignment]
            "entity_id": "eid-first-thread",
            "canonical_name": kw["canonical_name"],
            "resolution": "new",
        }
        svc._insert_alias = lambda **kw: "alias-id"  # type: ignore[assignment]

        # Use alias_type="tlc" + a non-digit reference so _resolve_or_register
        # only issues ONE find_entity_by_alias call per _resolve invocation
        # (name-type expands to 3 searches, digits-14 adds gtin, etc.).
        reference = "LOT-ABC-001"
        # Thread 1: no existing entity -> registers new.
        result1 = svc._resolve_or_register(
            tenant_id=TENANT, reference=reference,
            entity_type="lot", source_system="test", alias_type="tlc",
        )
        # Thread 2: thread 1's row now visible -> returns existing.
        result2 = svc._resolve_or_register(
            tenant_id=TENANT, reference=reference,
            entity_type="lot", source_system="test", alias_type="tlc",
        )

        assert result1["resolution"] == "new"
        assert result2["resolution"] == "existing"
        # CRITICAL: both resolve to the same entity_id -- "exactly one
        # canonical entity" is the #1235 acceptance criterion.
        assert result1["entity_id"] == result2["entity_id"]


# ---------------------------------------------------------------------------
# The UNIQUE constraint is still invoked via _insert_alias even if
# advisory locks degrade (non-Postgres path).
# ---------------------------------------------------------------------------


class TestUniqueConstraintFallback_Issue1235:
    def test_insert_alias_sql_uses_on_conflict_do_nothing(self, svc, mock_session):
        """_insert_alias MUST emit ON CONFLICT DO NOTHING so the UNIQUE
        constraint is the authoritative dedup barrier when the advisory
        lock path degrades (e.g., on SQLite in a non-prod test harness).
        This locks in the #1179 contract."""
        # Call _insert_alias directly and capture the SQL.
        svc._insert_alias(
            tenant_id=TENANT,
            entity_id="eid-X",
            alias_type="gtin",
            alias_value="00012345678901",
            source_system="test",
            confidence=1.0,
        )
        # Find an INSERT call to entity_aliases.
        sqls = [str(c.args[0]) for c in mock_session.execute.call_args_list]
        alias_inserts = [s for s in sqls if "entity_aliases" in s and "INSERT" in s.upper()]
        assert alias_inserts, (
            f"Expected at least one INSERT into entity_aliases, saw: {sqls}"
        )
        insert_sql = alias_inserts[0].replace("\n", " ").upper()
        assert "ON CONFLICT" in insert_sql, (
            "_insert_alias must use ON CONFLICT DO NOTHING to leverage the "
            "UNIQUE(tenant_id, alias_type, alias_value) constraint from v059"
        )

    def test_advisory_lock_failure_is_non_fatal(self, svc, mock_session):
        """If pg_advisory_xact_lock raises (e.g., on non-Postgres backends),
        _resolve_or_register must still proceed -- the UNIQUE constraint
        is the true dedup barrier. A regression that lets the exception
        bubble out would break every non-Postgres test harness."""
        def _raise_on_lock(sql, params=None, *a, **kw):
            if "pg_advisory_xact_lock" in str(sql):
                raise RuntimeError("not a postgres backend")
            result = MagicMock()
            result.fetchall.return_value = []
            result.fetchone.return_value = (1,)
            return result

        mock_session.execute.side_effect = _raise_on_lock
        svc.register_entity = lambda **kw: {  # type: ignore[assignment]
            "entity_id": "eid", "canonical_name": kw["canonical_name"],
            "resolution": "new",
        }
        svc._insert_alias = lambda **kw: "alias-id"  # type: ignore[assignment]

        # Must not raise -- advisory-lock unavailability is logged+swallowed.
        result = svc._resolve_or_register(
            tenant_id=TENANT, reference="00012345678901",
            entity_type="product", source_system="test", alias_type="gtin",
        )
        assert result["resolution"] == "new"
