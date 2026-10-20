"""One-shot local dry run with the Colorado SB 24-205 fixture.

  python app/local_factory.py [--tenant T]

Z3 verification, Rego compile, cartridge write, OPA evaluation, Ed25519 signed
receipts appended to the Postgres hash chain, then a full chain verification.
Uses the fixture IR (no Ollama) and skips the human approval step and Neo4j;
use pipeline.py for that flow. Reads the same environment as pipeline.py.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# `python app/local_factory.py` puts app/ on sys.path; the modules live one level up.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg  # noqa: E402
from compiler import compile_ir_to_rego  # noqa: E402
from extract import load_fixture  # noqa: E402
from pipeline import TENANT_ID, VERSION_UID, deploy_and_record, ensure_schema, package_for, pg_connect  # noqa: E402
from verify import OK_STATUS, verify_ir  # noqa: E402


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tenant", default=TENANT_ID)
    args = parser.parse_args(argv)
    try:
        out = dry_run(args.tenant)
    except psycopg.OperationalError as exc:
        print(f"Postgres unreachable ({type(exc).__name__}). Start it: docker compose up -d", file=sys.stderr)
        return 2
    print(json.dumps(out, indent=2, default=str))
    return 0 if out["chain"]["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
