"""#2808 — the insecure-default secret checks must stay wired to startup.

``validate_production_secrets()`` and ``require_secure_secrets_in_production()``
were dead code: defined, documented, and never called anywhere in the repo, so
the ``INSECURE_DEFAULTS`` table (``ADMIN_MASTER_KEY=dev-admin-key``,
``NEO4J_PASSWORD=neo4j``, the object-storage ``test`` credentials) was never
consulted and a deploy could boot on shipped placeholders. ``bd2ef97`` wired
both into ``server/main.py`` — the only deployed entrypoint (the Dockerfile
``CMD`` runs ``gunicorn server.main:app``).

The whole hazard of a dead-code finding is that the wiring can silently vanish
again, so this module pins it: the call sites exist, the escape hatch is
honoured in both directions, and the checks still reject the placeholders they
exist to reject.

Structured like ``test_auth_fail_closed.py``, which proves the same pattern for
``validate_auth_config``. All key material here is either synthetic or a
placeholder already published in ``INSECURE_DEFAULTS``.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SERVICES_DIR = REPO_ROOT / "services"
SERVER_MAIN = REPO_ROOT / "server" / "main.py"

VALIDATE_SCRIPT = (
    "import sys; "
    f"sys.path.insert(0, {str(SERVICES_DIR)!r}); "
    "from shared.secrets_manager import require_secure_secrets_in_production, "
    "validate_production_secrets; "
    "require_secure_secrets_in_production(); "
    "validate_production_secrets(); "
    "print('SECRETS_OK')"
)

# Every variable the checks consult, cleared so the host environment cannot
# make a "not set" case accidentally pass. ENV and DATABASE_URL are included
# because production detection now uses the central detector in shared.env
# (REGENGINE_ENV, then ENV, then the DATABASE_URL heuristic).
_CLEARED = (
    "REGENGINE_ENV",
    "ENV",
    "DATABASE_URL",
    "ENABLED_ROUTERS",
    "EVENT_BACKBONE",
    "REGENGINE_SKIP_SECRET_CHECK",
    "POSTGRES_HOST",
    "POSTGRES_PASSWORD",
    "NEO4J_URI",
    "NEO4J_URL",
    "NEO4J_PASSWORD",
    "ADMIN_MASTER_KEY",
    "KAFKA_BOOTSTRAP_SERVERS",
    "OBJECT_STORAGE_ACCESS_KEY_ID",
    "OBJECT_STORAGE_SECRET_ACCESS_KEY",
)

_SECURE_ENV = {
    "DATABASE_URL": "postgresql://synthetic-prod-host:5432/regengine",
    "POSTGRES_HOST": "synthetic-postgres-host",
    "POSTGRES_PASSWORD": "synthetic-postgres-passphrase-7d1c",  # pragma: allowlist secret
    "NEO4J_URI": "bolt://synthetic-neo4j:7687",
    "NEO4J_PASSWORD": "synthetic-neo4j-passphrase-9f2a",  # pragma: allowlist secret
    "ADMIN_MASTER_KEY": "synthetic-admin-master-key-4c7e",  # pragma: allowlist secret
    "KAFKA_BOOTSTRAP_SERVERS": "synthetic-kafka:9092",
    "OBJECT_STORAGE_ACCESS_KEY_ID": "SYNTHETICACCESSKEYID",  # pragma: allowlist secret
    "OBJECT_STORAGE_SECRET_ACCESS_KEY": "synthetic-object-storage-secret",  # pragma: allowlist secret
}


def _run(env_overrides: dict[str, str]) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in _CLEARED}
    env.update(env_overrides)
    return subprocess.run(
        [sys.executable, "-c", VALIDATE_SCRIPT],
        capture_output=True,
        text=True,
        env=env,
    )


# Import-only values for the deployed entrypoint: the child imports
# server.main (the gunicorn target) under production posture and exits
# without serving anything. Same shape as the OpenAPI production child.
def _synthetic_fernet_key() -> str:
    """A fresh Fernet key per parent process for the strict-auth MFA gate.

    Generated at runtime so no key material lives in the file. The child
    boots under production posture, which is always strict, and strict
    runtimes refuse to boot without a valid MFA_ENCRYPTION_KEY (#3238).
    """
    from cryptography.fernet import Fernet

    return Fernet.generate_key().decode()


_SERVER_MAIN_CHILD_ENV = {
    "REGENGINE_ENV": "production",
    "ENV": "production",
    "EVENT_BACKBONE": "pg",
    "REDIS_URL": "redis://127.0.0.1:6379/15",
    "ACCESS_TOKEN_EXPIRE_MINUTES": "5",
    "SESSION_STORE_BACKEND": "redis",
    "DATABASE_URL": "sqlite:///:memory:",
    "ADMIN_DATABASE_URL": "sqlite:///:memory:",
    "ADMIN_FALLBACK_SQLITE": "1",
    "AUTH_SECRET_KEY": "fail-closed-test-import-only-not-a-real-secret-7a1c",  # pragma: allowlist secret
    "JWT_SECRET": "fail-closed-test-import-only-not-a-real-jwt-secret-3e9d",  # pragma: allowlist secret
    "REGENGINE_API_KEY": "fail-closed-test-import-only-not-a-real-key-8b2f",  # pragma: allowlist secret
    "TOOL_ACCESS_SECRET": "fail-closed-test-import-only-not-a-real-tool-5d4a",  # pragma: allowlist secret
    "MFA_ENCRYPTION_KEY": _synthetic_fernet_key(),
}

_SERVER_MAIN_CHILD_SCRIPT = (
    f"import os, sys; sys.path.insert(0, {str(REPO_ROOT)!r}); "
    f"sys.path.insert(0, {str(SERVICES_DIR)!r}); "
    "from server.router_policy import PRODUCTION_ENABLED_ROUTERS; "
    "os.environ['ENABLED_ROUTERS'] = ','.join(sorted(PRODUCTION_ENABLED_ROUTERS)); "
    "import server.main; "
    "print('SERVER_MAIN_BOOTED')"
)

# Host-inherited knobs the production gate refuses or that would change the
# posture under test. Same scrub as the OpenAPI production child.
_SERVER_MAIN_SCRUB = _CLEARED + (
    "AUTH_TEST_BYPASS_TOKEN",
    "ALLOW_LEGACY_ENTRYPOINT_IN_PROD",
    "ALLOW_INMEMORY_SESSION_STORE",
    "AUTH_ALLOW_LEGACY_JTI_FREE",
    "ENABLE_EXPERIMENTAL_ROUTERS",
    "DISABLED_ROUTERS",
    "NEO4J_URI",
    "NEO4J_URL",
    "NEO4J_PASSWORD",
    "OBJECT_STORAGE_ACCESS_KEY_ID",
    "OBJECT_STORAGE_SECRET_ACCESS_KEY",
)


def _run_server_main(env_overrides: dict[str, str]) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in _SERVER_MAIN_SCRUB}
    env.update(_SERVER_MAIN_CHILD_ENV)
    env.update(env_overrides)
    return subprocess.run(
        [sys.executable, "-c", _SERVER_MAIN_CHILD_SCRIPT],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO_ROOT),
        timeout=300,
    )


class TestStartupWiring:
    """The deployed entrypoint uses the current auth configuration validator.

    The utility checks below cover optional integration secrets. The removed
    master-key mechanism is not restored to satisfy historical startup tests.
    """

    def test_server_main_calls_auth_validation(self):
        source = SERVER_MAIN.read_text(encoding="utf-8")
        assert "from shared.auth import validate_auth_config" in source
        assert re.search(r"^validate_auth_config\(\)", source, re.MULTILINE)

    def test_retired_master_key_is_not_a_runtime_requirement(self):
        from shared.secrets_manager import INSECURE_DEFAULTS

        assert "ADMIN_MASTER_KEY" not in INSECURE_DEFAULTS

    def test_server_main_boots_with_synthetic_database_url(self):
        """Positive case: the child env above is sufficient to import the
        deployed entrypoint under production posture. Guards the negative
        test below against passing for an unrelated import failure."""
        result = _run_server_main({})
        assert result.returncode == 0, (
            "server.main failed to import under production posture:\n" + result.stderr[-3000:]
        )
        assert "SERVER_MAIN_BOOTED" in result.stdout

    def test_server_main_refuses_skip_flag_in_production(self):
        """Importing server.main with REGENGINE_SKIP_SECRET_CHECK=true must
        refuse to boot. Deleting the wiring calls (or swallowing them in
        try/except) lets this import succeed, so this fails without the fix.
        The asserted event name proves the refusal came from the secret
        gate, not from an unrelated import error."""
        result = _run_server_main({"REGENGINE_SKIP_SECRET_CHECK": "true"})
        assert result.returncode != 0, "server.main booted with secret checks disabled"
        combined = result.stdout + result.stderr
        assert "secure_secrets_required_in_production" in combined


class TestProductionSecretValidation:
    def test_no_op_outside_production(self):
        """Development boots must be untouched, whatever the local env holds."""
        result = _run({"REGENGINE_ENV": "development"})
        assert result.returncode == 0, result.stderr
        assert "SECRETS_OK" in result.stdout

    def test_secure_values_pass_in_production(self):
        result = _run({"REGENGINE_ENV": "production", **_SECURE_ENV})
        assert result.returncode == 0, result.stderr
        assert "SECRETS_OK" in result.stdout

    @pytest.mark.parametrize(
        ("var", "insecure_value"),
        [
            ("NEO4J_PASSWORD", "neo4j"),
            ("OBJECT_STORAGE_ACCESS_KEY_ID", "test"),
        ],
    )
    def test_insecure_default_is_rejected_in_production(self, var, insecure_value):
        env = {"REGENGINE_ENV": "production", **_SECURE_ENV, var: insecure_value}
        result = _run(env)
        assert result.returncode != 0, f"{var}={insecure_value} booted without a failure"
        assert "production_secrets_validation_failed" in (result.stdout + result.stderr)
        # The failure names the variable, never its value.
        assert var in (result.stdout + result.stderr)

    def test_skip_flag_cannot_disable_the_check_in_production(self):
        result = _run(
            {
                "REGENGINE_ENV": "production",
                "REGENGINE_SKIP_SECRET_CHECK": "true",
                **_SECURE_ENV,
            }
        )
        assert result.returncode != 0
        assert "secure_secrets_required_in_production" in (result.stdout + result.stderr)

    def test_unset_secrets_fail_in_production(self):
        """Production startup fails when its required database is absent.

        Optional disabled integrations do not add missing-credential errors.
        The monolith calls this validator unconditionally before serving.
        """
        result = _run({"REGENGINE_ENV": "production"})
        assert result.returncode != 0
        combined = result.stdout + result.stderr
        assert "DATABASE_URL is not set" in combined
        for var in (
            "POSTGRES_HOST",
            "POSTGRES_PASSWORD",
            "NEO4J_PASSWORD",
            "KAFKA_BOOTSTRAP_SERVERS",
            "OBJECT_STORAGE_ACCESS_KEY_ID",
            "OBJECT_STORAGE_SECRET_ACCESS_KEY",
        ):
            assert f"{var} is not set" not in combined
        assert "NEO4J_URI / NEO4J_URL is not set" not in combined
