import subprocess
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def test_script_imports_resolve_when_run_by_path():
    # Run from a different cwd so only the script's own sys.path fix can find the modules.
    out = subprocess.run(
        [sys.executable, str(ROOT / "app" / "local_factory.py"), "--help"],
        cwd=ROOT / "tests",
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert out.returncode == 0, out.stderr
    assert "--tenant" in out.stdout


@pytest.mark.integration
def test_dry_run_end_to_end():
    import httpx

    psycopg = pytest.importorskip("psycopg")
    from app.local_factory import dry_run
    from pipeline import opa_url

    try:
        httpx.get(f"{opa_url()}/health", timeout=2).raise_for_status()
    except httpx.HTTPError:
        pytest.skip("OPA not reachable")
    tenant = f"itest-dry-{uuid.uuid4()}"
    try:
        out = dry_run(tenant)
    except psycopg.OperationalError:
        pytest.skip("Postgres not reachable")
    assert out["z3_status"] == "UNSAT_DETERMINISTIC_AND_COMPLETE"
    assert [(e["compliance_status"], e["violation_exposure_usd"]) for e in out["evaluations"]] == [
        ("COMPLIANT_VIA_SAFE_HARBOR", 0),
        ("NON_COMPLIANT_BREACH", 300000),
    ]
    assert out["chain"] == {"ok": True, "count": 2, "first_bad": None}
    assert (ROOT / "cartridges" / "us_co_sb205.rego").exists()
