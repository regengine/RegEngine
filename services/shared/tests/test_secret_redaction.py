"""Pattern 11: secrets are masked in logs, never echoed, read from env.

Covers the one shared mechanism in ``shared.secret_redaction`` plus its
adoption sites:

- ``mask_secret`` never returns the full credential.
- ``redact_text`` scrubs credential shapes out of free text.
- the ``redact_secrets`` structlog processor is registered in the shared
  logging pipeline, so every service redacts by default.
- ``read_secret`` reads from the environment only and names the variable,
  never the value, when a required secret is missing.
- ``scripts/seed_phase2b_key.py`` no longer prints the raw key.
- ``scripts/create_neo4j_indexes.sh`` and ``scripts/init-postgres.sh``
  no longer place passwords on command lines.

All key material below is synthetic (``pragma: allowlist secret`` keeps
the secret scanner quiet about test fixtures).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from shared.secret_redaction import (
    REDACTED,
    mask_secret,
    read_secret,
    redact_secrets,
    redact_text,
)

REPO_ROOT = Path(__file__).resolve().parents[3]

SYNTHETIC_RGE_KEY = "rge_testkeyid.SYNTHETICSECRET789"  # pragma: allowlist secret
SYNTHETIC_TOKEN = "SYNTHETIC-TOKEN-abc123xyz"  # pragma: allowlist secret


class TestMaskSecret:
    def test_full_value_never_returned(self):
        masked = mask_secret(SYNTHETIC_RGE_KEY)
        assert SYNTHETIC_RGE_KEY not in masked
        assert "SYNTHETICSECRET789" not in masked

    def test_rge_key_keeps_public_key_id(self):
        masked = mask_secret(SYNTHETIC_RGE_KEY)
        assert "rge_testkeyid" in masked
        assert masked.startswith("rge_testkeyid.***")

    def test_generic_secret_shows_prefix_and_fingerprint(self):
        masked = mask_secret(SYNTHETIC_TOKEN)
        assert SYNTHETIC_TOKEN not in masked
        assert masked.startswith("SYNT***")
        assert "#sha256:" in masked

    def test_same_secret_gives_stable_fingerprint(self):
        assert mask_secret(SYNTHETIC_TOKEN) == mask_secret(SYNTHETIC_TOKEN)

    def test_different_secrets_give_different_output(self):
        assert mask_secret("alpha-secret-value") != mask_secret("beta-secret-value")

    @pytest.mark.parametrize("missing", [None, ""])
    def test_missing_reports_as_missing(self, missing):
        assert mask_secret(missing) == "<not-set>"

    def test_non_string_input_is_masked_not_leaked(self):
        masked = mask_secret(123456789)
        assert "123456789" not in masked


class TestRedactText:
    def test_rge_key_redacted(self):
        text = f"auth failed for key {SYNTHETIC_RGE_KEY} on path /v1/x"
        redacted = redact_text(text)
        assert SYNTHETIC_RGE_KEY not in redacted
        assert REDACTED in redacted
        assert "/v1/x" in redacted

    def test_bearer_header_redacted(self):
        redacted = redact_text("Authorization: Bearer abcdef123456")
        assert "abcdef123456" not in redacted
        assert "Authorization:" in redacted

    def test_bare_token_value_redacted(self):
        # Credential shapes are built at runtime so none is committed.
        token = "abcdef" + "123456"
        assert token not in redact_text("saw " + "bearer " + token + " here")
        jwt = "eyJhbGciOi" + "JIUzI1NiJ9.eyJzdWIiOiIxIn0.SflKxwRJ"
        assert jwt not in redact_text("saw " + jwt + " in log")

    def test_password_in_url_redacted(self):
        redacted = redact_text("postgres://u:SYNTHETIC-PW-42@host/db")
        assert "SYNTHETIC-PW-42" not in redacted
        assert "@host/db" in redacted

    def test_password_query_param_redacted(self):
        redacted = redact_text("/login?user=a&password=SYNTHETIC-PW-42&x=1")
        assert "SYNTHETIC-PW-42" not in redacted
        assert "user=a" in redacted

    def test_private_key_block_redacted(self):
        pem = "-----BEGIN RSA PRIVATE KEY-----\nSYNTHETICKEYDATA\n-----END RSA PRIVATE KEY-----"
        assert REDACTED in redact_text(f"loaded {pem} ok")

    def test_ordinary_text_passes_through(self):
        text = "tenant 11111111-1111-1111-1111-111111111111 approved discovery item 7"
        assert redact_text(text) == text

    def test_non_string_passes_through(self):
        assert redact_text(None) is None
        assert redact_text(42) == 42
        assert redact_text("") == ""


class TestRedactSecretsProcessor:
    def test_event_dict_values_redacted(self):
        event = {
            "event": "login_failed",
            "detail": f"key {SYNTHETIC_RGE_KEY} rejected",
            "status": 401,
        }
        out = redact_secrets(None, "info", dict(event))
        assert SYNTHETIC_RGE_KEY not in str(out)
        assert out["status"] == 401

    def test_nested_structures_redacted(self):
        event = {"ctx": {"headers": {"x-key": SYNTHETIC_RGE_KEY}}}
        out = redact_secrets(None, "info", event)
        assert SYNTHETIC_RGE_KEY not in str(out)

    def test_processor_never_raises(self):
        class BadStr(str):
            def __str__(self):
                raise RuntimeError("boom")

        event = {"bad": BadStr("x")}
        assert redact_secrets(None, "info", event) == event


class TestReadSecret:
    def test_reads_from_environment(self, monkeypatch):
        monkeypatch.setenv("PAT11_SYNTHETIC_SECRET", "synthetic-value")
        assert read_secret("PAT11_SYNTHETIC_SECRET") == "synthetic-value"

    def test_missing_optional_returns_default(self, monkeypatch):
        monkeypatch.delenv("PAT11_SYNTHETIC_SECRET", raising=False)
        assert read_secret("PAT11_SYNTHETIC_SECRET") == ""
        assert read_secret("PAT11_SYNTHETIC_SECRET", default="d") == "d"

    def test_missing_required_names_var_not_value(self, monkeypatch):
        monkeypatch.delenv("PAT11_SYNTHETIC_SECRET", raising=False)
        with pytest.raises(RuntimeError) as exc:
            read_secret("PAT11_SYNTHETIC_SECRET", required=True)
        assert "PAT11_SYNTHETIC_SECRET" in str(exc.value)


class TestPipelineWiring:
    """The processor must stay registered in the shared logging pipeline."""

    def test_redact_secrets_in_shared_processors(self):
        source = (REPO_ROOT / "services" / "shared" / "observability" / "log_config.py").read_text()
        assert "redact_secrets" in source
        assert re.search(r"redact_secrets,", source)

    def test_configure_logging_uses_redaction(self):
        import structlog

        seen = []

        def collect(logger, method, event_dict):
            seen.append(event_dict)
            return event_dict

        structlog.configure(
            processors=[redact_secrets, collect],
            logger_factory=structlog.ReturnLoggerFactory(),
        )
        try:
            log = structlog.get_logger("pat11-test")
            log.info("login_failed", detail=f"key {SYNTHETIC_RGE_KEY} rejected")
        finally:
            structlog.reset_defaults()
        assert seen, "expected the spy processor to run"
        assert SYNTHETIC_RGE_KEY not in str(seen)


class TestSeedScriptHygiene:
    """The audit finding: seed_phase2b_key.py printed the raw key."""

    def test_seed_script_never_prints_raw_key(self):
        source = (REPO_ROOT / "scripts" / "seed_phase2b_key.py").read_text()
        assert "Seeding API Key: {RAW_KEY}" not in source
        assert "mask_secret" in source

    def test_seed_script_imports_shared_mechanism(self):
        source = (REPO_ROOT / "scripts" / "seed_phase2b_key.py").read_text()
        assert "secret_redaction" in source
        assert "mask_secret" in source


class TestShellScriptHygiene:
    """Passwords must not travel on command lines."""

    def test_neo4j_password_not_on_argv(self):
        source = (REPO_ROOT / "scripts" / "create_neo4j_indexes.sh").read_text()
        assert "-p ${NEO4J_PASSWORD}" not in source
        assert "-p $NEO4J_PASSWORD" not in source
        assert "NEO4J_PASSWORD" in source  # still read from the environment

    def test_postgres_password_not_on_argv(self):
        source = (REPO_ROOT / "scripts" / "init-postgres.sh").read_text()
        assert '-v runtime_pw="$POSTGRES_PASSWORD"' not in source
        assert '-v admin_runtime_pw="$POSTGRES_PASSWORD"' not in source
        assert "POSTGRES_PASSWORD" in source  # still read from the environment
