"""Offline tests for app/seed_neo4j.py with a fake session; one live test marked integration."""

import io
import os

import pytest
from app import seed_neo4j as seed


class FakeResult:
    def __init__(self, rows=None):
        self.rows = rows or []

    def consume(self):
        return None

    def data(self):
        return self.rows


class FakeSession:
    def __init__(self, rows=None):
        self.calls: list[tuple[str, dict]] = []
        self.rows = rows or []

    def run(self, query, **params):
        self.calls.append((query, params))
        return FakeResult(self.rows if query == seed.BUYER_INTENT_QUERY else None)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeDriver:
    def __init__(self, session):
        self._session = session

    def session(self):
        return self._session


ROWS = [
    {"corporation": "Workday", "firm": "Sample Capitol Strategies (fictional)", "bill": "CO-SB205-2024",
     "passage_probability": 0.82, "position": "AMEND", "spend": 185000, "filing_id": "SAMPLE-LD2-0001"},
]


@pytest.fixture
def graph():
    return seed.load_sample_graph()


def test_constraints_cover_every_key():
    s = FakeSession()
    seed.create_constraints(s)
    queries = [q for q, _ in s.calls]
    assert len(queries) == 6
    for label, key in [("Bill", "bill_uid"), ("BillVersion", "version_uid"),
                       ("Legislator", "bioguide_or_os_id"), ("Committee", "committee_uid"),
                       ("Corporation", "domain"), ("LobbyingFirm", "name")]:
        assert any(f"FOR (n:{label}) REQUIRE n.{key} IS UNIQUE" in q and "IF NOT EXISTS" in q for q in queries)


def test_every_merge_is_tagged_sample(graph):
    s = FakeSession()
    seed.seed_sample_graph(s, graph)
    merges = [(q, p) for q, p in s.calls if "MERGE" in q]
    node_count = sum(len(graph[section]) for section in seed.NODES)
    assert len(merges) == node_count + len(graph["relationships"])
    for query, params in merges:
        assert params["sample"] is True
        assert "sample = $sample" in query
        assert "CREATE " not in query


def test_fixture_covers_required_entities(graph):
    assert {b["bill_uid"] for b in graph["bills"]} >= {"CO-SB205-2024", "CT-SB2-2025", "TX-HB1709-2025", "CA-SB253-2023"}
    assert {c["name"] for c in graph["corporations"]} == {"Workday", "HireVue", "Upstart", "Chevron"}
    sponsors = {lg["name"].split()[-1] for lg in graph["legislators"]}
    assert sponsors >= {"Rodriguez", "Maroney", "Capriglione", "Wiener"}
    assert {r["type"] for r in graph["relationships"]} == set(seed.RELS)
    assert {r["props"]["position"] for r in graph["relationships"] if r["type"] == "RETAINED"} == {
        "OPPOSE", "AMEND", "MONITOR", "SUPPORT"}


def test_relationship_endpoints_exist(graph):
    # MATCH ... MERGE writes nothing when an endpoint is missing, so a typo would vanish silently.
    keys = {label: {n[key] for n in graph[section]} for section, (label, key) in seed.NODES.items()}
    for rel in graph["relationships"]:
        src, dst = seed.RELS[rel["type"]]
        assert rel["from"] in keys[src], rel
        assert rel["to"] in keys[dst], rel


def test_buyer_intent_query_filter():
    s = FakeSession(rows=ROWS)
    assert seed.buyer_intent(s) == ROWS
    query, params = s.calls[0]
    assert "(c:Corporation)-[r:RETAINED]->(f:LobbyingFirm)-[:LOBBIED_ON]->(b:Bill)" in query
    assert "b.passage_probability >= $min_probability" in query
    assert "r.position IN $positions" in query
    assert "ORDER BY r.spend DESC" in query
    assert params == {"min_probability": 0.4, "positions": ["OPPOSE", "AMEND", "MONITOR"]}


def test_run_prints_banner_and_table(graph):
    s = FakeSession(rows=ROWS)
    out = io.StringIO()
    assert seed.run(FakeDriver(s), graph, out=out) == ROWS
    text = out.getvalue()
    assert text.count("SAMPLE DATA") >= 2
    assert "Workday" in text and "SAMPLE-LD2-0001" in text
    assert "SAMPLE DATA" in seed.__doc__


def test_settings_fall_back_to_neo4j_auth(monkeypatch):
    for name in ("NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD", "FACTORY_NEO4J_BOLT_PORT"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("NEO4J_AUTH", "neo4j/from-auth")
    assert seed.neo4j_settings() == ("bolt://localhost:7687", "neo4j", "from-auth")
    monkeypatch.setenv("NEO4J_PASSWORD", "explicit")
    assert seed.neo4j_settings()[2] == "explicit"
    monkeypatch.delenv("NEO4J_AUTH")
    monkeypatch.delenv("NEO4J_PASSWORD")
    with pytest.raises(SystemExit):
        seed.neo4j_settings()


@pytest.mark.integration
def test_live_seed_and_intent():
    neo4j = pytest.importorskip("neo4j")
    from dotenv import load_dotenv

    load_dotenv(seed.PACKAGE_DIR / ".env")
    if not (os.environ.get("NEO4J_PASSWORD") or os.environ.get("NEO4J_AUTH")):
        pytest.skip("no Neo4j credentials in env or .env")
    uri, user, password = seed.neo4j_settings()
    driver = neo4j.GraphDatabase.driver(uri, auth=(user, password))
    try:
        driver.verify_connectivity()
    except Exception:
        driver.close()
        pytest.skip(f"Neo4j not reachable at {uri}")
    with driver:
        rows = seed.run(driver, out=io.StringIO())
        seed.run(driver, out=io.StringIO())  # idempotent: MERGE must not duplicate
        with driver.session() as s:
            assert s.run("MATCH (n:Bill {bill_uid: 'CO-SB205-2024'}) RETURN count(n) AS c").single()["c"] == 1
            assert s.run("MATCH (n {sample: true}) WHERE n.bill_uid IS NOT NULL OR n.domain IS NOT NULL "
                         "RETURN count(n) AS c").single()["c"] == 8
    assert [r["corporation"] for r in rows] == ["Workday", "Workday", "HireVue", "HireVue", "Upstart"]
    assert {r["position"] for r in rows} <= {"OPPOSE", "AMEND", "MONITOR"}
