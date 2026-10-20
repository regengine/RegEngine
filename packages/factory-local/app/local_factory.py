"""One-shot local dry run with the Colorado SB 24-205 fixture, or a live LegiScan bill.

  python app/local_factory.py [--tenant T]
  python app/local_factory.py --bill SB205 [--state CO] [--tenant T]
  python app/local_factory.py --bill-id 1234567 [--tenant T]

Dry run (no --bill/--bill-id): Z3 verification, Rego compile, cartridge write, OPA
evaluation, Ed25519 signed receipts appended to the Postgres hash chain, then a full
chain verification. Uses the fixture IR (no Ollama) and skips the human approval step
and Neo4j; use pipeline.py for that flow. Reads the same environment as pipeline.py.

Live bill: fetches the latest bill text from LegiScan (LEGISCAN_API_KEY), extracts a
DeonticIR through an OpenAI compatible endpoint (LLM_BASE_URL, LLM_MODEL), checks it with
Z3, compiles package cartridge.<slug>, stores the bill version and rule
(human_verified=false), then deploys and records receipts for a Z3 boundary payload.
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
from extract import load_fixture  # noqa: E402
from pipeline import (  # noqa: E402
    TENANT_ID,
    VERSION_UID,
    cartridge_name,
    deploy_and_record,
    ensure_schema,
    package_for,
    pg_connect,
)
from psycopg.types.json import Jsonb  # noqa: E402
from pydantic import Field, field_validator  # noqa: E402
from schemas import DeonticIR, Operator  # noqa: E402
from verify import OK_STATUS, model_to_dict, status_bodies, verify_ir  # noqa: E402

LEGISCAN_URL = "https://api.legiscan.com/"
MAX_LLM_CHARS = 45000


def dry_run(tenant_id: str = TENANT_ID) -> dict:
    ir = load_fixture()
    z3_result = verify_ir(ir)
    if z3_result["status"] != OK_STATUS:
        raise RuntimeError(f"refusing to deploy {ir.rule_id}: Z3 status {z3_result['status']}")
    rego = compile_ir_to_rego(ir, package_for(ir.rule_id))
    with pg_connect() as conn:
        ensure_schema(conn)
        deployed = deploy_and_record(conn, ir, ir.rule_id, rego, VERSION_UID, tenant_id)
    return {"rule_uid": ir.rule_id, "tenant_id": tenant_id, "z3_status": z3_result["status"], **deployed}


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
    "the duty. safe_harbor_control is a snake_case control that gives an affirmative defense, default "
    "nist_ai_rmf_aligned. max_penalty_usd is the per violation civil penalty in USD (0 if none stated). "
    "opportunity_score_vs is 0 to 100. Reply with JSON only."
)


def extract_deontic_ir_from_text(bill_meta: dict, client=None) -> LiveDeonticIR:
    """LLM structured extraction. rule_id is forced to bill_uid so cartridge paths are deterministic."""
    model = llm_model()
    if client is None:
        import openai

        client = openai.OpenAI(
            base_url=os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1"),
            api_key=os.environ.get("OPENAI_API_KEY", "ollama"),
        )
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
    if ir.safe_harbor_control != ir.action_required:  # otherwise turning it on also changes the action
        safe_harbor = {**breach, "controls": {**breach["controls"], ir.safe_harbor_control: True}}
        cases.append(("boundary_safe_harbor", safe_harbor, "COMPLIANT_VIA_SAFE_HARBOR", 0))
    return cases


def live_bill_run(
    api_key: str,
    state: str = "CO",
    bill: str | None = None,
    bill_id: int | None = None,
    tenant_id: str = TENANT_ID,
    legiscan: LegiScanClient | None = None,
    llm_client=None,
) -> dict:
    legiscan = legiscan or LegiScanClient(api_key)
    if bill_id is None:
        bill_id = legiscan.search_bill_id(state, bill)
    meta = legiscan.fetch_latest_bill_text(bill_id)
    live_ir = extract_deontic_ir_from_text(meta, llm_client)
    ir = DeonticIR.model_validate(live_ir.model_dump(exclude={"opportunity_score_vs"}))
    rule_uid, slug = ir.rule_id, cartridge_name(ir.rule_id)
    check = verify_with_boundary(ir)
    rego = compile_ir_to_rego(ir, f"cartridge.{slug}")
    version_uid = f"{meta['bill_uid']}@{meta['doc_id']}"
    jurisdiction = "US" if meta["state"] == "US" else f"US-{meta['state']}"
    # status is the overall verdict, so pipeline.approve refuses a rule that failed either check.
    z3_record = {
        **check["z3"],
        "status": check["status"],
        "verified": check["verified"],
        "boundary_payload": check["boundary_payload"],
    }

    with pg_connect() as conn:
        ensure_schema(conn)
        conn.execute(
            """INSERT INTO bill_versions (version_uid, bill_id, jurisdiction, title, statutory_text, source_uri,
                                          version_stage)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (version_uid) DO UPDATE SET statutory_text = EXCLUDED.statutory_text,
                   title = EXCLUDED.title, version_stage = EXCLUDED.version_stage""",
            (
                version_uid,
                meta["bill_uid"],
                jurisdiction,
                meta["title"],
                meta["full_text"],
                meta["url"],
                meta["version_stage"],
            ),
        )
        # No human review on this path: the rule is stored and deployed with human_verified = false.
        conn.execute(
            """INSERT INTO extracted_rules (rule_uid, version_uid, ir_json, rego, z3_result, human_verified,
                                            extraction_source, opportunity_score_vs, approved_at, updated_at)
               VALUES (%s, %s, %s, %s, %s, false, %s, %s, NULL, now())
               ON CONFLICT (rule_uid) DO UPDATE SET version_uid = EXCLUDED.version_uid,
                   ir_json = EXCLUDED.ir_json, rego = EXCLUDED.rego, z3_result = EXCLUDED.z3_result,
                   human_verified = false, extraction_source = EXCLUDED.extraction_source,
                   opportunity_score_vs = EXCLUDED.opportunity_score_vs, approved_at = NULL, updated_at = now()""",
            (
                rule_uid,
                version_uid,
                Jsonb(ir.model_dump(mode="json")),
                rego,
                Jsonb(z3_record),
                f"llm:{llm_model()}",
                live_ir.opportunity_score_vs,
            ),
        )
        if not check["verified"]:
            raise LiveBillError(f"refusing to deploy {rule_uid}: Z3 status {check['status']}")
        deployed = deploy_and_record(
            conn,
            ir,
            rule_uid,
            rego,
            version_uid,
            tenant_id,
            cases=boundary_cases(ir, check["boundary_payload"]),
            data_path=f"cartridge/{slug}",
        )
    return {
        "rule_uid": rule_uid,
        "version_uid": version_uid,
        "version_stage": meta["version_stage"],
        "legiscan_bill_id": bill_id,
        "doc_id": meta["doc_id"],
        "source_uri": meta["url"],
        "tenant_id": tenant_id,
        "cartridge": f"cartridges/{slug}.rego",
        "package": f"cartridge.{slug}",
        "opportunity_score_vs": live_ir.opportunity_score_vs,
        "z3_status": check["status"],
        "boundary_payload": check["boundary_payload"],
        "human_verified": False,
        **deployed,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tenant", default=TENANT_ID)
    parser.add_argument("--state", default="CO", help="LegiScan state code, or US for Congress (with --bill)")
    parser.add_argument("--bill", help="bill number, e.g. SB205; runs the live LegiScan pipeline")
    parser.add_argument("--bill-id", type=int, help="LegiScan bill_id; skips the search")
    args = parser.parse_args(argv)
    live = args.bill is not None or args.bill_id is not None
    if live and not os.environ.get("LEGISCAN_API_KEY"):
        print(
            "LEGISCAN_API_KEY is not set. Add it to .env (gitignored, never commit it), then "
            "`set -a; . ./.env; set +a` and retry. The dry run (no --bill) needs no key.",
            file=sys.stderr,
        )
        return 2
    try:
        if live:
            out = live_bill_run(os.environ["LEGISCAN_API_KEY"], args.state, args.bill, args.bill_id, args.tenant)
        else:
            out = dry_run(args.tenant)
    except psycopg.OperationalError as exc:
        print(f"Postgres unreachable ({type(exc).__name__}). Start it: docker compose up -d", file=sys.stderr)
        return 2
    except LiveBillError as exc:
        print(f"live bill failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(out, indent=2, default=str))
    return 0 if out["chain"]["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
