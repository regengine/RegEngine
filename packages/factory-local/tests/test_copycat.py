"""Copycat detection: fingerprint embedding, pgvector persistence and the Neo4j SHARES_MODEL_DNA
writer. Offline tests use fake embeddings and a fake connection that evaluates the copycat query
in Python; the integration test runs the real SQL against the compose Postgres (pgvector)."""

import math
import uuid
from types import SimpleNamespace

import pytest
from app import local_factory as lf
from schemas import DeonticIR
from test_live_bill import LLM_IR, FakeLLM, bill_meta

IR = DeonticIR.model_validate({**LLM_IR, "rule_id": "CO_SB205_2061"})


def version(bill_uid: str, doc_id: int = 1) -> dict:
    return {
        "version_uid": f"{bill_uid}@{doc_id}",
        "bill_uid": bill_uid,
        "jurisdiction": "US-CO",
        "title": f"bill {bill_uid}",
        "full_text": "text",
        "source_uri": "https://example.test",
        "version_stage": "Introduced",
    }


def parse_vector(literal: str) -> list[float]:
    return [float(x) for x in literal.strip("[]").split(",")]


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


class VectorConn:
    """bill_versions in memory. Answers COPYCAT_SQL with the same filters the SQL applies."""

    def __init__(self, stored: dict[str, tuple[str, list[float] | None]] | None = None):
        # version_uid -> (bill_uid, embedding)
        self.versions = dict(stored or {})
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        if "INSERT INTO bill_versions" in sql:
            self.versions[params[0]] = (params[1], parse_vector(params[6]))
        if sql is lf.COPYCAT_SQL:
            target = parse_vector(params["target"])
            best: dict[str, float] = {}
            for bill_uid, emb in self.versions.values():
                if bill_uid == params["bill_uid"] or emb is None or len(emb) != params["dims"]:
                    continue
                best[bill_uid] = max(best.get(bill_uid, -2.0), cosine(emb, target))
            rows = sorted(((b, s) for b, s in best.items() if s >= params["threshold"]), key=lambda r: (-r[1], r[0]))[
                : params["limit"]
            ]
            return SimpleNamespace(fetchall=lambda: rows)
        return SimpleNamespace(fetchall=lambda: [])


class RecordingDriver:
    def __init__(self, fail: Exception | None = None):
        self.runs = []
        self.fail = fail

    def session(self):
        driver = self

        class Session:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def run(self, query, **params):
                if driver.fail:
                    raise driver.fail
                driver.runs.append((query, params))
                return SimpleNamespace(consume=lambda: None)

        return Session()


# Fingerprint embedding


def test_fingerprint_text_has_the_duty_fields_then_6000_chars():
    text = lf.fingerprint_text({**bill_meta("y" * 9000), "title": "AI Act"}, IR)
    head, body = text.split("\n\n", 1)
    assert head.splitlines() == [
        "TITLE: AI Act",
        "MODALITY: OBLIGATION",
        "OBLIGATION_CONTROL: annual_impact_assessment_completed",
        "SAFE_HARBOR: nist_ai_rmf_aligned",
        "APPLICABILITY_PREDICATES: fte_count GREATER_THAN 49; does_business_in_co EQUALS True",
    ]
    assert body == "y" * lf.FINGERPRINT_TEXT_CHARS


def test_embedding_uses_embedding_model(monkeypatch):
    monkeypatch.delenv("EMBEDDING_MODEL", raising=False)
    fake = FakeLLM(embedding=[1, 2, 3])
    assert lf.generate_regulatory_fingerprint_embedding(bill_meta(), IR, client=fake) == [1.0, 2.0, 3.0]
    assert fake.embed_kwargs["model"] == "nomic-embed-text"
    assert fake.embed_kwargs["input"].startswith("TITLE: AI\nMODALITY: OBLIGATION")
    monkeypatch.setenv("EMBEDDING_MODEL", "other-embed")
    lf.generate_regulatory_fingerprint_embedding(bill_meta(), IR, client=fake)
    assert fake.embed_kwargs["model"] == "other-embed"


def test_embedding_default_client_matches_extraction(monkeypatch):
    for name in ("LLM_BASE_URL", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    import openai

    seen = {}

    def factory(**kwargs):
        seen.update(kwargs)
        return FakeLLM()

    monkeypatch.setattr(openai, "OpenAI", factory)
    lf.generate_regulatory_fingerprint_embedding(bill_meta(), IR)
    assert seen == {"base_url": "http://localhost:11434/v1", "api_key": "ollama"}  # pragma: allowlist secret


@pytest.mark.parametrize("embedding", [[], None])
def test_embedding_errors_are_live_bill_errors(embedding):
    fake = FakeLLM(embedding=[])
    if embedding is None:
        fake.embeddings = SimpleNamespace(create=lambda **_: (_ for _ in ()).throw(OSError("model not found")))
    with pytest.raises(lf.LiveBillError, match="embedding with"):
        lf.generate_regulatory_fingerprint_embedding(bill_meta(), IR, client=fake)


# Persistence and matching


def test_threshold_is_inclusive_and_top_5_by_similarity():
    target = [1.0, 0.0]
    stored = {
        "A@1": ("A", [1.0, 0.0]),  # 1.00
        "B@1": ("B", [0.8, 0.6]),  # 0.80, exactly on the threshold
        "C@1": ("C", [0.6, 0.8]),  # 0.60, below
        "D@1": ("D", [0.95, math.sqrt(1 - 0.95**2)]),  # 0.95
    }
    conn, driver = VectorConn(stored), RecordingDriver()
    matches = lf.persist_and_detect_copycats(conn, version("T"), target, "impact_assessment", neo4j_driver=driver)
    assert [m["bill_uid"] for m in matches] == ["A", "D", "B"]
    assert matches[0]["similarity"] == 1.0 and matches[2]["similarity"] == 0.8

    stricter = lf.persist_and_detect_copycats(
        VectorConn(stored), version("T"), target, "x", sim_threshold=0.9, neo4j_driver=RecordingDriver()
    )
    assert [m["bill_uid"] for m in stricter] == ["A", "D"]

    many = {f"B{i}@1": (f"B{i}", [1.0, 0.0]) for i in range(8)}
    capped = lf.persist_and_detect_copycats(VectorConn(many), version("T"), target, "x", neo4j_driver=driver)
    assert len(capped) == lf.COPYCAT_LIMIT


def test_dimension_filter_same_bill_and_null_embeddings_are_excluded():
    stored = {
        "T@0": ("T", [1.0, 0.0]),  # an older version of the same bill
        "W@1": ("W", [1.0, 0.0, 0.0]),  # same direction, different embedding model
        "N@1": ("N", None),  # stored before embeddings existed
        "M@1": ("M", [1.0, 0.1]),
        "M@2": ("M", [1.0, 0.0]),  # best version of M wins, M appears once
    }
    conn = VectorConn(stored)
    matches = lf.persist_and_detect_copycats(conn, version("T"), [1.0, 0.0], "x", neo4j_driver=RecordingDriver())
    assert matches == [{"bill_uid": "M", "similarity": 1.0}]
    query = conn.executed[-1][1]
    assert query["dims"] == 2 and query["bill_uid"] == "T" and query["threshold"] == lf.SIM_THRESHOLD


def test_bill_version_is_upserted_with_embedding_and_rule_only_when_given():
    conn = VectorConn()
    lf.persist_and_detect_copycats(conn, version("T"), [0.5, 0.25], "x")
    sqls = [sql for sql, _ in conn.executed]
    assert "INSERT INTO bill_versions" in sqls[0] and "%s::vector" in sqls[0]
    assert "full_text_embedding = EXCLUDED.full_text_embedding" in sqls[0]
    assert conn.executed[0][1][6] == "[0.5,0.25]"
    assert not any("extracted_rules" in sql for sql in sqls)
    assert not any("ALTER TABLE" in sql for sql in sqls)  # schema changes live in db_init only

    conn = VectorConn()
    lf.persist_and_detect_copycats(conn, version("T"), [0.5, 0.25], "x", rule_params=("T", "T@1"))
    assert "INSERT INTO extracted_rules" in conn.executed[1][0] and conn.executed[1][1] == ("T", "T@1")


# Neo4j


def test_matches_are_merged_into_neo4j():
    driver = RecordingDriver()
    stored = {"A@1": ("A", [1.0, 0.0])}
    lf.persist_and_detect_copycats(
        VectorConn(stored), version("T"), [1.0, 0.0], "impact_assessment", neo4j_driver=driver
    )
    ((query, params),) = driver.runs
    assert "MERGE (a)-[r:SHARES_MODEL_DNA]->(b)" in query and "'PGVECTOR_AUTO_SCAN'" in query
    assert "r.cosine_similarity = m.similarity" in query and "r.shared_pattern = $shared_pattern" in query
    assert params == {
        "source": "T",
        "matches": [{"bill_uid": "A", "similarity": 1.0}],
        "shared_pattern": "impact_assessment",
    }


def test_no_matches_means_no_neo4j_connection(monkeypatch):
    monkeypatch.setattr(lf, "write_copycats_to_neo4j", lambda *a, **k: pytest.fail("no matches, no Neo4j"))
    assert lf.persist_and_detect_copycats(VectorConn(), version("T"), [1.0, 0.0], "x") == []


def test_neo4j_failure_is_a_warning_and_matches_still_return(caplog):
    driver = RecordingDriver(fail=OSError("connection refused"))
    with caplog.at_level("WARNING"):
        matches = lf.persist_and_detect_copycats(
            VectorConn({"A@1": ("A", [1.0, 0.0])}), version("T"), [1.0, 0.0], "x", neo4j_driver=driver
        )
    assert matches == [{"bill_uid": "A", "similarity": 1.0}]
    assert "Neo4j copycat write for T skipped (OSError: connection refused)" in caplog.text


def test_neo4j_without_password_is_tolerated(monkeypatch, caplog):
    for name in ("NEO4J_AUTH", "NEO4J_PASSWORD"):
        monkeypatch.delenv(name, raising=False)
    with caplog.at_level("WARNING"):
        assert lf.write_copycats_to_neo4j("T", [{"bill_uid": "A", "similarity": 0.9}], "x") is False
    assert "SystemExit" in caplog.text


# Wiring


def test_scan_matrix_shows_a_copycat_line_per_bill_with_matches():
    rows = [
        {
            "rank": 1,
            "bill_uid": "CO_HB2_2100",
            "opportunity_score_vs": 85,
            "max_penalty_usd": 20000,
            "private_right_of_action": False,
            "z3_status": lf.OK_STATUS,
            "action": "GREENLIT",
            "cartridge": "cartridges/co_hb2_2100.rego",
            "copycats": [
                {"bill_uid": "CA_SB7_2100", "similarity": 0.912},
                {"bill_uid": "NY_A1_2100", "similarity": 0.8},
            ],
        },
        {"rank": 2, "bill_uid": "CO_SB1_2100", "action": "SKIPPED", "reason": "low", "copycats": []},
        {"rank": 3, "bill_uid": "CO_HB10", "action": "ERROR", "reason": "boom", "cartridge": None},
    ]
    lines = lf.format_matrix(rows).splitlines()
    assert len(lines) == 5  # header, 3 bills, 1 copycat line
    assert "CO_HB2_2100" in lines[1]
    assert lines[2].strip() == "copycats: CA_SB7_2100 0.91, NY_A1_2100 0.80"
    assert "CO_SB1_2100" in lines[3] and "CO_HB10" in lines[4]


def test_sim_threshold_flag_reaches_the_scan(monkeypatch):
    monkeypatch.setenv("LEGISCAN_API_KEY", "k")
    seen = {}
    monkeypatch.setattr(lf, "LegiScanClient", lambda key: object())
    monkeypatch.setattr(lf, "scan_state", lambda *a, **k: seen.update(k) or [])
    assert lf.main(["--scan-state", "--sim-threshold", "0.9"]) == 0
    assert seen["sim_threshold"] == 0.9
    with pytest.raises(SystemExit):
        lf.main(["--scan-state", "--sim-threshold", "1.5"])


# Real pgvector


@pytest.mark.integration
def test_copycat_sql_against_pgvector():
    psycopg = pytest.importorskip("psycopg")
    from pipeline import ensure_schema, pg_connect

    try:
        conn = pg_connect()
    except psycopg.OperationalError:
        pytest.skip("Postgres not reachable")
    run = uuid.uuid4().hex[:8]
    uid = lambda name: f"ITEST_{run}_{name}"  # noqa: E731
    try:
        ensure_schema(conn)
        stored = {"A": [2.0, 0.0], "C": [0.6, 0.8], "W": [1.0, 0.0, 0.0]}  # 1.0 (scale free), 0.6, other dims
        for name, emb in stored.items():
            lf.persist_and_detect_copycats(conn, version(uid(name)), emb, "x", sim_threshold=1.1)
        # Only rows from this run can match: other test data is a different direction or dimension
        # with near certainty, and the assertion filters on the run prefix anyway.
        matches = lf.persist_and_detect_copycats(
            conn, version(uid("T")), [1.0, 0.0], "x", neo4j_driver=RecordingDriver()
        )
        ours = [m for m in matches if m["bill_uid"].startswith(f"ITEST_{run}_")]
        assert ours == [{"bill_uid": uid("A"), "similarity": 1.0}]
    finally:
        conn.execute("DELETE FROM bill_versions WHERE bill_id LIKE %s", (f"ITEST_{run}_%",))
        conn.close()
