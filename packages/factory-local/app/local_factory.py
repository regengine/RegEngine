"""Process a live LegiScan bill or scan a state for candidates.

  python app/local_factory.py [--tenant T]
  python app/local_factory.py --bill BILL [--state STATE] --tenant TENANT
  python app/local_factory.py --bill-id LEGISCAN_BILL_ID --tenant TENANT
  python app/local_factory.py --scan-state --state CO [--top-n 5] [--tenant T]
  (--bill, --bill-id and --scan-state also take --sim-threshold 0.80)

With no bill or scan input, reports "No data yet" and makes no external calls.

Live bill: fetches the latest bill text from LegiScan (LEGISCAN_API_KEY), extracts a
DeonticIR through an OpenAI compatible endpoint (LLM_BASE_URL, LLM_MODEL), checks it with
Z3, embeds a regulatory fingerprint (EMBEDDING_MODEL, default nomic-embed-text) and stores the
bill version with its embedding, then looks up copycat bills with pgvector and writes them to
Neo4j as SHARES_MODEL_DNA. Every processed bill is embedded and stored. Only when
opportunity_score_vs >= 70 and Z3 verifies it: compile package cartridge.<slug>, store the rule
(human_verified=false), then deploy and record receipts for a Z3 boundary payload.

Scan: one getMasterList call ranks the state's current bills by compliance keywords, then
runs the top N through the live bill steps and prints a ranked matrix.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import logging
import os
import re
import sys
from pathlib import Path

# `python app/local_factory.py` puts app/ on sys.path; the modules live one level up.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402
import psycopg  # noqa: E402
import z3  # noqa: E402
from compiler import compile_ir_to_rego  # noqa: E402
from pipeline import (  # noqa: E402
    TENANT_ID,
    cartridge_name,
    deploy_and_record,
    ensure_schema,
    pg_connect,
)
from psycopg.types.json import Jsonb  # noqa: E402
from pydantic import Field, field_validator  # noqa: E402
from schemas import DeonticIR, Operator  # noqa: E402
from verify import OK_STATUS, model_to_dict, status_bodies, verify_ir  # noqa: E402

from app.seed_neo4j import neo4j_settings  # noqa: E402

LEGISCAN_URL = "https://api.legiscan.com/"
MAX_LLM_CHARS = 45000
OPPORTUNITY_THRESHOLD = 70
SIM_THRESHOLD = 0.80
COPYCAT_LIMIT = 5
FINGERPRINT_TEXT_CHARS = 6000

log = logging.getLogger(__name__)

# Stage 1 masterlist triage. Case insensitive substring match on title + description.
NOISE_KEYWORDS = (
    "appropriations",
    "budget",
    "memorial",
    "highway",
    "bridge",
    "license plate",
    "congratulating",
    "commemorating",
    "school district",
)
KEYWORD_WEIGHTS = {
    "artificial intelligence": 5,
    "algorithmic": 5,
    "automated decision": 5,
    "biometric": 4,
    "privacy": 4,
    "consumer data": 4,
    "data broker": 4,
    "cybersecurity": 4,
    "emissions": 4,
    "greenhouse gas": 4,
    "extended producer responsibility": 5,
    "packaging": 3,
    "supply chain": 4,
    "pay transparency": 4,
    "employer": 3,
    "disclosure": 3,
    "reporting": 3,
    "audit": 3,
    "impact assessment": 5,
    "civil penalty": 4,
    "attorney general": 3,
    "fiduciary": 3,
    "financial": 2,
}
ACTIVE_STATUSES = range(1, 5)  # LegiScan 1 Introduced, 2 Engrossed, 3 Enrolled, 4 Passed
ADVANCED_BONUS = 3  # past introduction (status >= 2) and already relevant
MIN_CANDIDATE_SCORE = 4


class LiveBillError(RuntimeError):
    """A live bill step failed. Messages never contain the LegiScan key."""


class LegiScanClient:
    """Minimal LegiScan Pull API client. The key travels only as the `key` query parameter;
    error messages are rebuilt without the URL so the key cannot leak through them."""

    def __init__(self, api_key: str, transport: httpx.BaseTransport | None = None, timeout: float = 30.0):
        if not api_key:
            raise LiveBillError("LEGISCAN_API_KEY is empty")
        self._key = api_key
        self._http = httpx.Client(base_url=LEGISCAN_URL, transport=transport, timeout=timeout)
        # httpx logs every request URL (key included) at INFO.
        logging.getLogger("httpx").setLevel(logging.WARNING)

    def __repr__(self) -> str:
        return "LegiScanClient(api_key=***)"

    def _call(self, op: str, **params) -> dict:
        try:
            resp = self._http.get("", params={"key": self._key, "op": op, **params})
            resp.raise_for_status()
            body = resp.json()
        except httpx.HTTPStatusError as exc:
            raise LiveBillError(f"LegiScan {op} returned HTTP {exc.response.status_code}") from None
        except httpx.HTTPError as exc:
            raise LiveBillError(f"LegiScan {op} request failed ({type(exc).__name__})") from None
        except ValueError:
            raise LiveBillError(f"LegiScan {op} returned a non JSON body") from None
        if body.get("status") != "OK":
            message = (body.get("alert") or {}).get("message", "unknown error")
            raise LiveBillError(f"LegiScan {op} error: {message}")
        return body

    def search_bill_id(self, state: str, bill_number: str) -> int:
        """Exact bill number match across all sessions; the most recent last action wins.
        state may be 'US' for Congress."""
        state, wanted = state.upper(), _norm_bill_number(bill_number)
        results = self._call("getSearch", state=state, bill=bill_number, year=1)["searchresult"]
        hits = [
            r
            for k, r in results.items()
            if k != "summary" and r.get("state") == state and _norm_bill_number(r.get("bill_number", "")) == wanted
        ]
        if not hits:
            raise LiveBillError(f"LegiScan has no bill {bill_number} in {state}")
        return int(max(hits, key=lambda r: r.get("last_action_date") or "")["bill_id"])

    def fetch_state_master_candidates(self, state: str, limit: int = 5) -> list[dict]:
        """Stage 1: one getMasterList call for the state's current session, ranked by
        rank_master_candidates. Each candidate carries bill_id, number, title, status, score."""
        masterlist = self._call("getMasterList", state=state.upper())["masterlist"]
        return rank_master_candidates(masterlist, limit)

    def get_bill(self, bill_id: int) -> dict:
        return self._call("getBill", id=bill_id)["bill"]

    def get_bill_text(self, doc_id: int) -> dict:
        return self._call("getBillText", id=doc_id)["text"]

    def fetch_latest_bill_text(self, bill_id: int) -> dict:
        bill = self.get_bill(bill_id)
        if not bill.get("texts"):
            raise LiveBillError(f"LegiScan bill {bill_id} has no texts yet")
        latest = max(bill["texts"], key=lambda t: (t.get("date") or "", int(t["doc_id"])))
        text = self.get_bill_text(latest["doc_id"])
        full_text = doc_to_text(base64.b64decode(text["doc"]), text.get("mime") or latest.get("mime", ""))
        state, number = bill["state"], bill["bill_number"]
        session = bill.get("session", {}).get("session_id", "na")
        return {
            "bill_uid": f"{state}_{_norm_bill_number(number)}_{session}",
            "version_stage": latest.get("type", ""),
            "full_text": full_text,
            "state": state,
            "bill_number": number,
            "title": bill.get("title", ""),
            "doc_id": int(latest["doc_id"]),
            "url": latest.get("state_link") or bill.get("state_link") or bill.get("url", ""),
        }


def score_candidate(text: str, status: int) -> tuple[int, list[str]] | None:
    """Keyword score for one masterlist entry, or None when a noise keyword excludes it."""
    text = text.lower()
    if any(noise in text for noise in NOISE_KEYWORDS):
        return None
    matched = [kw for kw in KEYWORD_WEIGHTS if kw in text]
    score = sum(KEYWORD_WEIGHTS[kw] for kw in matched)
    if score > 0 and status >= 2:
        score += ADVANCED_BONUS
    return score, matched


def rank_master_candidates(masterlist: dict, limit: int) -> list[dict]:
    candidates = []
    for key, entry in masterlist.items():
        if key == "session" or not isinstance(entry, dict):
            continue
        status = int(entry.get("status") or 0)
        if status not in ACTIVE_STATUSES:
            continue
        title, description = entry.get("title") or "", entry.get("description") or ""
        scored = score_candidate(f"{title} {description}", status)
        if scored is None or scored[0] < MIN_CANDIDATE_SCORE:
            continue
        candidates.append(
            {
                "bill_id": int(entry["bill_id"]),
                "number": entry.get("number", ""),
                "title": title,
                "status": status,
                "score": scored[0],
                "matched": scored[1],
            }
        )
    candidates.sort(key=lambda c: (c["score"], c["status"]), reverse=True)
    return candidates[:limit]


def _norm_bill_number(number: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", number).upper()


def doc_to_text(raw: bytes, mime: str) -> str:
    """Plain text from a LegiScan doc. HTML via BeautifulSoup, PDF via pypdf."""
    if "html" in mime:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(raw, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        text = soup.get_text("\n")
    elif "pdf" in mime:
        from pypdf import PdfReader

        text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(raw)).pages)
    else:
        raise LiveBillError(f"unsupported bill text mime type {mime!r}")
    text = re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n\n", text)).strip()
    if not text:
        raise LiveBillError(f"no extractable text in the {mime} document (scanned PDF?)")
    return text


def llm_model() -> str:
    return os.environ.get("LLM_MODEL", "qwen2.5-coder:14b")


def embedding_model() -> str:
    return os.environ.get("EMBEDDING_MODEL", "nomic-embed-text")


def openai_client():
    """OpenAI compatible client for extraction and embeddings (Ollama by default)."""
    import openai

    return openai.OpenAI(
        base_url=os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1"),
        api_key=os.environ.get("OPENAI_API_KEY", "ollama"),  # pragma: allowlist secret
    )


class LiveDeonticIR(DeonticIR):
    """schemas.DeonticIR plus the LLM's market score. Only the DeonticIR part is compiled."""

    opportunity_score_vs: int = Field(ge=0, le=100, description="Commercial opportunity for a compliance vendor")

    @field_validator("rule_id")
    @classmethod
    def _rule_id_is_safe(cls, v: str) -> str:
        # Overrides the parent check by name: the model's rule_id is replaced with bill_uid, and the
        # DeonticIR built from it re-applies the strict identifier check.
        return v


LLM_SYSTEM_PROMPT = (
    "You convert one bill's text into a single DeonticIR JSON object for its main compliance duty. "
    "Use the rule_id given by the user exactly. citation is the section of law the duty adds or amends. "
    "applicability_predicates are snake_case input facts that make the duty apply (numeric thresholds use "
    "GREATER_THAN or LESS_THAN with a number). action_required is a snake_case control name that satisfies "
    "the duty. safe_harbor_control is a snake_case control only when the text establishes an affirmative "
    "defense; otherwise use null. max_penalty_usd is the per violation civil penalty in USD (0 if none stated). "
    "opportunity_score_vs is an integer 0 to 100 for how much a compliance software vendor could sell "
    "against this duty. Add up four parts: breadth of regulated entities, up to 30 (many private "
    "businesses across sectors scores high; one agency or a tiny niche scores low); enforcement "
    "severity, up to 25 (large per violation civil penalty, private right of action, attorney general "
    "enforcement); recurring work software can automate, up to 25 (impact assessments, audits, "
    "reporting, disclosures, record keeping, monitoring); certainty and timing, up to 20 (enacted or "
    "advancing, near effective date, concrete deadlines). Give 70 or more only when the duty is broad, "
    "enforceable and creates recurring compliance work. A bill that only funds, studies, names or "
    "commemorates scores below 20. Reply with JSON only."
)


def extract_deontic_ir_from_text(bill_meta: dict, client=None) -> LiveDeonticIR:
    """LLM structured extraction. rule_id is forced to bill_uid so cartridge paths are deterministic."""
    model = llm_model()
    client = client or openai_client()
    user = (
        f"rule_id: {bill_meta['bill_uid']}\n"
        f"bill: {bill_meta['state']} {bill_meta['bill_number']} ({bill_meta['version_stage']}): {bill_meta['title']}\n\n"
        f"{bill_meta['full_text'][:MAX_LLM_CHARS]}"
    )
    try:
        completion = client.beta.chat.completions.parse(
            model=model,
            messages=[{"role": "system", "content": LLM_SYSTEM_PROMPT}, {"role": "user", "content": user}],
            response_format=LiveDeonticIR,
            temperature=0,
        )
    except Exception as exc:  # openai connection, HTTP, length, or pydantic validation errors
        raise LiveBillError(f"LLM extraction with {model} failed ({type(exc).__name__}: {exc})") from exc
    message = completion.choices[0].message
    if message.parsed is None:
        raise LiveBillError(f"LLM returned no DeonticIR (refusal: {message.refusal!r})")
    return message.parsed.model_copy(update={"rule_id": bill_meta["bill_uid"]})


def fingerprint_text(bill_meta: dict, ir: DeonticIR) -> str:
    predicates = "; ".join(f"{p.fact} {p.operator.value} {p.value}" for p in ir.applicability_predicates)
    return (
        f"TITLE: {bill_meta['title']}\n"
        f"MODALITY: {ir.modality.value}\n"
        f"OBLIGATION_CONTROL: {ir.action_required}\n"
        f"SAFE_HARBOR: {ir.safe_harbor_control or ''}\n"
        f"APPLICABILITY_PREDICATES: {predicates}\n\n"
        f"{bill_meta['full_text'][:FINGERPRINT_TEXT_CHARS]}"
    )


def generate_regulatory_fingerprint_embedding(bill_meta: dict, ir: DeonticIR, client=None) -> list[float]:
    """Embedding of the bill's duty structure plus the start of its text. Bills that copy a model
    act share the control names and predicates even when their wording drifts."""
    model = embedding_model()
    client = client or openai_client()
    try:
        response = client.embeddings.create(model=model, input=fingerprint_text(bill_meta, ir))
        embedding = [float(x) for x in response.data[0].embedding]
    except Exception as exc:  # openai connection or HTTP errors, or an empty response
        raise LiveBillError(f"embedding with {model} failed ({type(exc).__name__}: {exc})") from exc
    if not embedding:
        raise LiveBillError(f"embedding with {model} returned an empty vector")
    return embedding


def _vector_literal(embedding: list[float]) -> str:
    return "[" + ",".join(repr(x) for x in embedding) + "]"


# The CTE is MATERIALIZED so the dimension filter runs before the <=> operator: Postgres may
# otherwise evaluate the similarity first, and <=> raises on vectors of different dimensions.
# DISTINCT ON keeps the best matching version of each other bill.
COPYCAT_SQL = """
WITH same_dim AS MATERIALIZED (
    SELECT bill_id, full_text_embedding FROM bill_versions
    WHERE bill_id <> %(bill_uid)s AND full_text_embedding IS NOT NULL
      AND vector_dims(full_text_embedding) = %(dims)s
), scored AS (
    SELECT DISTINCT ON (bill_id) bill_id, 1 - (full_text_embedding <=> %(target)s::vector) AS similarity
    FROM same_dim ORDER BY bill_id, similarity DESC
)
SELECT bill_id, similarity FROM scored WHERE similarity >= %(threshold)s
ORDER BY similarity DESC, bill_id LIMIT %(limit)s
"""

NEO4J_COPYCAT_CYPHER = (
    "MERGE (a:Bill {bill_uid: $source}) "
    "WITH a UNWIND $matches AS m "
    "MERGE (b:Bill {bill_uid: m.bill_uid}) "
    "MERGE (a)-[r:SHARES_MODEL_DNA]->(b) "
    "SET r.cosine_similarity = m.similarity, r.shared_pattern = $shared_pattern, "
    "r.detected_by = 'PGVECTOR_AUTO_SCAN'"
)


def write_copycats_to_neo4j(bill_uid: str, matches: list[dict], shared_pattern: str, driver=None) -> bool:
    """MERGE (a:Bill)-[:SHARES_MODEL_DNA]->(b:Bill) per match. Neo4j is optional for the live
    pipeline: any failure is logged as a warning and the bill carries on."""
    try:
        if driver is None:
            from neo4j import GraphDatabase

            uri, user, password = neo4j_settings()
            with GraphDatabase.driver(uri, auth=(user, password), connection_timeout=5) as owned:
                return write_copycats_to_neo4j(bill_uid, matches, shared_pattern, owned)
        with driver.session() as session:
            session.run(NEO4J_COPYCAT_CYPHER, source=bill_uid, matches=matches, shared_pattern=shared_pattern).consume()
        return True
    except (Exception, SystemExit) as exc:  # neo4j_settings exits when no password is configured
        log.warning("Neo4j copycat write for %s skipped (%s: %s)", bill_uid, type(exc).__name__, exc)
        return False


def persist_and_detect_copycats(
    conn: psycopg.Connection,
    version: dict,
    embedding: list[float],
    shared_pattern: str,
    rule_params: tuple | None = None,
    sim_threshold: float = SIM_THRESHOLD,
    neo4j_driver=None,
) -> list[dict]:
    """Upsert the bill version with its embedding, insert the rule when a cartridge was built
    (rule_params), then return the top COPYCAT_LIMIT other bills at or above sim_threshold
    cosine similarity and record them in Neo4j."""
    target = _vector_literal(embedding)
    conn.execute(
        """INSERT INTO bill_versions (version_uid, bill_id, jurisdiction, title, statutory_text, source_uri,
                                      full_text_embedding, version_stage)
           VALUES (%s, %s, %s, %s, %s, %s, %s::vector, %s)
           ON CONFLICT (version_uid) DO UPDATE SET statutory_text = EXCLUDED.statutory_text,
               title = EXCLUDED.title, version_stage = EXCLUDED.version_stage,
               full_text_embedding = EXCLUDED.full_text_embedding""",
        (
            version["version_uid"],
            version["bill_uid"],
            version["jurisdiction"],
            version["title"],
            version["full_text"],
            version["source_uri"],
            target,
            version["version_stage"],
        ),
    )
    if rule_params is not None:
        # No human review on this path: the rule is stored and deployed with human_verified = false.
        conn.execute(
            """INSERT INTO extracted_rules (rule_uid, version_uid, ir_json, rego, z3_result, human_verified,
                                            extraction_source, opportunity_score_vs, approved_at, updated_at)
               VALUES (%s, %s, %s, %s, %s, false, %s, %s, NULL, now())
               ON CONFLICT (rule_uid) DO UPDATE SET version_uid = EXCLUDED.version_uid,
                   ir_json = EXCLUDED.ir_json, rego = EXCLUDED.rego, z3_result = EXCLUDED.z3_result,
                   human_verified = false, extraction_source = EXCLUDED.extraction_source,
                   opportunity_score_vs = EXCLUDED.opportunity_score_vs, approved_at = NULL, updated_at = now()""",
            rule_params,
        )
    rows = conn.execute(
        COPYCAT_SQL,
        {
            "bill_uid": version["bill_uid"],
            "dims": len(embedding),
            "target": target,
            "threshold": sim_threshold,
            "limit": COPYCAT_LIMIT,
        },
    ).fetchall()
    matches = [{"bill_uid": bill_uid, "similarity": round(float(sim), 4)} for bill_uid, sim in rows]
    if matches:
        write_copycats_to_neo4j(version["bill_uid"], matches, shared_pattern, neo4j_driver)
    return matches


def _nest(flat: dict) -> dict:
    """{'org.size': 5, 'controls.x': False} -> {'org': {'size': 5}, 'controls': {'x': False}}"""
    out: dict = {}
    for path, value in flat.items():
        *parents, leaf = path.split(".")
        node = out
        for part in parents:
            node = node.setdefault(part, {})
        node[leaf] = value
    return out


def verify_with_boundary(ir: DeonticIR) -> dict:
    """verify_ir plus two live bill checks: the applicability conditions are satisfiable, and
    a breach input sitting on each numeric threshold (Z3 Optimize) as the synthetic payload."""
    z3_result = verify_ir(ir)
    if z3_result["status"] != OK_STATUS:
        return {"verified": False, "status": z3_result["status"], "boundary_payload": None, "z3": z3_result}
    bodies, env = status_bodies(ir)
    opt = z3.Optimize()
    opt.add(bodies["NON_COMPLIANT_BREACH"])
    for p in ir.applicability_predicates:
        if p.operator == Operator.GREATER_THAN:
            opt.minimize(env[p.fact])
        elif p.operator == Operator.LESS_THAN:
            opt.maximize(env[p.fact])
    if opt.check() != z3.sat:
        # Contradictory predicates (the rule can never apply) or a safe harbor control that is the
        # required action itself under PROHIBITION (it can never be breached).
        return {"verified": False, "status": "UNSAT_BREACH_UNREACHABLE", "boundary_payload": None, "z3": z3_result}
    payload = _nest(model_to_dict(opt.model(), env))
    payload.setdefault("affected_consumer_count", 1)
    return {"verified": True, "status": OK_STATUS, "boundary_payload": payload, "z3": z3_result}


def boundary_cases(ir: DeonticIR, breach: dict) -> list[tuple[str, dict, str, float]]:
    """deploy_and_record cases: the boundary breach, and the same input with the safe harbor on."""
    cases = [
        ("boundary_breach", breach, "NON_COMPLIANT_BREACH", breach["affected_consumer_count"] * ir.max_penalty_usd)
    ]
    if ir.safe_harbor_control and ir.safe_harbor_control != ir.action_required:
        safe_harbor = {**breach, "controls": {**breach["controls"], ir.safe_harbor_control: True}}
        cases.append(("boundary_safe_harbor", safe_harbor, "COMPLIANT_VIA_SAFE_HARBOR", 0))
    return cases


def process_single_bill(
    bill_id: int,
    legiscan: LegiScanClient,
    tenant_id: str = TENANT_ID,
    llm_client=None,
    threshold: int = OPPORTUNITY_THRESHOLD,
    sim_threshold: float = SIM_THRESHOLD,
) -> dict:
    """Stage 2 for one LegiScan bill: text, IR extraction, Z3, embedding. Every bill is stored in
    bill_versions with its embedding and checked for copycats. Only when opportunity_score_vs >=
    threshold and Z3 verifies: compile, store the rule, write the cartridge and load it into OPA
    (deploy_and_record). A skipped bill never touches OPA or extracted_rules. Errors raise."""
    meta = legiscan.fetch_latest_bill_text(bill_id)
    if not meta.get("full_text", "").strip():
        raise LiveBillError("No data yet: bill text is empty")
    live_ir = extract_deontic_ir_from_text(meta, llm_client)
    ir = DeonticIR.model_validate(live_ir.model_dump(exclude={"opportunity_score_vs"}))
    rule_uid, slug = ir.rule_id, cartridge_name(ir.rule_id)
    check = verify_with_boundary(ir)
    version_uid = f"{meta['bill_uid']}@{meta['doc_id']}"
    row = {
        "bill_uid": meta["bill_uid"],
        "rule_uid": rule_uid,
        "version_uid": version_uid,
        "version_stage": meta["version_stage"],
        "legiscan_bill_id": bill_id,
        "doc_id": meta["doc_id"],
        "source_uri": meta["url"],
        "tenant_id": tenant_id,
        "opportunity_score_vs": live_ir.opportunity_score_vs,
        "max_penalty_usd": ir.max_penalty_usd,
        "private_right_of_action": ir.private_right_of_action,
        "z3_status": check["status"],
        "boundary_payload": check["boundary_payload"],
        "human_verified": False,
    }
    reasons = []
    if live_ir.opportunity_score_vs < threshold:
        reasons.append(f"opportunity_score_vs {live_ir.opportunity_score_vs} < {threshold}")
    if not check["verified"]:
        reasons.append(f"Z3 status {check['status']}")

    embedding = generate_regulatory_fingerprint_embedding(meta, ir, llm_client)
    version = {
        "version_uid": version_uid,
        "bill_uid": meta["bill_uid"],
        "jurisdiction": "US" if meta["state"] == "US" else f"US-{meta['state']}",
        "title": meta["title"],
        "full_text": meta["full_text"],
        "source_uri": meta["url"],
        "version_stage": meta["version_stage"],
    }
    row = {**row, "embedding_model": embedding_model(), "embedding_dims": len(embedding)}
    if reasons:
        with pg_connect() as conn:
            ensure_schema(conn)
            copycats = persist_and_detect_copycats(
                conn, version, embedding, ir.action_required, sim_threshold=sim_threshold
            )
        return {**row, "copycats": copycats, "action": "SKIPPED", "reason": "; ".join(reasons), "cartridge": None}

    rego = compile_ir_to_rego(ir, f"cartridge.{slug}")
    z3_record = {
        **check["z3"],
        "status": check["status"],
        "verified": check["verified"],
        "boundary_payload": check["boundary_payload"],
    }
    rule_params = (
        rule_uid,
        version_uid,
        Jsonb(ir.model_dump(mode="json")),
        rego,
        Jsonb(z3_record),
        f"llm:{llm_model()}",
        live_ir.opportunity_score_vs,
    )
    with pg_connect() as conn:
        ensure_schema(conn)
        copycats = persist_and_detect_copycats(conn, version, embedding, ir.action_required, rule_params, sim_threshold)
        deployed = deploy_and_record(
            conn,
            ir,
            rule_uid,
            rego,
            version_uid,
            tenant_id,
            cases=boundary_cases(ir, check["boundary_payload"]),
            data_path=f"cartridge/{slug}",
            source_uri=meta["url"],
        )
    return {
        **row,
        "copycats": copycats,
        "action": "GREENLIT",
        "reason": None,
        "cartridge": f"cartridges/{slug}.rego",
        "package": f"cartridge.{slug}",
        **deployed,
    }


def live_bill_run(
    api_key: str,
    state: str = "CO",
    bill: str | None = None,
    bill_id: int | None = None,
    tenant_id: str = TENANT_ID,
    legiscan: LegiScanClient | None = None,
    llm_client=None,
    sim_threshold: float = SIM_THRESHOLD,
) -> dict:
    legiscan = legiscan or LegiScanClient(api_key)
    if bill_id is None:
        bill_id = legiscan.search_bill_id(state, bill)
    return process_single_bill(bill_id, legiscan, tenant_id, llm_client, sim_threshold=sim_threshold)


def scan_state(
    state: str,
    legiscan: LegiScanClient,
    top_n: int = 5,
    tenant_id: str = TENANT_ID,
    llm_client=None,
    threshold: int = OPPORTUNITY_THRESHOLD,
    sim_threshold: float = SIM_THRESHOLD,
) -> list[dict]:
    """Stage 1 then stage 2 for each candidate. A bill that errors becomes an ERROR row and the
    loop continues. Rows are ranked by opportunity_score_vs (stage 1 order breaks ties), errors last."""
    rows = []
    for c in legiscan.fetch_state_master_candidates(state, top_n):
        try:
            row = process_single_bill(
                c["bill_id"], legiscan, tenant_id, llm_client, threshold, sim_threshold=sim_threshold
            )
        except Exception as exc:  # one bad bill (LegiScan, LLM, Postgres, OPA) must not stop the scan
            row = {
                "bill_uid": f"{state.upper()}_{_norm_bill_number(c['number'])}",
                "legiscan_bill_id": c["bill_id"],
                "action": "ERROR",
                "reason": f"{type(exc).__name__}: {exc}",
                "cartridge": None,
            }
        rows.append({**row, "candidate_score": c["score"]})
    rows.sort(key=lambda r: (r["action"] == "ERROR", -(r.get("opportunity_score_vs") or 0)))
    return [{"rank": i, **r} for i, r in enumerate(rows, 1)]


def format_matrix(rows: list[dict]) -> str:
    if not rows:
        return "No data yet"
    header = ("rank", "bill_uid", "score", "max fine", "PRA", "Z3 status", "action")
    lines = []
    for r in rows:
        if r["action"] == "GREENLIT":
            action = f"GREENLIT {r['cartridge']}"
        else:
            action = f"{r['action']}: {r['reason']}"
        pra = r.get("private_right_of_action")
        lines.append(
            (
                str(r["rank"]),
                r["bill_uid"],
                "" if r.get("opportunity_score_vs") is None else str(r["opportunity_score_vs"]),
                "" if r.get("max_penalty_usd") is None else f"${r['max_penalty_usd']:,.0f}",
                "" if pra is None else ("yes" if pra else "no"),
                r.get("z3_status") or "",
                action,
            )
        )
    widths = [max(len(row[i]) for row in [header, *lines]) for i in range(len(header) - 1)]
    out = []
    for i, row in enumerate([header, *lines]):
        out.append("  ".join(cell.ljust(w) for cell, w in zip(row, widths)) + "  " + row[-1])
        if i and rows[i - 1].get("copycats"):
            out.append(f"{'':{widths[0]}}  copycats: {format_copycats(rows[i - 1]['copycats'])}")
    return "\n".join(out)


def format_copycats(matches: list[dict]) -> str:
    return ", ".join(f"{m['bill_uid']} {m['similarity']:.2f}" for m in matches) or "none"


def print_single_bill_steps(out: dict, sim_threshold: float, err=None) -> None:
    err = err or sys.stderr
    print(f"step 1 of 4: extracted {out['bill_uid']} (opportunity_score_vs {out['opportunity_score_vs']})", file=err)
    print(f"step 2 of 4: Z3 {out['z3_status']}", file=err)
    print(f"step 3 of 4: copycats >= {sim_threshold:.2f}: {format_copycats(out['copycats'])}", file=err)
    if out["action"] == "SKIPPED":
        print(
            f"step 4 of 4: SKIPPED {out['bill_uid']}: {out['reason']}; bill version and embedding stored, "
            "no rule compiled or deployed",
            file=err,
        )
    else:
        print(f"step 4 of 4: GREENLIT {out['cartridge']}, receipt chain ok={out['chain']['ok']}", file=err)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tenant", default=TENANT_ID)
    parser.add_argument(
        "--state", default="CO", help="LegiScan state code, or US for Congress (with --bill or --scan-state)"
    )
    parser.add_argument("--bill", help="bill number; runs the live LegiScan pipeline")
    parser.add_argument("--bill-id", type=int, help="LegiScan bill_id; skips the search")
    parser.add_argument("--scan-state", action="store_true", help="rank the --state masterlist and process the top N")
    parser.add_argument("--top-n", type=int, default=5, help="bills to process with --scan-state (default 5)")
    parser.add_argument(
        "--sim-threshold",
        type=float,
        default=SIM_THRESHOLD,
        help=f"cosine similarity for a copycat match, 0 to 1 (default {SIM_THRESHOLD:.2f})",
    )
    args = parser.parse_args(argv)
    single = args.bill is not None or args.bill_id is not None
    if args.scan_state and single:
        parser.error("--scan-state cannot be combined with --bill or --bill-id")
    if args.top_n < 1:
        parser.error("--top-n must be at least 1")
    if not 0 <= args.sim_threshold <= 1:
        parser.error("--sim-threshold must be between 0 and 1")
    live = single or args.scan_state
    if not live:
        print("No data yet")
        return 0
    if not args.tenant:
        print("FACTORY_TENANT_ID or --tenant is required", file=sys.stderr)
        return 2
    if live and not os.environ.get("LEGISCAN_API_KEY"):
        print(
            "LEGISCAN_API_KEY is not set. Add it to .env (gitignored, never commit it), then "
            "`set -a; . ./.env; set +a` and retry.",
            file=sys.stderr,
        )
        return 2
    try:
        if args.scan_state:
            legiscan = LegiScanClient(os.environ["LEGISCAN_API_KEY"])
            rows = scan_state(args.state, legiscan, args.top_n, args.tenant, sim_threshold=args.sim_threshold)
            if not rows:
                print("No data yet")
                return 0
            print(format_matrix(rows))
            failed = any(r["action"] == "ERROR" or not r.get("chain", {"ok": True})["ok"] for r in rows)
            return 1 if failed else 0
        if single:
            out = live_bill_run(
                os.environ["LEGISCAN_API_KEY"],
                args.state,
                args.bill,
                args.bill_id,
                args.tenant,
                sim_threshold=args.sim_threshold,
            )
    except psycopg.OperationalError as exc:
        print(f"Postgres unreachable ({type(exc).__name__}). Start it: docker compose up -d", file=sys.stderr)
        return 2
    except LiveBillError as exc:
        print(f"live bill failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(out, indent=2, default=str))
    if single:
        print_single_bill_steps(out, args.sim_threshold)
    if out.get("action") == "SKIPPED":
        return 1 if out["z3_status"] != OK_STATUS else 0  # a low score is a decision, a Z3 failure is not
    return 0 if out["chain"]["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
