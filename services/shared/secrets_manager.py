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
        """
        host = os.getenv("POSTGRES_HOST", "")
        if not host:
            logger.warning("POSTGRES_HOST not set, defaulting to localhost (dev only)")
            host = "localhost"
        return {
            "username": os.getenv("POSTGRES_USER", "postgres"),
            "password": os.getenv("POSTGRES_PASSWORD", ""),
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
        """
        uri = os.getenv("NEO4J_URI") or os.getenv("NEO4J_URL", "")
        if not uri:
            logger.warning("NEO4J_URI not set, defaulting to localhost (dev only)")
            uri = "bolt://localhost:7687"
        return {
            "uri": uri,
            "username": os.getenv("NEO4J_USER", "neo4j"),
            "password": os.getenv("NEO4J_PASSWORD", ""),
        }

    def get_kafka_credentials(self, environment: Optional[str] = None) -> dict:
        """Get Kafka credentials.

        Args:
            environment: Environment name (production, staging, dev)

        Returns:
            Dict with bootstrap_servers, username, password, security_protocol
        """
        servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "")
        if not servers:
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
        """
        return {
            "access_key_id": os.getenv("OBJECT_STORAGE_ACCESS_KEY_ID", ""),
            "secret_access_key": os.getenv("OBJECT_STORAGE_SECRET_ACCESS_KEY", ""),
            "region": os.getenv("OBJECT_STORAGE_REGION", "us-east-1"),
            "bucket_prefix": os.getenv("S3_BUCKET_PREFIX", "regengine-dev"),
            "endpoint_url": os.getenv("OBJECT_STORAGE_ENDPOINT_URL", ""),
        }

    def get_admin_master_key(self, environment: Optional[str] = None) -> str:
        """Get admin master key for API authentication.

        Args:
            environment: Environment name (production, staging, dev)

        Returns:
            Admin master key string
        """
        key = os.getenv("ADMIN_MASTER_KEY")
        if not key:
            env = os.getenv("REGENGINE_ENV", "development").lower()
            if env == "production":
                raise ValueError(
                    "ADMIN_MASTER_KEY must be set in production. "
                    "Generate a secure key and set it as an environment variable."
                )
            # Non-production: generate a random key so dev/test can proceed
            import secrets as _secrets
            key = f"dev-{_secrets.token_hex(16)}"
            logger.warning(
                "admin_master_key_not_set_using_random",
                environment=env,
            )
        return key


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


def get_admin_master_key(environment: Optional[str] = None) -> str:
    """Get admin master key.

    Args:
        environment: Environment name

    Returns:
        Admin master key
    """
    return get_secrets_manager().get_admin_master_key(environment)


# Production secret validation

INSECURE_DEFAULTS = {
    "NEO4J_PASSWORD": ["change-me", "password", "secret", "test", "demo", "default", "neo4j"],
    "ADMIN_MASTER_KEY": ["dev-admin-key", "change-in-production", "test", "demo", "default", "admin", "dev_master_key_change_in_production"],
    "OBJECT_STORAGE_ACCESS_KEY_ID": ["test"],
    "OBJECT_STORAGE_SECRET_ACCESS_KEY": ["test"],
}


def validate_production_secrets() -> None:
    """Validate that insecure default values are not used in production.

    This function should be called at service startup to fail fast if production
    mode is enabled with insecure default credentials.

    Raises:
        RuntimeError: If running in production with insecure defaults
    """
    env = os.getenv("REGENGINE_ENV", "development")

    # Only enforce in production mode
    if env.lower() != "production":
        logger.info("secrets_validation_skipped", environment=env, reason="not_production")
        return

    logger.info("validating_production_secrets", environment=env)

    errors = []

    # Check each critical secret
    for var_name, insecure_values in INSECURE_DEFAULTS.items():
        current_value = os.getenv(var_name, "")

        if not current_value:
            errors.append(f"{var_name} is not set")
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

    logger.info("production_secrets_validated", environment=env, checks_passed=len(INSECURE_DEFAULTS))


def require_secure_secrets_in_production() -> None:
    """Ensure production mode does not bypass secret validation.

    Raises:
        RuntimeError: If running in production with secret checks disabled
    """
    env = os.getenv("REGENGINE_ENV", "development")

    if env.lower() != "production":
        return

    if os.getenv("REGENGINE_SKIP_SECRET_CHECK", "false").lower() == "true":
        error_msg = (
            "Production mode requires secret validation to stay enabled.\n"
            "Unset REGENGINE_SKIP_SECRET_CHECK or set it to false.\n"
            "For development, set REGENGINE_ENV=development"
        )
        logger.error("secure_secrets_required_in_production", environment=env)
        raise RuntimeError(error_msg)
