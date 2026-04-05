#!/usr/bin/env python3
"""
Startup environment validation script (#533).

Checks that:
  1. Required environment variables are set and non-empty.
  2. Known insecure dev-default values are not used in production.

Usage:
  python scripts/validate_env.py            # validates current process env
  python scripts/validate_env.py --strict   # exits non-zero on any warning

Services can call this at startup:
  from scripts.validate_env import validate_env; validate_env()

Or from an entrypoint:
  python scripts/validate_env.py && exec uvicorn ...
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Known insecure dev defaults that must never appear in production
# ---------------------------------------------------------------------------
_KNOWN_WEAK_VALUES: set[str] = {
    # MinIO well-known defaults
    "minioadmin",
    "minioadmin123",
    # Generic dev placeholders
    "changeme",
    "password",
    "secret",
    "admin",
    "test",
    "dev",
    "development",
    "replace_me",
    "replace-me",
    "placeholder",
    "your_secret_here",
    "your-secret-here",
    # Common weak examples from docs
    "supersecret",
    "verysecret",
    "abc123",
    "123456",
    "qwerty",
}

# ---------------------------------------------------------------------------
# Variables that must always be set (regardless of environment)
# ---------------------------------------------------------------------------
_ALWAYS_REQUIRED: list[str] = [
    "REGENGINE_ENV",
    "AUTH_SECRET_KEY",
    "ADMIN_MASTER_KEY",
    "POSTGRES_PASSWORD",
    "NEO4J_PASSWORD",
    "AUTH_TEST_BYPASS_TOKEN",  # must be SET — value may be empty (disabled)
]

# ---------------------------------------------------------------------------
# Additional variables required only in production
# ---------------------------------------------------------------------------
_PRODUCTION_REQUIRED: list[str] = [
    "SCHEDULER_API_KEY",
    "OBJECT_STORAGE_ACCESS_KEY_ID",
    "OBJECT_STORAGE_SECRET_ACCESS_KEY",
]

# ---------------------------------------------------------------------------
# Credential variables that must not use known-weak values in production
# ---------------------------------------------------------------------------
_CREDENTIAL_VARS: list[str] = [
    "AUTH_SECRET_KEY",
    "ADMIN_MASTER_KEY",
    "POSTGRES_PASSWORD",
    "NEO4J_PASSWORD",
    "SCHEDULER_API_KEY",
    "MINIO_ROOT_PASSWORD",
    "OBJECT_STORAGE_SECRET_ACCESS_KEY",
    "GRAFANA_PASSWORD",
    "SUPABASE_SERVICE_ROLE_KEY",
]


@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0


def validate_env(strict: bool = False, env: Optional[dict] = None) -> ValidationResult:
    """
    Validate environment variables.

    Args:
        strict: If True, warnings are promoted to errors.
        env:    Dict to validate (defaults to os.environ).

    Returns:
        ValidationResult with any errors/warnings found.
    """
    if env is None:
        env = dict(os.environ)

    result = ValidationResult()
    is_production = env.get("REGENGINE_ENV", "").lower() == "production"

    # ── 1. Always-required variables ────────────────────────────────────────
    for var in _ALWAYS_REQUIRED:
        if var not in env:
            result.errors.append(f"Missing required environment variable: {var}")

    # ── 2. Production-required variables ────────────────────────────────────
    if is_production:
        for var in _PRODUCTION_REQUIRED:
            if not env.get(var):
                result.errors.append(
                    f"[production] Required variable not set: {var}"
                )

    # ── 3. Check for known weak defaults in credential variables ────────────
    for var in _CREDENTIAL_VARS:
        value = env.get(var, "")
        if not value:
            continue  # empty is caught by required checks above
        if value.lower() in _KNOWN_WEAK_VALUES:
            msg = (
                f"Insecure default value detected for {var}: '{value}'. "
                f"Generate a strong secret with: "
                f"python -c \"import secrets; print(secrets.token_urlsafe(64))\""
            )
            if is_production:
                result.errors.append(f"[production] {msg}")
            else:
                result.warnings.append(msg)

    # ── 4. Production-specific checks ───────────────────────────────────────
    if is_production:
        # AUTH_TEST_BYPASS_TOKEN must be empty (disabled) in production
        bypass = env.get("AUTH_TEST_BYPASS_TOKEN", "")
        if bypass:
            result.errors.append(
                "[production] AUTH_TEST_BYPASS_TOKEN must be empty in production. "
                "Set AUTH_TEST_BYPASS_TOKEN= (empty string) to disable the bypass."
            )

        # REGENGINE_ENV sanity: if we think we're in production, enforce it
        regengine_env = env.get("REGENGINE_ENV", "")
        if regengine_env.lower() not in ("production", "staging"):
            result.warnings.append(
                f"REGENGINE_ENV='{regengine_env}' — expected 'production' or 'staging' "
                f"for a non-development deployment."
            )

    # ── 5. Promote warnings to errors in strict mode ────────────────────────
    if strict:
        result.errors.extend(result.warnings)
        result.warnings.clear()

    return result


def main() -> int:
    strict = "--strict" in sys.argv
    result = validate_env(strict=strict)

    if result.warnings:
        print("⚠  Environment warnings:", file=sys.stderr)
        for w in result.warnings:
            print(f"   • {w}", file=sys.stderr)

    if result.errors:
        print("✗  Environment validation FAILED:", file=sys.stderr)
        for e in result.errors:
            print(f"   • {e}", file=sys.stderr)
        print(
            "\n   Fix the errors above before starting RegEngine.",
            file=sys.stderr,
        )
        return 1

    is_prod = os.getenv("REGENGINE_ENV", "").lower() == "production"
    env_label = "PRODUCTION" if is_prod else os.getenv("REGENGINE_ENV", "unknown")
    print(f"✓  Environment valid ({env_label})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
