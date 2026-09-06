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
# make a "not set" case accidentally pass.
_CLEARED = (
    "REGENGINE_ENV",
    "REGENGINE_SKIP_SECRET_CHECK",
    "NEO4J_PASSWORD",
    "ADMIN_MASTER_KEY",
    "OBJECT_STORAGE_ACCESS_KEY_ID",
    "OBJECT_STORAGE_SECRET_ACCESS_KEY",
)

_SECURE_ENV = {
    "NEO4J_PASSWORD": "synthetic-neo4j-passphrase-9f2a",  # pragma: allowlist secret
    "ADMIN_MASTER_KEY": "synthetic-admin-master-key-4c7e",  # pragma: allowlist secret
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
        """The finding behind server/main.py's non-fatal default.

        With none of the four variables set — which is the state of a plain
        checkout and of any deploy that has not had all four confirmed —
        validate_production_secrets() raises on "is not set", not just on a
        known placeholder. server/main.py therefore logs rather than aborts
        unless REGENGINE_REQUIRE_SECURE_SECRETS is set, because raising here
        would crash-loop the single deployed container fleet-wide.
        """
        result = _run({"REGENGINE_ENV": "production"})
        assert result.returncode != 0
        combined = result.stdout + result.stderr
        for var in (
            "NEO4J_PASSWORD",
            "OBJECT_STORAGE_ACCESS_KEY_ID",
            "OBJECT_STORAGE_SECRET_ACCESS_KEY",
        ):
            assert f"{var} is not set" in combined
