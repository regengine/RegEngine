"""factory-local pipeline CLI.

python pipeline.py run --text PATH --bill-id ID --version-uid UID --title TITLE --jurisdiction CODE --source-uri URI
                                                extract, compile, verify, store (unverified)
python pipeline.py approve --rule RULE           reports no data until cases are supplied through the API
python pipeline.py verify-chain [--tenant T]    recompute and check the receipt chain
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote

import httpx
import psycopg
from compiler import compile_ir_to_rego
from extract import extract_ir
from ledger import DEFAULT_KEY_PATH, append_receipt, load_or_create_signing_key, verify_chain
from psycopg.types.json import Jsonb
from schemas import DeonticIR
from verify import OK_STATUS, verify_ir

ROOT = Path(__file__).resolve().parent
CARTRIDGES = ROOT / "cartridges"
TENANT_ID = os.environ.get("FACTORY_TENANT_ID", "")


def pg_connect() -> psycopg.Connection:
    return psycopg.connect(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("FACTORY_PG_PORT", "5432")),
        user=os.environ.get("POSTGRES_USER", "factory"),
        password=os.environ["POSTGRES_PASSWORD"],
        dbname=os.environ.get("POSTGRES_DB", "factory"),
        autocommit=True,
        connect_timeout=5,
    )


def ensure_schema(conn: psycopg.Connection) -> None:
    """Apply db_init/*.sql in order (each is idempotent). The compose initdb mount alone is
    not enough when the Docker VM does not share this directory (colima default mounts)."""
    for sql in sorted((ROOT / "db_init").glob("*.sql")):
        conn.execute(sql.read_text())


def opa_url() -> str:
    return os.environ.get("OPA_URL", f"http://localhost:{os.environ.get('FACTORY_OPA_PORT', '8181')}").rstrip("/")


def cartridge_name(rule_uid: str) -> str:
    """Remove a version suffix from the policy path."""
    return re.sub(r"_V\d+$", "", rule_uid).lower()


def package_for(rule_uid: str) -> str:
    return f"factory.{cartridge_name(rule_uid)}"


def citation_uri(source_uri: str, citation: str) -> str:
    return f"{source_uri}#{quote(citation)}"


def run(
    text_path: Path | None = None,
    *,
    bill_id: str | None = None,
    version_uid: str | None = None,
    title: str | None = None,
    jurisdiction: str | None = None,
    source_uri: str | None = None,
) -> dict:
    if text_path is None or not text_path.is_file():
        return {"message": "No data yet"}
    text = text_path.read_text()
    if not text.strip():
        return {"message": "No data yet"}
    if not all((bill_id, version_uid, title, jurisdiction, source_uri)):
        return {"message": "No data yet: bill metadata required"}
    ir, source = extract_ir(text)
    if ir is None:
        return {"message": source}
    with pg_connect() as conn:
        ensure_schema(conn)
        conn.execute(
            """INSERT INTO bill_versions (version_uid, bill_id, jurisdiction, title, statutory_text, source_uri)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (version_uid) DO UPDATE SET statutory_text = EXCLUDED.statutory_text""",
            (version_uid, bill_id, jurisdiction, title, text, source_uri),
        )

    rego = compile_ir_to_rego(ir, package_for(ir.rule_id))
    z3_result = verify_ir(ir)

    with pg_connect() as conn:
        # Re-extraction always resets approval: a human must review the new output.
        conn.execute(
            """INSERT INTO extracted_rules (rule_uid, version_uid, ir_json, rego, z3_result, human_verified,
                                            extraction_source, approved_at, updated_at)
               VALUES (%s, %s, %s, %s, %s, false, %s, NULL, now())
               ON CONFLICT (rule_uid) DO UPDATE SET version_uid = EXCLUDED.version_uid,
                   ir_json = EXCLUDED.ir_json, rego = EXCLUDED.rego, z3_result = EXCLUDED.z3_result,
                   human_verified = false, extraction_source = EXCLUDED.extraction_source,
                   approved_at = NULL, updated_at = now()""",
            (ir.rule_id, version_uid, Jsonb(ir.model_dump(mode="json")), rego, Jsonb(z3_result), source),
        )
    return {
        "rule_uid": ir.rule_id,
        "extraction_source": source,
        "z3_status": z3_result["status"],
        "human_verified": False,
    }


def wait_for_opa_policy(rego: str, timeout: float = 30.0) -> bool:
    """True once OPA holds a module whose raw text is exactly `rego`."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            policies = httpx.get(f"{opa_url()}/v1/policies", timeout=5).json().get("result", [])
            if any(p.get("raw") == rego for p in policies):
                return True
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    return False


def deploy_to_opa(rule_uid: str, rego: str, watch_timeout: float = 10.0) -> str:
    """Prefer the --watch load of cartridges/. When the Docker VM does not share or
    forward this directory (colima), push the same text through the policy API."""
    if wait_for_opa_policy(rego, watch_timeout):
        return "watch"
    resp = httpx.put(
        f"{opa_url()}/v1/policies/factory_local/{cartridge_name(rule_uid)}",
        content=rego,
        headers={"Content-Type": "text/plain"},
        timeout=10,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"OPA rejected the policy: {resp.status_code} {resp.text}")
    if not wait_for_opa_policy(rego, 10.0):
        raise TimeoutError("OPA accepted the policy but does not report it as loaded")
    return "api"


def evaluate(rule_uid: str, payload: dict, data_path: str | None = None) -> dict:
    """POST to /v1/data/<data_path>. The default reads the `result` object of the rule's package."""
    path = data_path or package_for(rule_uid).replace(".", "/") + "/result"
    resp = httpx.post(f"{opa_url()}/v1/data/{path}", json={"input": payload}, timeout=10)
    resp.raise_for_status()
    body = resp.json()
    if "result" not in body:
        raise RuntimeError(f"OPA returned no result for {path}")
    return body["result"]


def approve(rule_uid: str, cases: list[tuple[str, dict, str, float]] | None = None, tenant_id: str = TENANT_ID) -> dict:
    if not cases:
        return {"message": "No data yet: evaluation cases required"}
    if not tenant_id:
        raise ValueError("tenant_id is required for evaluation receipts")
    with pg_connect() as conn:
        row = conn.execute(
            """SELECT r.ir_json, r.rego, r.z3_result, r.version_uid, b.source_uri
               FROM extracted_rules r JOIN bill_versions b USING (version_uid) WHERE r.rule_uid = %s""",
            (rule_uid,),
        ).fetchone()
        if row is None:
            raise LookupError(f"no extracted rule {rule_uid}; run `python pipeline.py run` first")
        ir_json, rego, z3_result, version_uid, source_uri = row
        if z3_result.get("status") != OK_STATUS:
            raise RuntimeError(f"refusing to deploy {rule_uid}: Z3 status {z3_result.get('status')}")
        ir = DeonticIR.model_validate(ir_json)
        # The deployed text must be exactly what the verified IR compiles to.
        if compile_ir_to_rego(ir, package_for(rule_uid)) != rego:
            raise RuntimeError(f"refusing to deploy {rule_uid}: stored rego does not match its IR")

        conn.execute(
            "UPDATE extracted_rules SET human_verified = true, approved_at = now(), updated_at = now() "
            "WHERE rule_uid = %s",
            (rule_uid,),
        )
        deployed = deploy_and_record(
            conn, ir, rule_uid, rego, version_uid, tenant_id=tenant_id, cases=cases, source_uri=source_uri
        )
    return {"rule_uid": rule_uid, "human_verified": True, **deployed}


def deploy_and_record(
    conn: psycopg.Connection,
    ir: DeonticIR,
    rule_uid: str,
    rego: str,
    version_uid: str,
    tenant_id: str = TENANT_ID,
    cases: list[tuple[str, dict, str, float]] | None = None,
    data_path: str | None = None,
    source_uri: str = "",
) -> dict:
    """Deploy a verified rule and evaluate only explicitly supplied cases."""
    cases = cases or []
    if cases and (not tenant_id or not source_uri):
        raise ValueError("tenant_id and source_uri are required for evaluation receipts")
    if not cases:
        return {"message": "No data yet: evaluation cases required", "evaluations": [], "receipts": []}
    CARTRIDGES.mkdir(exist_ok=True)
    (CARTRIDGES / f"{cartridge_name(rule_uid)}.rego").write_text(rego)
    loaded_via = deploy_to_opa(rule_uid, rego)

    evaluations = []
    for name, payload, want_status, want_exposure in cases:
        got = evaluate(rule_uid, payload, data_path)
        if got["compliance_status"] != want_status or got["violation_exposure_usd"] != want_exposure:
            raise AssertionError(
                f"{name}: expected {want_status}/{want_exposure}, "
                f"got {got['compliance_status']}/{got['violation_exposure_usd']}"
            )
        evaluations.append(
            {
                "case": name,
                "compliance_status": got["compliance_status"],
                "violation_exposure_usd": got["violation_exposure_usd"],
            }
        )

    key = load_or_create_signing_key()
    receipts = []
    for (name, payload, _, _), ev in zip(cases, evaluations):
        r = append_receipt(
            conn,
            tenant_id,
            rule_uid=rule_uid,
            version_uid=version_uid,
            input_payload=payload,
            evaluated_decision=ev["compliance_status"],
            citation_uri=citation_uri(source_uri, ir.citation),
            private_key=key,
        )
        receipts.append({"case": name, "seq": r["seq"], "leaf_hash": r["leaf_hash"]})
    chain = verify_chain(conn, tenant_id, key.public_key())
    return {"opa_loaded_via": loaded_via, "evaluations": evaluations, "receipts": receipts, "chain": chain}


def verify_chain_cmd(tenant_id: str) -> dict:
    if not tenant_id:
        return {"message": "No data yet"}
    if not DEFAULT_KEY_PATH.exists():
        raise FileNotFoundError(f"no signing key at {DEFAULT_KEY_PATH}; run approve first")
    key = load_or_create_signing_key()
    with pg_connect() as conn:
        return {"tenant_id": tenant_id, **verify_chain(conn, tenant_id, key.public_key())}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    rp = sub.add_parser("run")
    rp.add_argument("--text", type=Path)
    rp.add_argument("--bill-id")
    rp.add_argument("--version-uid")
    rp.add_argument("--title")
    rp.add_argument("--jurisdiction")
    rp.add_argument("--source-uri")
    ap = sub.add_parser("approve")
    ap.add_argument("--rule", required=True)
    vp = sub.add_parser("verify-chain")
    vp.add_argument("--tenant", default=TENANT_ID)
    args = parser.parse_args(argv)
    try:
        if args.cmd == "run":
            out = run(
                args.text,
                bill_id=args.bill_id,
                version_uid=args.version_uid,
                title=args.title,
                jurisdiction=args.jurisdiction,
                source_uri=args.source_uri,
            )
        elif args.cmd == "approve":
            out = approve(args.rule)
        else:
            out = verify_chain_cmd(args.tenant)
    except psycopg.OperationalError as exc:
        print(f"Postgres unreachable ({type(exc).__name__}). Start it: docker compose up -d", file=sys.stderr)
        return 2
    print(json.dumps(out, indent=2, default=str))
    return 0 if out.get("ok", out.get("chain", {}).get("ok", True)) else 1


if __name__ == "__main__":
    sys.exit(main())
