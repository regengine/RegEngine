"""
SEC-004: Tests for current environment validation.
"""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
SPEC = importlib.util.spec_from_file_location(
    "_tests_validate_env",
    ROOT / "scripts" / "validate_env.py",
)
assert SPEC and SPEC.loader
validate_env_module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validate_env_module
SPEC.loader.exec_module(validate_env_module)
validate_env = validate_env_module.validate_env


def base_env(**overrides):
    env = {
        "REGENGINE_ENV": "production",
        "AUTH_SECRET_KEY": "auth-secret-with-enough-entropy",  # pragma: allowlist secret
        "ADMIN_MASTER_KEY": "admin-master-key-with-enough-entropy",  # pragma: allowlist secret
        "POSTGRES_PASSWORD": "postgres-password-with-enough-entropy",  # pragma: allowlist secret
        "DATABASE_URL": "postgresql://regengine:password@localhost:5432/regengine",  # pragma: allowlist secret
        "AUTH_TEST_BYPASS_TOKEN": "",
        "SCHEDULER_API_KEY": "scheduler-key-with-enough-entropy",  # pragma: allowlist secret
        "OBJECT_STORAGE_ACCESS_KEY_ID": "prod-access-key",  # pragma: allowlist secret
        "OBJECT_STORAGE_SECRET_ACCESS_KEY": "prod-secret-key-with-enough-entropy",  # pragma: allowlist secret
        # Added to _PRODUCTION_REQUIRED by #2911 (boot-critical: unset in
        # production, the monolith import raises and the v094 backfill refuses
        # to run) and #2912 (silent: email OTP never delivers, Stripe webhooks
        # 500). A valid production env supplies all four, so the "happy path"
        # fixture must too.
        "TOOL_ACCESS_SECRET": "tool-access-secret-with-enough-entropy",  # pragma: allowlist secret
        "AUTH_OTP_HMAC_SECRET": "otp-hmac-secret-with-enough-entropy",  # pragma: allowlist secret
        "RESEND_API_KEY": "re_prod_key_with_enough_entropy",  # pragma: allowlist secret
        "STRIPE_WEBHOOK_SECRET": "whsec_prod_with_enough_entropy",  # pragma: allowlist secret
    }
    env.update(overrides)
    return env


class TestEnvValidation:
    def test_fails_with_missing_production_secrets(self):
        result = validate_env(env={"REGENGINE_ENV": "production"})

        assert not result.ok
        assert any("AUTH_SECRET_KEY" in error for error in result.errors)
        assert any("OBJECT_STORAGE_SECRET_ACCESS_KEY" in error for error in result.errors)

    def test_passes_with_valid_production_secrets(self):
        result = validate_env(env=base_env())

        assert result.ok

    def test_rejects_weak_values_in_production(self):
        for insecure_value in [
            "change-me-in-production",
            "password",
            "secret",
            "test",
            "demo",
            "default",
            "neo4j",
        ]:
            result = validate_env(env=base_env(POSTGRES_PASSWORD=insecure_value))
            assert not result.ok, f"Should reject insecure value {insecure_value!r}"

    def test_rejects_test_object_storage_credentials_in_production(self):
        result = validate_env(
            env=base_env(
                OBJECT_STORAGE_ACCESS_KEY_ID="test",
                OBJECT_STORAGE_SECRET_ACCESS_KEY="test",
            )
        )

        assert not result.ok
        assert any("OBJECT_STORAGE" in error for error in result.errors)

    def test_warns_for_weak_values_in_development(self):
        result = validate_env(
            env=base_env(
                REGENGINE_ENV="development",
                POSTGRES_PASSWORD="password",  # pragma: allowlist secret
                SCHEDULER_API_KEY="",
                OBJECT_STORAGE_ACCESS_KEY_ID="",
                OBJECT_STORAGE_SECRET_ACCESS_KEY="",
            )
        )

        assert result.ok
        assert result.warnings


class TestEmptyStringsAreRejected:
    """#2913 — the required checks were presence-only.

    ``AUTH_SECRET_KEY=''`` — exactly what ``set -a; source .env`` produces from
    the values ``.env.example`` shipped — passed every check and the script
    printed "✓  Environment valid (PRODUCTION)".
    """

    ALWAYS_REQUIRED = validate_env_module._ALWAYS_REQUIRED

    def test_every_always_required_var_rejects_the_empty_string(self):
        for var in self.ALWAYS_REQUIRED:
            result = validate_env(env=base_env(**{var: ""}))
            assert not result.ok, f"empty {var} must not validate"
            assert any(var in error for error in result.errors), (
                f"error list must name {var}: {result.errors}"
            )

    def test_every_always_required_var_rejects_absence(self):
        for var in self.ALWAYS_REQUIRED:
            env = base_env()
            env.pop(var)
            result = validate_env(env=env)
            assert not result.ok, f"missing {var} must not validate"
            assert any(var in error for error in result.errors)

    def test_empty_auth_secret_key_in_production_names_the_variable(self):
        """Acceptance criterion 1 of #2913, verbatim."""
        result = validate_env(env=base_env(AUTH_SECRET_KEY=""))

        assert not result.ok
        assert any("AUTH_SECRET_KEY" in error for error in result.errors)

    def test_empty_secrets_rejected_outside_production_too(self):
        """_ALWAYS_REQUIRED means always — an empty dev secret is still unset."""
        result = validate_env(env=base_env(REGENGINE_ENV="development", ADMIN_MASTER_KEY=""))

        assert not result.ok
        assert any("ADMIN_MASTER_KEY" in error for error in result.errors)


class TestBypassTokenFalseRed:
    """#2913, the other half: the validator false-FAILED on a fresh .env.

    An empty ``AUTH_TEST_BYPASS_TOKEN`` is how the bypass is *disabled*, so it
    must stay presence-checked rather than joining the non-empty rule.
    """

    def test_empty_bypass_token_is_accepted(self):
        result = validate_env(env=base_env(AUTH_TEST_BYPASS_TOKEN=""))

        assert result.ok, result.errors

    def test_absent_bypass_token_is_still_an_error(self):
        env = base_env()
        env.pop("AUTH_TEST_BYPASS_TOKEN")
        result = validate_env(env=env)

        assert not result.ok
        assert any("AUTH_TEST_BYPASS_TOKEN" in error for error in result.errors)

    def test_bypass_token_is_not_in_the_non_empty_required_list(self):
        assert "AUTH_TEST_BYPASS_TOKEN" not in validate_env_module._ALWAYS_REQUIRED
        assert "AUTH_TEST_BYPASS_TOKEN" in validate_env_module._ALWAYS_PRESENT_MAY_BE_EMPTY


class TestProductionRequiredCoversBootCriticalSecrets:
    """#2911 and #2912 acceptance criteria."""

    def test_boot_critical_secrets_fail_production_validation_when_unset(self):
        """#2911: unset, the monolith import raises and migrations abort."""
        for var in ("TOOL_ACCESS_SECRET", "AUTH_OTP_HMAC_SECRET"):
            env = base_env()
            env.pop(var)
            result = validate_env(env=env)
            assert not result.ok, f"production env without {var} must not validate"
            assert any(var in error for error in result.errors)

    def test_resend_and_stripe_fail_production_validation_when_unset(self):
        """#2912: unset, login silently never delivers and webhooks 500."""
        for var in ("RESEND_API_KEY", "STRIPE_WEBHOOK_SECRET"):
            result = validate_env(env=base_env(**{var: ""}))
            assert not result.ok, f"production env without {var} must not validate"
            assert any(var in error for error in result.errors)

    def test_these_are_not_required_outside_production(self):
        env = base_env(REGENGINE_ENV="development")
        for var in (
            "TOOL_ACCESS_SECRET",
            "AUTH_OTP_HMAC_SECRET",
            "RESEND_API_KEY",
            "STRIPE_WEBHOOK_SECRET",
        ):
            env.pop(var)
        result = validate_env(env=env)

        assert result.ok, result.errors


class TestEnvExampleDocumentsWhatValidateEnvRequires:
    """#2911 / #2912 / #2914 — the template and the validator must agree.

    ``.env.example:12`` tells operators to run ``scripts/validate_env.py``. A
    variable the validator demands but the template never mentions is a
    guaranteed first-run failure with no way to discover the fix.
    """

    @property
    def env_example(self) -> str:
        return (Path(__file__).parent.parent.parent / ".env.example").read_text()

    def _declared_names(self) -> set[str]:
        names = set()
        for line in self.env_example.splitlines():
            stripped = line.lstrip().lstrip("#").strip()
            if "=" in stripped:
                key = stripped.split("=", 1)[0].strip()
                if key and key.replace("_", "").isalnum():
                    names.add(key)
        return names

    def test_every_validator_required_variable_is_in_the_template(self):
        declared = self._declared_names()
        required = (
            validate_env_module._ALWAYS_REQUIRED
            + validate_env_module._ALWAYS_PRESENT_MAY_BE_EMPTY
            + validate_env_module._PRODUCTION_REQUIRED
        )
        missing = [var for var in required if var not in declared]

        assert not missing, f".env.example does not document: {missing}"

    def test_bypass_token_is_uncommented_so_a_fresh_env_validates(self):
        """#2913 acceptance criterion 2: no false-red on `cp .env.example .env`."""
        assert any(
            line.strip() == "AUTH_TEST_BYPASS_TOKEN="
            for line in self.env_example.splitlines()
        ), "AUTH_TEST_BYPASS_TOKEN must be present-but-empty, not commented out"

    def test_router_control_variables_are_documented(self):
        """#2914 acceptance criterion 2."""
        declared = self._declared_names()
        for var in (
            "DISABLED_ROUTERS",
            "ENABLE_EXPERIMENTAL_ROUTERS",
            "ALLOW_DISABLE_COMPLIANCE_ROUTERS",
        ):
            assert var in declared, f".env.example does not document {var}"

    def test_disabled_routers_carries_the_boot_abort_warning(self):
        """Naming a compliance router aborts startup; the template must say so."""
        content = self.env_example

        assert "ALLOW_DISABLE_COMPLIANCE_ROUTERS" in content
        for router in (
            "canonical_records",
            "rules",
            "exceptions",
            "remediation",
            "fda_export",
            "chain_verification",
        ):
            assert router in content, f"compliance-critical router {router} unnamed"

    def test_documented_compliance_routers_match_the_code(self):
        """Guard against the doc drifting from server/main.py._COMPLIANCE_ROUTERS."""
        main_py = (Path(__file__).parent.parent.parent / "server" / "main.py").read_text()
        block = main_py.split("_COMPLIANCE_ROUTERS = {", 1)[1].split("}", 1)[0]
        code_routers = {
            part.strip().strip('",').strip("'")
            for part in block.split("\n")
            if part.strip().startswith(('"', "'"))
        }

        content = self.env_example
        for router in code_routers:
            assert router in content, (
                f"{router} is compliance-critical in server/main.py but is not "
                f"named in the .env.example boot-abort warning"
            )


class TestEnvExample:
    def test_env_example_has_no_real_secrets(self):
        env_example_path = Path(__file__).parent.parent.parent / ".env.example"
        content = env_example_path.read_text()

        for line in content.split("\n"):
            if line.startswith("ADMIN_MASTER_KEY="):
                value = line.split("=", 1)[1].strip()
                assert value == "" or "your-" in value.lower() or value.startswith("#"), (
                    f"ADMIN_MASTER_KEY should be empty in example: {line}"
                )


class TestDevCompose:
    def test_dev_compose_exists(self):
        dev_compose_path = Path(__file__).parent.parent.parent / "docker-compose.dev.yml"
        assert dev_compose_path.exists(), "docker-compose.dev.yml should exist"

    def test_dev_compose_is_postgres_only(self):
        content = (Path(__file__).parent.parent.parent / "docker-compose.dev.yml").read_text()

        assert "postgres:" in content
        assert "redpanda" not in content.lower()
        assert "neo4j" not in content.lower()
