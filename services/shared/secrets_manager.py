"""Secrets access utilities for RegEngine.

This module provides a centralized interface for retrieving secrets from
environment variables with optional namespace-based lookups.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

import structlog

logger = structlog.get_logger("secrets")

ENVIRONMENT = os.getenv("ENVIRONMENT", "development")


def _is_production_environment(environment: Optional[str] = None) -> bool:
    """Return True when credentials must be fail-closed, not defaulted.

    An explicit ``environment`` argument wins (the credential getters accept
    one). Otherwise use the central detector in ``shared.env``
    (``REGENGINE_ENV``, then ``ENV``, then the ``DATABASE_URL`` heuristic)
    so this module cannot drift from the rest of the repo. Imported locally
    to match ``shared.auth`` and avoid import-time coupling.
    """
    if environment is not None:
        return environment.strip().lower() == "production"
    from shared.env import is_production  # noqa: PLC0415

    return is_production()


class SecretsManager:
    """Manages secrets retrieval from environment variables."""

    def __init__(self, region_name: str = "us-east-1"):
        """Initialize SecretsManager.

        Args:
            region_name: Retained for backward compatibility
        """
        self.region_name = region_name
        logger.info(
            "secrets_manager_initialized",
            environment=ENVIRONMENT,
            source="environment_variables",
        )

    @lru_cache(maxsize=128)
    def get_secret(self, secret_name: str) -> dict:
        """Retrieve a namespaced secret from environment variables (cached).

        Args:
            secret_name: Secret namespace (example: ``regengine/production/database``)

        Returns:
            Dict containing secret data

        Raises:
            RuntimeError: If secret payload is invalid JSON
        """
        env_key = f"REGENGINE_SECRET_{secret_name.upper().replace('/', '_')}"
        raw_value = os.getenv(env_key)
        if not raw_value:
            return {}

        try:
            import json

            secret_data = json.loads(raw_value)
            logger.info("secret_retrieved", secret_name=secret_name)
            return secret_data
        except Exception as exc:
            logger.exception(
                "secret_retrieval_failed",
                secret_name=secret_name,
                error=str(exc),
            )
            raise RuntimeError(f"Failed to retrieve secret {secret_name}: {exc}")

    def get_database_credentials(self, environment: Optional[str] = None) -> dict:
        """Get PostgreSQL database credentials.

        Args:
            environment: Environment name (production, staging, dev)

        Returns:
            Dict with username, password, host, port, database

        Raises:
            RuntimeError: If running in production with host or password missing
        """
        host = os.getenv("POSTGRES_HOST", "")
        password = os.getenv("POSTGRES_PASSWORD", "")
        if _is_production_environment(environment):
            missing = []
            if not host:
                missing.append("POSTGRES_HOST")
            if not password:
                missing.append("POSTGRES_PASSWORD")
            if missing:
                raise RuntimeError(
                    "Missing required database credentials in production: "
                    + ", ".join(missing)
                    + ". Set them via environment variables; "
                    + "the localhost fallback is for local development only."
                )
        elif not host:
            logger.warning("POSTGRES_HOST not set, defaulting to localhost (dev only)")
            host = "localhost"
        return {
            "username": os.getenv("POSTGRES_USER", "postgres"),
            "password": password,
            "host": host,
            "port": os.getenv("POSTGRES_PORT", "5432"),
            "database": os.getenv("POSTGRES_DB", "regengine"),
        }

    def get_neo4j_credentials(self, environment: Optional[str] = None) -> dict:
        """Get Neo4j database credentials.

        Args:
            environment: Environment name (production, staging, dev)

        Returns:
            Dict with uri, username, password

        Raises:
            RuntimeError: If running in production with uri or password missing
        """
        uri = os.getenv("NEO4J_URI") or os.getenv("NEO4J_URL", "")
        password = os.getenv("NEO4J_PASSWORD", "")
        if _is_production_environment(environment):
            missing = []
            if not uri:
                missing.append("NEO4J_URI")
            if not password:
                missing.append("NEO4J_PASSWORD")
            if missing:
                raise RuntimeError(
                    "Missing required Neo4j credentials in production: "
                    + ", ".join(missing)
                    + ". Set them via environment variables; "
                    + "the localhost fallback is for local development only."
                )
        elif not uri:
            logger.warning("NEO4J_URI not set, defaulting to localhost (dev only)")
            uri = "bolt://localhost:7687"
        return {
            "uri": uri,
            "username": os.getenv("NEO4J_USER", "neo4j"),
            "password": password,
        }

    def get_kafka_credentials(self, environment: Optional[str] = None) -> dict:
        """Get Kafka credentials.

        Args:
            environment: Environment name (production, staging, dev)

        Returns:
            Dict with bootstrap_servers, username, password, security_protocol

        Raises:
            RuntimeError: If running in production with bootstrap servers missing
        """
        servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "")
        if _is_production_environment(environment):
            if not servers:
                raise RuntimeError(
                    "Missing required Kafka credentials in production: "
                    "KAFKA_BOOTSTRAP_SERVERS. Set it via environment variables; "
                    "the localhost fallback is for local development only."
                )
        elif not servers:
            logger.warning("KAFKA_BOOTSTRAP_SERVERS not set, defaulting to localhost (dev only)")
            servers = "localhost:9092"
        return {
            "bootstrap_servers": servers,
            "username": os.getenv("KAFKA_USERNAME", ""),
            "password": os.getenv("KAFKA_PASSWORD", ""),
            "security_protocol": os.getenv("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT"),
        }

    def get_s3_credentials(self, environment: Optional[str] = None) -> dict:
        """Get object storage credentials and configuration.

        Args:
            environment: Environment name (production, staging, dev)

        Returns:
            Dict with access_key_id, secret_access_key, region, bucket_prefix, endpoint_url

        Raises:
            RuntimeError: If running in production with storage keys missing
        """
        access_key_id = os.getenv("OBJECT_STORAGE_ACCESS_KEY_ID", "")
        secret_access_key = os.getenv("OBJECT_STORAGE_SECRET_ACCESS_KEY", "")
        if _is_production_environment(environment):
            missing = []
            if not access_key_id:
                missing.append("OBJECT_STORAGE_ACCESS_KEY_ID")
            if not secret_access_key:
                missing.append("OBJECT_STORAGE_SECRET_ACCESS_KEY")
            if missing:
                raise RuntimeError(
                    "Missing required object storage credentials in production: "
                    + ", ".join(missing)
                    + ". Set them via environment variables."
                )
        return {
            "access_key_id": access_key_id,
            "secret_access_key": secret_access_key,
            "region": os.getenv("OBJECT_STORAGE_REGION", "us-east-1"),
            "bucket_prefix": os.getenv("S3_BUCKET_PREFIX", "regengine-dev"),
            "endpoint_url": os.getenv("OBJECT_STORAGE_ENDPOINT_URL", ""),
        }


# Global instance for singleton pattern
_secrets_manager: Optional[SecretsManager] = None


def get_secrets_manager(region_name: str = "us-east-1") -> SecretsManager:
    """Get the global SecretsManager instance.

    Args:
        region_name: Retained for backward compatibility

    Returns:
        SecretsManager instance
    """
    global _secrets_manager
    if _secrets_manager is None:
        _secrets_manager = SecretsManager(region_name=region_name)
    return _secrets_manager


# Convenience functions for common use cases


def get_database_credentials(environment: Optional[str] = None) -> dict:
    """Get database credentials.

    Args:
        environment: Environment name

    Returns:
        Database credentials dict
    """
    return get_secrets_manager().get_database_credentials(environment)


def get_neo4j_credentials(environment: Optional[str] = None) -> dict:
    """Get Neo4j credentials.

    Args:
        environment: Environment name

    Returns:
        Neo4j credentials dict
    """
    return get_secrets_manager().get_neo4j_credentials(environment)


def get_kafka_credentials(environment: Optional[str] = None) -> dict:
    """Get Kafka credentials.

    Args:
        environment: Environment name

    Returns:
        Kafka credentials dict
    """
    return get_secrets_manager().get_kafka_credentials(environment)


def get_s3_credentials(environment: Optional[str] = None) -> dict:
    """Get S3 credentials.

    Args:
        environment: Environment name

    Returns:
        S3 credentials dict
    """
    return get_secrets_manager().get_s3_credentials(environment)


# Production secret validation

INSECURE_DEFAULTS = {
    "NEO4J_PASSWORD": ["change-me", "password", "secret", "test", "demo", "default", "neo4j"],
    "OBJECT_STORAGE_ACCESS_KEY_ID": ["test"],
    "OBJECT_STORAGE_SECRET_ACCESS_KEY": ["test"],
}

# The only credential production always needs at startup: the database the
# monolith cannot boot without (shared/database.py raises without it).
# The localhost fallbacks in the getters are for local development only
# and never satisfy this requirement.
REQUIRED_PRODUCTION_CREDENTIALS: tuple[tuple[str, ...], ...] = (("DATABASE_URL",),)

# Kafka consumers run only when EVENT_BACKBONE=kafka (default pg).
KAFKA_PRODUCTION_CREDENTIALS: tuple[tuple[str, ...], ...] = (("KAFKA_BOOTSTRAP_SERVERS",),)

# Neo4j is absent from the release-approved production router set; its
# credentials stay fail-closed on use. Object storage is optional: absent
# keys degrade document routes to 503 while the monolith still boots.


def _production_env_label() -> str:
    """Best-effort environment label for validation log lines."""
    from shared.env import get_environment  # noqa: PLC0415

    return get_environment()


def validate_production_secrets() -> None:
    """Validate that required credentials are present and secure in production.

    This function should be called at service startup to fail fast if
    production mode is enabled with missing or insecure default credentials.

    Raises:
        RuntimeError: If running in production with missing or insecure credentials
    """
    # Only enforce in production mode, using the central detector
    # (REGENGINE_ENV, then ENV, then the DATABASE_URL heuristic).
    if not _is_production_environment():
        logger.info(
            "secrets_validation_skipped",
            environment=_production_env_label(),
            reason="not_production",
        )
        return

    env = _production_env_label()
    logger.info("validating_production_secrets", environment=env)

    # DATABASE_URL is always required; subsystem credentials join the list
    # only when their subsystem is actually enabled.
    from shared.event_backbone import kafka_enabled  # noqa: PLC0415

    required: list[tuple[str, ...]] = list(REQUIRED_PRODUCTION_CREDENTIALS)
    if kafka_enabled():
        required.extend(KAFKA_PRODUCTION_CREDENTIALS)

    errors = []

    # Every required credential must be set; the localhost fallbacks in
    # the getters must never silently stand in for them.
    for alternatives in required:
        if not any(os.getenv(var_name, "") for var_name in alternatives):
            if len(alternatives) == 1:
                errors.append(f"{alternatives[0]} is not set")
            else:
                errors.append(f"{' / '.join(alternatives)} is not set")

    # Insecure placeholders are rejected whenever SET, even for a disabled
    # subsystem — but an unset optional value is fine.
    for var_name, insecure_values in INSECURE_DEFAULTS.items():
        current_value = os.getenv(var_name, "")

        if not current_value:
            continue

        # Check if current value matches any insecure default
        for insecure_value in insecure_values:
            if current_value == insecure_value or current_value.startswith(insecure_value):
                errors.append(f"{var_name} is using an insecure default value")
                break

    if errors:
        error_msg = "Production secret validation FAILED:\n" + "\n".join(f"  - {err}" for err in errors)
        error_msg += "\n\nProduction mode requires secure credentials. Set proper values via:"
        error_msg += "\n  1. Railway environment variables"
        error_msg += "\n  2. Managed secret stores wired to runtime env"
        error_msg += "\n  3. For development, set REGENGINE_ENV=development"

        logger.error("production_secrets_validation_failed", errors=errors, environment=env)
        raise RuntimeError(error_msg)

    logger.info(
        "production_secrets_validated",
        environment=env,
        checks_passed=len(required) + len(INSECURE_DEFAULTS),
    )


def require_secure_secrets_in_production() -> None:
    """Ensure production mode does not bypass secret validation.

    Raises:
        RuntimeError: If running in production with secret checks disabled
    """
    if not _is_production_environment():
        return

    env = _production_env_label()
    if os.getenv("REGENGINE_SKIP_SECRET_CHECK", "false").lower() == "true":
        error_msg = (
            "Production mode requires secret validation to stay enabled.\n"
            "Unset REGENGINE_SKIP_SECRET_CHECK or set it to false.\n"
            "For development, set REGENGINE_ENV=development"
        )
        logger.error("secure_secrets_required_in_production", environment=env)
        raise RuntimeError(error_msg)
