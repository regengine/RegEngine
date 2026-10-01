"""Cross-service collection must preserve dependencies used by existing routers."""

import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    ("collectors", "selected"),
    [
        pytest.param(
            [
                "services/graph/tests/test_compliance_export_escaping.py",
                "services/graph/tests/test_fsma_routes.py::TestTraceForwardEndpoint::test_trace_forward_success",
                "services/shared/tests/test_tenant_isolation.py",
            ],
            "test_trace_forward_success",
            id="shared-collection-preserves-graph-tenant-dependency",
        ),
        pytest.param(
            [
                "services/admin/tests/test_gdpr_neo4j_erasure_1412.py",
                "services/ingestion/tests/test_fda_export_router.py::test_export_default_returns_verifiable_zip_package",
                "services/ingestion/tests/test_routes_status_1342.py::TestGetIngestionStatus::test_running_status_no_result_fetch",
                "services/ingestion/tests/test_integration_router_1342.py::TestListAvailable::test_returns_integrations_from_registry",
                "services/scheduler/tests/test_task_queue_retention_2903.py",
            ],
            "test_export_default_returns_verifiable_zip_package or "
            "test_running_status_no_result_fetch or test_returns_integrations_from_registry",
            id="service-switch-preserves-ingestion-shared-dependencies",
        ),
    ],
)
def test_collected_router_dependencies_keep_their_identity(collectors, selected, tmp_path):
    """Only execute the existing mocked route tests; prefix modules collect only."""
    repo_root = Path(__file__).resolve().parents[1]
    # Do not pass developer credentials or live database/provider URLs to children.
    env = {key: os.environ[key] for key in ("PATH", "TMPDIR", "SYSTEMROOT") if key in os.environ}
    env.update(
        HOME=str(tmp_path),
        REGENGINE_ENV="test",
        ENVIRONMENT="test",
        PYTHONDONTWRITEBYTECODE="1",
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            *collectors,
            "-k",
            selected,
            "--no-cov",
            "-p",
            "no:cacheprovider",
        ],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
