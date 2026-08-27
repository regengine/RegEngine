"""Real-Neo4j traceability coverage (#2877).

The double guard this file used to have
---------------------------------------
Locally the graph-tree conftest auto-skipped it (``integration`` marker,
no ``--run-integration``); in CI a blanket ``_IN_CI`` guard skipped it
with the reason "uses CI service container instead". That reason was
not true: nothing connected to the ``neo4j:5.24-community`` service
container backend-ci provisioned on all seven ``test`` matrix legs --
the only other Neo4j-touching graph test patches
``AsyncGraphDatabase`` with a ``MagicMock``. So real-Neo4j behaviour
had no coverage anywhere, CI paid for the container seven times over,
and anyone reading the guard concluded coverage existed elsewhere.

The gate now
------------
``_neo4j_target()`` resolves, in order:

  1. ``NEO4J_URI`` (with ``NEO4J_USER`` / ``NEO4J_PASSWORD``) when it is
     actually reachable -- the CI service container. This is what makes
     the old skip message true: in CI the test RUNS against the service
     container instead of starting a testcontainer.
  2. A disposable ``testcontainers`` Neo4j -- local dev convenience.
  3. Neither available:
       * ``REGENGINE_REQUIRE_NEO4J=1`` -> ``pytest.fail``. The CI job
         that provisions Neo4j sets this, so the container can never be
         provisioned for a test that then skips.
       * unset -> ``pytest.skip`` with a reason that says what is
         uncovered, so local runs stay friendly.

The ``integration`` marker stays: it is the local ergonomics gate (a
Neo4j container dominates the graph-tree runtime). CI passes
``--run-integration`` on the dedicated Neo4j job, so the marker no
longer doubles as a second, silent CI skip.
"""

from __future__ import annotations

import os
from typing import Iterator

import pytest
from neo4j import GraphDatabase

pytestmark = pytest.mark.integration

_DEFAULT_USER = "neo4j"


def _require_neo4j() -> bool:
    return os.getenv("REGENGINE_REQUIRE_NEO4J", "").strip().lower() in {"1", "true", "yes"}


def _skip_or_fail(reason: str) -> None:
    if _require_neo4j():
        pytest.fail(f"{reason} (REGENGINE_REQUIRE_NEO4J=1 — this gate must run a real Neo4j, not skip)")
    pytest.skip(reason)


def _reachable(uri: str, auth: tuple[str, str]) -> bool:
    """True if a driver can actually open a session and answer a query.

    ``GraphDatabase.driver()`` is lazy, so constructing one proves
    nothing — a placeholder ``NEO4J_URI`` with nothing listening builds
    a driver just fine. Round-trip a query instead.
    """
    try:
        driver = GraphDatabase.driver(uri, auth=auth)
    except Exception:
        return False
    try:
        driver.verify_connectivity()
        return True
    except Exception:
        return False
    finally:
        driver.close()


@pytest.fixture(scope="session")
def neo4j_driver() -> Iterator[object]:
    """A driver against a live Neo4j: CI service container, else testcontainers."""
    uri = os.getenv("NEO4J_URI", "").strip()
    password = os.getenv("NEO4J_PASSWORD", "").strip()
    if uri and password:
        auth = (os.getenv("NEO4J_USER", _DEFAULT_USER).strip() or _DEFAULT_USER, password)
        if _reachable(uri, auth):
            driver = GraphDatabase.driver(uri, auth=auth)
            try:
                yield driver
            finally:
                driver.close()
            return
        # NEO4J_URI is set but dead. Under REGENGINE_REQUIRE_NEO4J this is
        # the interesting failure: the job declared a Neo4j and did not
        # deliver one. Otherwise fall through to testcontainers.
        if _require_neo4j():
            pytest.fail(f"REGENGINE_REQUIRE_NEO4J=1 but NEO4J_URI={uri!r} is not reachable")

    try:
        from testcontainers.neo4j import Neo4jContainer
    except ImportError as exc:  # pragma: no cover — depends on local env
        _skip_or_fail(f"no reachable NEO4J_URI and testcontainers unavailable ({exc}) — real-Neo4j traceability")
        return

    try:
        container = Neo4jContainer("neo4j:5.24-community")
        container.start()
    except Exception as exc:  # Docker missing, image pull fails, etc.
        _skip_or_fail(f"no reachable NEO4J_URI and Neo4jContainer unavailable ({exc}) — real-Neo4j traceability")
        return

    try:
        driver = container.get_driver()
        try:
            yield driver
        finally:
            driver.close()
    finally:
        container.stop()


@pytest.fixture
def clean_graph(neo4j_driver):
    """Give each test an empty graph and leave one behind.

    Session-scoped drivers plus a shared CI service container mean state
    leaks between tests otherwise — and a traceability assertion that
    passes only because a previous test seeded the node is exactly the
    kind of green this file is being fixed for.
    """
    with neo4j_driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")
    yield neo4j_driver
    with neo4j_driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")


def test_neo4j_traceability_query(clean_graph):
    """One-up/one-down traceback across a three-hop supply chain."""
    with clean_graph.session() as session:
        # Create a simple supply chain trace
        session.run("""
            CREATE (f:Facility {name: 'Farm A', gln: '123'})
            CREATE (d:Distributor {name: 'Distributor B', gln: '456'})
            CREATE (r:Retailer {name: 'Store C', gln: '789'})
            CREATE (f)-[:SHIPPED_TO {date: '2026-02-01'}]->(d)
            CREATE (d)-[:SHIPPED_TO {date: '2026-02-02'}]->(r)
        """)

        # Run a "one-up/one-down" traceability query
        result = session.run("""
            MATCH (r:Retailer {gln: '789'})<-[:SHIPPED_TO]-(d)<-[:SHIPPED_TO]-(f)
            RETURN f.name as source_farm, d.name as distributor
        """)

        record = result.single()
        assert record is not None, "the two-hop traceback returned no path"
        assert record["source_farm"] == "Farm A"
        assert record["distributor"] == "Distributor B"


def test_traceback_does_not_cross_into_an_unrelated_chain(clean_graph):
    """A second, disjoint chain must not appear in the first chain's trace.

    The original single-path assertion passes even if the query returns
    every facility in the database; this is the assertion that makes the
    graph traversal load-bearing.
    """
    with clean_graph.session() as session:
        session.run("""
            CREATE (f1:Facility {name: 'Farm A', gln: '123'})
            CREATE (d1:Distributor {name: 'Distributor B', gln: '456'})
            CREATE (r1:Retailer {name: 'Store C', gln: '789'})
            CREATE (f1)-[:SHIPPED_TO]->(d1)-[:SHIPPED_TO]->(r1)
            CREATE (f2:Facility {name: 'Farm X', gln: '999'})
            CREATE (d2:Distributor {name: 'Distributor Y', gln: '998'})
            CREATE (r2:Retailer {name: 'Store Z', gln: '997'})
            CREATE (f2)-[:SHIPPED_TO]->(d2)-[:SHIPPED_TO]->(r2)
        """)

        sources = {
            record["source_farm"]
            for record in session.run("""
                MATCH (r:Retailer {gln: '789'})<-[:SHIPPED_TO]-(d)<-[:SHIPPED_TO]-(f)
                RETURN f.name as source_farm
            """)
        }

    assert sources == {"Farm A"}, f"traceback leaked an unrelated chain: {sources!r}"


def test_broken_chain_yields_no_traceback(clean_graph):
    """A missing SHIPPED_TO link must produce no path, not a partial one.

    FSMA-204's whole point is that a gap in the chain is visible. If a
    severed link still returned a record, a broken traceability chain
    would read as complete.
    """
    with clean_graph.session() as session:
        session.run("""
            CREATE (f:Facility {name: 'Farm A', gln: '123'})
            CREATE (d:Distributor {name: 'Distributor B', gln: '456'})
            CREATE (r:Retailer {name: 'Store C', gln: '789'})
            CREATE (d)-[:SHIPPED_TO]->(r)
        """)

        record = session.run("""
            MATCH (r:Retailer {gln: '789'})<-[:SHIPPED_TO]-(d)<-[:SHIPPED_TO]-(f)
            RETURN f.name as source_farm
        """).single()

    assert record is None, f"a broken chain still produced a traceback: {record!r}"
