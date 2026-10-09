"""setup_production.sh must describe the consolidated monolith, not Phase 1A.

Audit finding: scripts/setup_production.sh referenced per-service Railway
roots (services/admin, services/ingestion, services/compliance,
services/graph), the retired Phase 1A migration/health scripts, and a
runbook path that no longer exists. Production is a single Railway service
built from the repo-root Dockerfile running server.main:app, with Alembic
migrations via scripts/run-migrations.sh (see scripts/deploy_railway.sh and
docs/operations/FSMA_RAILWAY_DEPLOYMENT.md).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "setup_production.sh"


def _source() -> str:
    return SCRIPT.read_text()


def test_no_per_service_deploy_roots():
    src = _source()
    assert "using these roots:" not in src
    for root in ("- services/admin", "- services/ingestion", "- services/compliance"):
        assert root not in src, f"stale per-service deploy root: {root}"
    # services/graph/... is still the legitimate Neo4j constraints helper
    # path (also used by scripts/deploy_railway.sh); only the deploy-root
    # bullet form is stale.
    assert "\n   - services/graph\n" not in src


def test_no_phase1a_runner_as_instruction():
    src = _source()
    assert "bash scripts/railway/run_phase1a_migrations.sh" not in src
    assert "bash scripts/railway/verify_phase1a_health.sh" not in src


def test_runbook_path_is_current():
    src = _source()
    assert "docs/operations/FSMA_RAILWAY_DEPLOYMENT.md" in src
    assert "docs/FSMA_RAILWAY_DEPLOYMENT.md" not in src


def test_points_at_monolith_flow():
    src = _source()
    assert "server.main" in src
    assert "scripts/run-migrations.sh" in src
    assert "scripts/deploy_railway.sh" in src


def test_script_syntax_checks():
    result = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
