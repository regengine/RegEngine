"""Readiness verdicts must rest on structure, not substring matches.

scripts/verify_production_readiness.py used to pass a check when a token
merely appeared anywhere in the file text, so a file of comments mentioning
every token reported production ready. These tests pin the structural
behavior: comment-only fixtures fail each check, stub definitions without
the required methods fail, a workflow that references secrets without ever
invoking the Railway CLI fails, and the real repo files still pass.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "verify_production_readiness.py"

_spec = importlib.util.spec_from_file_location("verify_production_readiness", SCRIPT)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)

Verifier = _mod.ProductionReadinessVerifier

CORRELATION_REL = "services/shared/observability/correlation.py"
RATE_LIMIT_REL = "services/shared/rate_limit.py"
WORKFLOW_REL = ".github/workflows/deploy.yml"


def _verifier_with(tmp_path: Path, rel: str, body: str) -> Verifier:
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    return Verifier(tmp_path)


def test_correlation_comment_only_mentions_fail(tmp_path):
    """Every token in comments must not read as implemented."""
    body = (
        '"""Readiness notes."""\n'
        "# correlation_id_ctx\n"
        "# get_correlation_id\n"
        "# CorrelationIdMiddleware\n"
        "# X-Correlation-ID\n"
    )
    result = _verifier_with(tmp_path, CORRELATION_REL, body).check_correlation_middleware()
    assert not result.passed


def test_correlation_stub_class_without_handler_fails(tmp_path):
    """A class with the right name but no dispatch method is not middleware."""
    body = (
        "correlation_id_ctx = None\n"
        "\n"
        "\n"
        "def get_correlation_id():\n"
        "    return None\n"
        "\n"
        "\n"
        "class CorrelationIdMiddleware:\n"
        '    """X-Correlation-ID."""\n'
        "    pass\n"
    )
    result = _verifier_with(tmp_path, CORRELATION_REL, body).check_correlation_middleware()
    assert not result.passed


def test_correlation_real_file_passes():
    result = Verifier(REPO_ROOT).check_correlation_middleware()
    assert result.passed, result.details


def test_rate_limit_comment_only_mentions_fail(tmp_path):
    """Every token in comments must not read as a Redis-backed limiter."""
    body = (
        '"""Limiter notes."""\n'
        "# BruteForceLimiter\n"
        "# REGENGINE_REDIS_URL\n"
        "# REDIS_URL\n"
        "# record_failure\n"
        "# is_redis_backed\n"
    )
    result = _verifier_with(tmp_path, RATE_LIMIT_REL, body).check_rate_limit_security()
    assert not result.passed


def test_rate_limit_stub_class_without_methods_fails(tmp_path):
    """A bare class plus prose mentioning env vars is not a working limiter."""
    body = (
        '"""Uses REGENGINE_REDIS_URL or REDIS_URL with record_failure."""\n'
        "\n"
        "\n"
        "class BruteForceLimiter:\n"
        '    """is_redis_backed lives here."""\n'
        "    pass\n"
    )
    result = _verifier_with(tmp_path, RATE_LIMIT_REL, body).check_rate_limit_security()
    assert not result.passed


def test_rate_limit_real_file_passes():
    result = Verifier(REPO_ROOT).check_rate_limit_security()
    assert result.passed, result.details


def test_railway_comment_only_mentions_fail(tmp_path):
    """Tokens that appear only in YAML comments must not read as configured."""
    body = (
        "# railway\n"
        "# RAILWAY_API_TOKEN RAILWAY_PROJECT_ID RAILWAY_ENVIRONMENT_ID\n"
        "name: Deploy\n"
        "on: push\n"
        "jobs:\n"
        "  deploy:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - run: echo hello\n"
    )
    result = _verifier_with(tmp_path, WORKFLOW_REL, body).check_railway_deployment_workflow()
    assert not result.passed


def test_railway_secrets_without_cli_invocation_fail(tmp_path):
    """Secret references with no Railway CLI run step are not a deployment."""
    body = (
        "name: Deploy\n"
        "on: push\n"
        "jobs:\n"
        "  deploy:\n"
        "    runs-on: ubuntu-latest\n"
        "    env:\n"
        "      RAILWAY_API_TOKEN: ${{ secrets.RAILWAY_API_TOKEN }}\n"
        "      RAILWAY_PROJECT_ID: ${{ secrets.RAILWAY_PROJECT_ID }}\n"
        "      RAILWAY_ENVIRONMENT_ID: ${{ secrets.RAILWAY_ENVIRONMENT_ID }}\n"
        "    steps:\n"
        "      - run: echo deploying\n"
    )
    result = _verifier_with(tmp_path, WORKFLOW_REL, body).check_railway_deployment_workflow()
    assert not result.passed


def test_railway_real_workflow_passes():
    result = Verifier(REPO_ROOT).check_railway_deployment_workflow()
    assert result.passed, result.details
