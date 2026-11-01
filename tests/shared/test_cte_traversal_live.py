"""Live-DB regression: transformation-links traversal executes real SQL.

``_expand_tlcs_via_transformation_links`` and its batch twin wrote the
bidirectional walk as a three-branch UNION inside ``WITH RECURSIVE``.
Postgres splits a recursive CTE at the LAST top-level UNION, so the
forward branch landed inside the non-recursive term and EVERY execution
failed with InvalidRecursion ("recursive reference to query "tlc_graph"
must not appear within its non-recursive term") — GET /api/v1/fda/export
500'd whenever ``fsma.transformation_links`` existed and held rows for
the tenant's graph.

The hardening tests drive these methods through a FakeSession keyed on
SQL regexes, which is exactly why the malformed SQL shipped: only a real
Postgres objects to it. This test seeds a small link graph and runs both
traversal methods against a schema-at-head database. Requires
DATABASE_URL and skips without it (same pattern as
test_fda_export_v2_canonical_columns_live.py).
"""

from __future__ import annotations

import uuid

import pytest
from shared.db_url import sync_postgres_url

from tests.migrations.rls_db import guarded_live_database_url

DATABASE_URL = guarded_live_database_url()
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="no designated live test DB (CI DATABASE_URL or REGENGINE_MIGRATION_TEST_DB) — skipping live TLC traversal test",
)


def _seed_link(session, tenant_id: str, input_tlc: str, output_tlc: str) -> None:
    from sqlalchemy import text

    session.execute(
        text("""
            INSERT INTO fsma.transformation_links
                (tenant_id, transformation_event_id, input_tlc, output_tlc)
            VALUES
                (CAST(:tid AS uuid), CAST(:eid AS uuid), :input_tlc, :output_tlc)
        """),
        {"tid": tenant_id, "eid": str(uuid.uuid4()), "input_tlc": input_tlc, "output_tlc": output_tlc},
    )


def test_tlc_traversal_executes_and_walks_both_directions() -> None:
    from shared.cte_persistence.core import CTEPersistence
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    engine = create_engine(sync_postgres_url(DATABASE_URL))
    tenant_id = str(uuid.uuid4())
    other_tenant_id = str(uuid.uuid4())

    with Session(engine) as session:
        # Link graph, all rolled back at the end:
        #   TLC-X → TLC-A → TLC-B → TLC-C   (this tenant)
        #   TLC-B → TLC-LEAK                (another tenant — must not appear)
        _seed_link(session, tenant_id, "TLC-A", "TLC-B")
        _seed_link(session, tenant_id, "TLC-B", "TLC-C")
        _seed_link(session, tenant_id, "TLC-X", "TLC-A")
        _seed_link(session, other_tenant_id, "TLC-B", "TLC-LEAK")

        persistence = CTEPersistence(session)

        # The crash path: any traversal with the table present raised
        # InvalidRecursion before the fix. Seeding mid-chain proves both
        # directions are walked from one recursive branch.
        reachable = persistence._expand_tlcs_via_transformation_links(tenant_id=tenant_id, seed_tlc="TLC-B")
        assert set(reachable) == {"TLC-A", "TLC-B", "TLC-C", "TLC-X"}

        # Tenant isolation: the other tenant's edge must not be followed.
        assert "TLC-LEAK" not in reachable

        # Depth cap: one hop from TLC-X reaches only TLC-A.
        capped = persistence._expand_tlcs_via_transformation_links(tenant_id=tenant_id, seed_tlc="TLC-X", depth=1)
        assert set(capped) == {"TLC-X", "TLC-A"}

        # A seed with no links comes back alone, not as an error.
        lone = persistence._expand_tlcs_via_transformation_links(tenant_id=tenant_id, seed_tlc="TLC-NOWHERE")
        assert lone == ["TLC-NOWHERE"]

        # Batch twin: same closure from a VALUES-seeded base case, with an
        # unlinked seed preserved in the result.
        batch = persistence._expand_tlcs_via_transformation_links_batch(
            tenant_id=tenant_id, seed_tlcs=["TLC-C", "TLC-LONER"]
        )
        assert set(batch) == {"TLC-A", "TLC-B", "TLC-C", "TLC-X", "TLC-LONER"}

        assert persistence._expand_tlcs_via_transformation_links_batch(tenant_id=tenant_id, seed_tlcs=[]) == []

        session.rollback()


def test_tlc_traversal_is_directed_and_excludes_sibling_lots() -> None:
    """S2 (gap analysis 2026-10-28): ``both`` is the union of a forward and
    a backward walk, not an undirected walk. With A → B and A → S, a trace
    from B must reach A (its input) but never S (a sibling output of A that
    B never touched); a forward trace from B must not step back to A at all.
    Also checks the depth-limit flag against real SQL."""
    from shared.cte_persistence.core import CTEPersistence
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    engine = create_engine(sync_postgres_url(DATABASE_URL))
    tenant_id = str(uuid.uuid4())

    with Session(engine) as session:
        #   A → B → C      (seed chain)
        #   A → S          (sibling of B; shares the input A)
        #   S → T          (downstream of the sibling)
        _seed_link(session, tenant_id, "A", "B")
        _seed_link(session, tenant_id, "B", "C")
        _seed_link(session, tenant_id, "A", "S")
        _seed_link(session, tenant_id, "S", "T")

        persistence = CTEPersistence(session)

        both = persistence._expand_tlcs_detailed(tenant_id=tenant_id, seed_tlc="B", direction="both")
        assert set(both.tlcs) == {"A", "B", "C"}
        assert both.reached_via["A"] == {"depth": 1, "downstream": False, "upstream": True}
        assert both.reached_via["C"] == {"depth": 1, "downstream": True, "upstream": False}
        assert both.depth_exhausted is False

        forward = persistence._expand_tlcs_detailed(tenant_id=tenant_id, seed_tlc="B", direction="forward")
        assert set(forward.tlcs) == {"B", "C"}

        backward = persistence._expand_tlcs_detailed(tenant_id=tenant_id, seed_tlc="S", direction="backward")
        assert set(backward.tlcs) == {"S", "A"}

        # Depth limit: from A forward with depth=1, B and S are reached at
        # the limit and never expanded, so the flag must be raised and C, T
        # must be absent.
        capped = persistence._expand_tlcs_detailed(tenant_id=tenant_id, seed_tlc="A", depth=1, direction="forward")
        assert set(capped.tlcs) == {"A", "B", "S"}
        assert capped.depth_exhausted is True

        # Batch twin honours direction as well: forward from B and S never
        # reaches A.
        batch = persistence._expand_tlcs_via_transformation_links_batch(
            tenant_id=tenant_id, seed_tlcs=["B", "S"], direction="forward"
        )
        assert set(batch) == {"B", "C", "S", "T"}

        session.rollback()


def test_depth_limit_is_reported_per_direction_on_a_cycle() -> None:
    """Codex review on #3713: S -> A -> X -> S plus X -> Y. A ``both`` trace
    from S at depth 2 reaches X at depth 2 forward (so Y is never reached)
    and at depth 1 backward. Collapsing the two walks to MIN(depth) before
    judging the limit hid the exhausted forward frontier."""
    from shared.cte_persistence.core import CTEPersistence
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    engine = create_engine(sync_postgres_url(DATABASE_URL))
    tenant_id = str(uuid.uuid4())

    with Session(engine) as session:
        _seed_link(session, tenant_id, "S", "A")
        _seed_link(session, tenant_id, "A", "X")
        _seed_link(session, tenant_id, "X", "S")
        _seed_link(session, tenant_id, "X", "Y")

        persistence = CTEPersistence(session)

        both = persistence._expand_tlcs_detailed(tenant_id=tenant_id, seed_tlc="S", depth=2, direction="both")
        assert set(both.tlcs) == {"S", "A", "X"}
        assert "Y" not in both.tlcs
        assert both.reached_via["X"]["depth"] == 1
        assert both.depth_exhausted is True

        # One more hop and the forward walk reaches Y, but only at the new
        # limit, so Y itself is unexpanded and the flag stays raised.
        at_three = persistence._expand_tlcs_detailed(tenant_id=tenant_id, seed_tlc="S", depth=3, direction="both")
        assert set(at_three.tlcs) == {"S", "A", "X", "Y"}
        assert at_three.reached_via["Y"]["depth"] == 3
        assert at_three.depth_exhausted is True

        # At depth 4 every lot is expanded below the limit in the direction
        # that found it (the cycle only re-finds S, A and X at depths above
        # their per-direction minimum), so nothing is left unexplored.
        at_four = persistence._expand_tlcs_detailed(tenant_id=tenant_id, seed_tlc="S", depth=4, direction="both")
        assert set(at_four.tlcs) == {"S", "A", "X", "Y"}
        assert at_four.depth_exhausted is False

        session.rollback()
