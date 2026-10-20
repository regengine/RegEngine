"""Live checks against the docker compose stack. Skipped when it is not up.

  docker compose up -d && .venv/bin/python -m pytest -m integration
"""

import os
import uuid

import httpx
import pytest

from compiler import compile_ir_to_rego
from ledger import append_receipt, verify_chain

pytestmark = pytest.mark.integration

OPA = os.environ.get("OPA_URL", f"http://localhost:{os.environ.get('FACTORY_OPA_PORT', '8181')}")
SAFE = {"fte_count": 250, "does_business_in_co": True, "affected_consumer_count": 15,
        "controls": {"annual_impact_assessment_completed": False, "nist_ai_rmf_aligned": True}}
BREACH = {**SAFE, "controls": {"annual_impact_assessment_completed": False, "nist_ai_rmf_aligned": False}}


@pytest.fixture(scope="module")
def opa():
    try:
        httpx.get(f"{OPA}/health", timeout=2).raise_for_status()
    except httpx.HTTPError:
        pytest.skip(f"OPA not reachable at {OPA}")
    return OPA


@pytest.fixture
def pg():
    psycopg = pytest.importorskip("psycopg")
    from pipeline import ensure_schema, pg_connect

    try:
        conn = pg_connect()
    except psycopg.OperationalError:
        pytest.skip("Postgres not reachable")
    ensure_schema(conn)
    yield conn
    conn.close()


@pytest.fixture
def deployed(opa, ir):
    pkg = f"factory.test_{uuid.uuid4().hex[:8]}"
    policy_id = pkg.replace(".", "_")
    r = httpx.put(f"{opa}/v1/policies/{policy_id}", content=compile_ir_to_rego(ir, pkg),
                  headers={"Content-Type": "text/plain"}, timeout=5)
    assert r.status_code == 200, r.text
    yield pkg.replace(".", "/")
    httpx.delete(f"{opa}/v1/policies/{policy_id}", timeout=5)


def _eval(opa, path, payload):
    r = httpx.post(f"{opa}/v1/data/{path}/result", json={"input": payload}, timeout=5)
    r.raise_for_status()
    return r.json()["result"]


def test_opa_evaluates_compiled_rego(opa, deployed):
    safe = _eval(opa, deployed, SAFE)
    assert (safe["status"], safe["violation_exposure_usd"]) == ("COMPLIANT_VIA_SAFE_HARBOR", 0)
    assert safe["rule_id"] == "US_CO_SB205_V2"
    breach = _eval(opa, deployed, BREACH)
    assert (breach["status"], breach["violation_exposure_usd"]) == ("NON_COMPLIANT_BREACH", 300000)
    done = {**SAFE, "controls": {"annual_impact_assessment_completed": True}}
    assert _eval(opa, deployed, done)["status"] == "COMPLIANT"
    small = {**BREACH, "fte_count": 49}
    assert _eval(opa, deployed, small)["status"] == "EXEMPT_OR_NOT_APPLICABLE"
    # Missing controls behave as false; missing facts make the rule not applicable.
    assert _eval(opa, deployed, {k: v for k, v in BREACH.items() if k != "controls"})["status"] == "NON_COMPLIANT_BREACH"
    assert _eval(opa, deployed, {"controls": {}})["status"] == "EXEMPT_OR_NOT_APPLICABLE"


def _append(pg, tenant, key, decision):
    return append_receipt(pg, tenant, rule_uid="US_CO_SB205_V2", version_uid="CO_SB24_205@V2",
                          input_payload=SAFE, evaluated_decision=decision, citation_uri="urn:test",
                          private_key=key)


def test_ledger_chain_and_tamper_detection(pg):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    key, tenant = Ed25519PrivateKey.generate(), f"itest-{uuid.uuid4()}"
    rows = [_append(pg, tenant, key, d) for d in ("COMPLIANT", "NON_COMPLIANT_BREACH", "COMPLIANT")]
    assert rows[1]["previous_leaf_hash"] == rows[0]["leaf_hash"]
    assert verify_chain(pg, tenant, key.public_key()) == {"ok": True, "count": 3, "first_bad": None}

    with pytest.raises(Exception, match="append only"):
        pg.execute("UPDATE compliance_audit_ledger SET evaluated_decision = 'X' WHERE tenant_id = %s", (tenant,))

    # A superuser can bypass the trigger; verify_chain must still catch the edit.
    with pg.transaction():
        pg.execute("ALTER TABLE compliance_audit_ledger DISABLE TRIGGER compliance_audit_ledger_no_mutation")
        pg.execute(
            "UPDATE compliance_audit_ledger SET evaluated_decision = 'COMPLIANT' WHERE execution_id = %s",
            (rows[1]["execution_id"],),
        )
        pg.execute("ALTER TABLE compliance_audit_ledger ENABLE TRIGGER compliance_audit_ledger_no_mutation")
    res = verify_chain(pg, tenant, key.public_key())
    assert res["ok"] is False and res["count"] == 2
    assert res["first_bad"]["seq"] == rows[1]["seq"] and res["first_bad"]["reason"] == "leaf_hash_mismatch"
