"""Regression tests for #1248 — ``store_events_batch`` lost-race reconciliation.

Before the fix: the batch INSERT used
``ON CONFLICT (tenant_id, idempotency_key) DO NOTHING`` to survive
concurrent-writer collisions, but never checked which rows actually
landed. Every event in the batch was reported back to the caller with
``idempotent=False`` and the caller-minted ``event_id`` regardless of
whether that id was the one persisted. A downstream reader that looked
up the returned event_id (in the graph sync, in the chain verifier,
in the FDA-export filter) would silently fail to find the row because
the *other* writer's id was the one that actually exists.

After the fix: the INSERT carries ``RETURNING id``. The set of
returned ids is the intersection of "our input" ∩ "what actually
inserted". The complement is the lost-race set; we re-select those
winners by ``(tenant_id, idempotency_key)`` and patch our in-memory
``StoreResult`` list to reflect the authoritative row.

These tests mock the SQLAlchemy session so we can assert on SQL text
and return the exact RETURNING rows we want the writer to see. No
live Postgres.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from shared.cte_persistence.core import CTEPersistence

from tests.shared.test_cte_persistence_hardening import (
    FakeSession,
    _FakeResult,
    _base_event,
)


# ---------------------------------------------------------------------------
# 1) SQL-shape assertions — RETURNING id + ON CONFLICT DO NOTHING
# ---------------------------------------------------------------------------


class TestBatchInsertSqlShape_Issue1248:
    def test_insert_sql_has_on_conflict_do_nothing_and_returning_id(self):
        """The batch INSERT must carry ``ON CONFLICT (tenant_id,
        idempotency_key) DO NOTHING RETURNING id`` — that is the whole
        basis for detecting lost-race rows."""
        session = FakeSession()
        session.add_rule(r"SELECT idempotency_key", _FakeResult(rows=[]))
        session.add_rule(r"FROM fsma\.hash_chain", _FakeResult(rows=[]))

        captured_insert_sql: list[str] = []

        def _insert(sql, params):
            captured_insert_sql.append(sql)
            # Return all rows as inserted (no lost race on this test).
            returned = [(params[f"id_{i}"],) for i in range(2)]
            return _FakeResult(rows=returned)

        session.add_rule(r"INSERT INTO fsma\.cte_events", _insert)

        p = CTEPersistence(session=session)
        p.store_events_batch(
            tenant_id="t-1",
            events=[
                _base_event(traceability_lot_code="TLC-A"),
                _base_event(traceability_lot_code="TLC-B"),
            ],
        )

        assert captured_insert_sql, "batch INSERT should have executed"
        sql_upper = captured_insert_sql[0].upper()
        assert "ON CONFLICT" in sql_upper
        assert "DO NOTHING" in sql_upper
        assert "RETURNING" in sql_upper, (
            "batch INSERT must RETURNING id so the caller can detect "
            "which rows actually landed"
        )


# ---------------------------------------------------------------------------
# 2) Partial lost race — one row wins, one row loses
# ---------------------------------------------------------------------------


class TestPartialLostRace_Issue1248:
    def test_lost_row_patched_to_idempotent_with_winner_data(self):
        """When the batch INSERT returns only the ids for rows that
        landed, the rows that lost the race must have their StoreResult
        replaced with the winner's event_id / sha256_hash / chain_hash
        and ``idempotent=True``."""
        winner_event_id = str(uuid4())
        winner_sha = "w" * 64
        winner_chain = "c" * 64

        session = FakeSession()

        # Capture what the writer submits to the initial INSERT so we
        # can return only *one* of those ids from RETURNING.
        captured_insert_params: dict = {}

        def _insert(sql, params):
            captured_insert_params.update(params)
            # Event 0 landed, event 1 lost the race — return only id_0.
            return _FakeResult(rows=[(params["id_0"],)])

        # Pre-flight idempotency SELECT (call 1): nothing pre-existing.
        # Reconcile SELECT (call 2): returns the winner row for event 1.
        idemp_call_count = {"n": 0}

        def _idemp_or_reconcile(sql, params):
            idemp_call_count["n"] += 1
            if idemp_call_count["n"] == 1:
                # Pre-flight call: no event pre-existing.
                return _FakeResult(rows=[])
            # Reconcile call: the writer is asking for the lost
            # event's winner. Pick the idempotency key the writer
            # passed in and return a faked winner row.
            lost_keys = [v for k, v in params.items() if k.startswith("lk")]
            assert len(lost_keys) == 1, (
                f"expected exactly one lost idempotency key, got {lost_keys}"
            )
            return _FakeResult(rows=[
                (lost_keys[0], winner_event_id, winner_sha, winner_chain),
            ])

        session.add_rule(
            r"SELECT idempotency_key, id, sha256_hash, chain_hash",
            _idemp_or_reconcile,
        )
        session.add_rule(r"FROM fsma\.hash_chain", _FakeResult(rows=[]))
        session.add_rule(r"INSERT INTO fsma\.cte_events", _insert)

        p = CTEPersistence(session=session)
        results = p.store_events_batch(
            tenant_id="t-1",
            events=[
                _base_event(traceability_lot_code="TLC-A"),
                _base_event(traceability_lot_code="TLC-B"),
            ],
        )

        assert len(results) == 2

        # Event 0 landed — keep our pre-computed event_id / hashes.
        assert results[0].idempotent is False
        assert results[0].event_id == captured_insert_params["id_0"]

        # Event 1 lost the race — patched to idempotent=True with the
        # winner's id/sha/chain, NOT the id we minted locally.
        assert results[1].idempotent is True, (
            "lost-race event must be reported as idempotent"
        )
        assert results[1].event_id == winner_event_id
        assert results[1].event_id != captured_insert_params["id_1"]
        assert results[1].sha256_hash == winner_sha
        assert results[1].chain_hash == winner_chain


# ---------------------------------------------------------------------------
# 3) Fully lost race — every row in the batch collided
# ---------------------------------------------------------------------------


class TestFullyLostRace_Issue1248:
    def test_all_rows_lost_all_patched_to_idempotent(self):
        """If RETURNING returns zero rows (every event in the batch
        lost the race), every StoreResult must be patched to
        ``idempotent=True`` with the corresponding winner row."""
        winner_ids = [str(uuid4()) for _ in range(3)]
        winner_shas = [f"{i}" * 64 for i in "abc"]
        winner_chains = [f"{i}" * 64 for i in "xyz"]

        session = FakeSession()

        captured_insert_params: dict = {}

        def _insert(sql, params):
            captured_insert_params.update(params)
            # Zero rows returned — complete lost race.
            return _FakeResult(rows=[])

        idemp_call_count = {"n": 0}

        def _idemp_or_reconcile(sql, params):
            idemp_call_count["n"] += 1
            if idemp_call_count["n"] == 1:
                return _FakeResult(rows=[])
            # Reconcile: map each lost key to a fabricated winner row.
            lost_keys = [v for k, v in params.items() if k.startswith("lk")]
            assert len(lost_keys) == 3
            return _FakeResult(rows=[
                (lost_keys[i], winner_ids[i], winner_shas[i], winner_chains[i])
                for i in range(3)
            ])

        session.add_rule(
            r"SELECT idempotency_key, id, sha256_hash, chain_hash",
            _idemp_or_reconcile,
        )
        session.add_rule(r"FROM fsma\.hash_chain", _FakeResult(rows=[]))
        session.add_rule(r"INSERT INTO fsma\.cte_events", _insert)

        p = CTEPersistence(session=session)
        results = p.store_events_batch(
            tenant_id="t-1",
            events=[
                _base_event(traceability_lot_code=f"TLC-{i}") for i in "ABC"
            ],
        )

        assert len(results) == 3
        for r in results:
            assert r.idempotent is True, (
                "every StoreResult must be marked idempotent when "
                "the whole batch lost the race"
            )
        # Each StoreResult's event_id came from the re-select, not the
        # locally-minted id_N.
        minted_ids = {captured_insert_params[f"id_{i}"] for i in range(3)}
        returned_ids = {r.event_id for r in results}
        assert returned_ids.isdisjoint(minted_ids), (
            "lost-race StoreResults must carry winner ids, not the "
            "locally-minted ones"
        )
        assert returned_ids == set(winner_ids)


# ---------------------------------------------------------------------------
# 4) Fast path — no lost race, no reconcile SELECT
# ---------------------------------------------------------------------------


class TestNoLostRaceFastPath_Issue1248:
    def test_no_lost_race_does_not_fire_reconcile_select(self):
        """When every event in the batch lands (RETURNING returns every
        submitted id), the writer must NOT issue a second
        idempotency-shape SELECT. This keeps the happy path a single
        round-trip."""
        session = FakeSession()
        session.add_rule(r"SELECT idempotency_key", _FakeResult(rows=[]))
        session.add_rule(r"FROM fsma\.hash_chain", _FakeResult(rows=[]))

        def _insert(sql, params):
            # All ids landed.
            ids = [(params[f"id_{i}"],) for i in range(2)]
            return _FakeResult(rows=ids)

        session.add_rule(r"INSERT INTO fsma\.cte_events", _insert)

        p = CTEPersistence(session=session)
        results = p.store_events_batch(
            tenant_id="t-1",
            events=[
                _base_event(traceability_lot_code="TLC-A"),
                _base_event(traceability_lot_code="TLC-B"),
            ],
        )

        idemp_select_calls = [
            c for c in session.calls
            if "SELECT idempotency_key, id, sha256_hash, chain_hash" in c[0]
        ]
        assert len(idemp_select_calls) == 1, (
            f"fast path must issue exactly one idempotency-shape SELECT "
            f"(the pre-flight). Got {len(idemp_select_calls)}: fired the "
            "lost-race reconcile SELECT unnecessarily."
        )
        assert all(r.idempotent is False for r in results)


# ---------------------------------------------------------------------------
# 5) Pre-flight idempotent path is unaffected
# ---------------------------------------------------------------------------


class TestPreFlightUnaffected_Issue1248:
    def test_pre_flight_idempotent_event_skips_insert_and_reconcile(self):
        """If the pre-flight SELECT finds an event already in the
        table, that event must be reported as ``idempotent=True`` and
        must NOT participate in either the INSERT or the reconcile
        SELECT. The lost-race code only triggers on genuinely-new
        rows that collided at INSERT time."""
        pre_existing_id = str(uuid4())
        pre_existing_sha = "p" * 64
        pre_existing_chain = "q" * 64

        session = FakeSession()

        idemp_call_count = {"n": 0}
        captured_lk_params: list[dict] = []

        def _idemp_or_reconcile(sql, params):
            idemp_call_count["n"] += 1
            if idemp_call_count["n"] == 1:
                # Pre-flight: return event A's hashed idempotency_key.
                # We can't know the exact key ahead of the call — so
                # echo back whichever key the writer asked for first.
                ks = [v for k, v in params.items() if k.startswith("k")]
                # Mark the first key (event A) as pre-existing so it
                # short-circuits without an INSERT row.
                return _FakeResult(rows=[
                    (ks[0], pre_existing_id, pre_existing_sha, pre_existing_chain),
                ])
            captured_lk_params.append(params)
            return _FakeResult(rows=[])

        insert_param_capture: dict = {}

        def _insert(sql, params):
            insert_param_capture.update(params)
            # Only event B should be in this INSERT (A was pre-flight
            # idempotent).
            submitted_count = sum(1 for k in params if k.startswith("id_"))
            ids = [(params[f"id_{i}"],) for i in range(submitted_count)]
            return _FakeResult(rows=ids)

        session.add_rule(
            r"SELECT idempotency_key, id, sha256_hash, chain_hash",
            _idemp_or_reconcile,
        )
        session.add_rule(r"FROM fsma\.hash_chain", _FakeResult(rows=[]))
        session.add_rule(r"INSERT INTO fsma\.cte_events", _insert)

        p = CTEPersistence(session=session)
        results = p.store_events_batch(
            tenant_id="t-1",
            events=[
                _base_event(traceability_lot_code="TLC-A"),
                _base_event(traceability_lot_code="TLC-B"),
            ],
        )

        assert len(results) == 2
        # Event A was pre-flight idempotent → winner's data.
        assert results[0].idempotent is True
        assert results[0].event_id == pre_existing_id
        assert results[0].sha256_hash == pre_existing_sha

        # Event B landed fresh → its own data, idempotent=False.
        assert results[1].idempotent is False

        # Only ONE row should have been submitted to the INSERT
        # (event B); event A's pre-flight hit should have been
        # filtered out of event_rows entirely.
        submitted_ids = [
            k for k in insert_param_capture if k.startswith("id_")
        ]
        assert submitted_ids == ["id_0"], (
            f"expected exactly one INSERT row (event B), got "
            f"{submitted_ids}; pre-flight idempotent events must NOT "
            "be re-submitted to the INSERT"
        )

        # And since event B landed, no reconcile SELECT should fire.
        assert idemp_call_count["n"] == 1, (
            f"expected 1 idempotency-shape SELECT (the pre-flight), "
            f"got {idemp_call_count['n']}: the reconcile SELECT "
            "fired even though nothing lost the race"
        )


# ---------------------------------------------------------------------------
# 6) Phantom event_id regression — the specific bug shape of #1248
# ---------------------------------------------------------------------------


class TestPhantomEventIdGuard_Issue1248:
    def test_lost_race_never_returns_locally_minted_event_id(self):
        """Directly models the #1248 regression: a caller that relies on
        the returned ``event_id`` to look up the row later must never
        receive a locally-minted uuid that does not exist in
        ``fsma.cte_events``. The fix guarantees that a lost-race
        StoreResult always carries the uuid that is actually in the
        table."""
        winner_id = str(uuid4())

        session = FakeSession()
        captured_insert_params: dict = {}

        def _insert(sql, params):
            captured_insert_params.update(params)
            # Lost the race entirely.
            return _FakeResult(rows=[])

        idemp_call_count = {"n": 0}

        def _idemp_or_reconcile(sql, params):
            idemp_call_count["n"] += 1
            if idemp_call_count["n"] == 1:
                return _FakeResult(rows=[])
            lost_keys = [v for k, v in params.items() if k.startswith("lk")]
            return _FakeResult(rows=[
                (lost_keys[0], winner_id, "s" * 64, "h" * 64),
            ])

        session.add_rule(
            r"SELECT idempotency_key, id, sha256_hash, chain_hash",
            _idemp_or_reconcile,
        )
        session.add_rule(r"FROM fsma\.hash_chain", _FakeResult(rows=[]))
        session.add_rule(r"INSERT INTO fsma\.cte_events", _insert)

        p = CTEPersistence(session=session)
        [result] = p.store_events_batch(
            tenant_id="t-1",
            events=[_base_event(traceability_lot_code="TLC-phantom")],
        )

        locally_minted = captured_insert_params["id_0"]
        assert result.event_id != locally_minted, (
            "regression: lost-race StoreResult still carries the locally-"
            "minted uuid, which does not exist in fsma.cte_events. "
            "Downstream lookups (graph sync, chain verifier, exports) "
            "will fail to find this row — this is the exact shape of #1248."
        )
        assert result.event_id == winner_id
        assert result.idempotent is True
