"""AWS Secrets Manager integration for RegEngine.

This module provides a centralized interface for retrieving secrets from
AWS Secrets Manager with local development fallback.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Optional

import structlog

logger = structlog.get_logger("secrets")

# Flag to determine if we should use AWS Secrets Manager
USE_AWS_SECRETS = os.getenv("USE_AWS_SECRETS", "false").lower() == "true"
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")


class SecretsManager:
    """Manages secrets retrieval from AWS Secrets Manager or environment variables."""

    def __init__(self, region_name: str = "us-east-1"):
        """Initialize SecretsManager.

        Args:
            region_name: AWS region for Secrets Manager
        """
        self.region_name = region_name
        self._client = None

        if USE_AWS_SECRETS:
            try:
                import boto3

                self._client = boto3.client("secretsmanager", region_name=region_name)
                logger.info(
                    "secrets_manager_initialized",
                    region=region_name,
                    environment=ENVIRONMENT,
                )
            except ImportError:
                logger.warning(
                    "boto3_not_installed",
                    message="boto3 not available, falling back to environment variables",
                )
                self._client = None
        else:
            logger.info(
                "secrets_manager_disabled",
                message="Using environment variables for local development",
            )

    @lru_cache(maxsize=128)
    def get_secret(self, secret_name: str) -> dict:
        """Retrieve secret from AWS Secrets Manager (cached).

        Args:
            secret_name: Name of the secret in AWS Secrets Manager

        Returns:
            Dict containing secret data

        Raises:
            RuntimeError: If secret retrieval fails
        """
        if not self._client:
            logger.warning(
                "secrets_manager_unavailable",
                secret_name=secret_name,
                message="AWS Secrets Manager not available, returning empty dict",
            )
            return {}

        try:
            response = self._client.get_secret_value(SecretId=secret_name)
            secret_data = json.loads(response["SecretString"])
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
        env = environment or ENVIRONMENT

        if USE_AWS_SECRETS and self._client:
            secret_name = f"regengine/{env}/database"
            return self.get_secret(secret_name)

        # Fallback to environment variables
        return {
            "username": os.getenv("POSTGRES_USER", "postgres"),
            "password": os.getenv("POSTGRES_PASSWORD", ""),
            "host": os.getenv("POSTGRES_HOST", "localhost"),
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
        env = environment or ENVIRONMENT

        if USE_AWS_SECRETS and self._client:
            secret_name = f"regengine/{env}/neo4j"
            return self.get_secret(secret_name)

        # Fallback to environment variables
        return {
            "uri": os.getenv("NEO4J_URI", "bolt://localhost:7687"),
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
        env = environment or ENVIRONMENT

        if USE_AWS_SECRETS and self._client:
            secret_name = f"regengine/{env}/kafka"
            return self.get_secret(secret_name)

        # Fallback to environment variables
        return {
            "bootstrap_servers": os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
            "username": os.getenv("KAFKA_USERNAME", ""),
            "password": os.getenv("KAFKA_PASSWORD", ""),
            "security_protocol": os.getenv("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT"),
        }

    def get_s3_credentials(self, environment: Optional[str] = None) -> dict:
        """Get S3 credentials and configuration.

        Args:
            environment: Environment name (production, staging, dev)

        Returns:
            Dict with access_key_id, secret_access_key, region, bucket_prefix
        """
        env = environment or ENVIRONMENT

        if USE_AWS_SECRETS and self._client:
            secret_name = f"regengine/{env}/s3"
            return self.get_secret(secret_name)

        # Fallback to environment variables
        return {
            "access_key_id": os.getenv("AWS_ACCESS_KEY_ID", ""),
            "secret_access_key": os.getenv("AWS_SECRET_ACCESS_KEY", ""),
            "region": os.getenv("AWS_REGION", "us-east-1"),
            "bucket_prefix": os.getenv("S3_BUCKET_PREFIX", "regengine-dev"),
        }

    def get_admin_master_key(self, environment: Optional[str] = None) -> str:
        """Get admin master key for API authentication.

        Args:
            environment: Environment name (production, staging, dev)

        Returns:
            Admin master key string
        """
        env = environment or ENVIRONMENT

        if USE_AWS_SECRETS and self._client:
            secret_name = f"regengine/{env}/admin"
            secret_data = self.get_secret(secret_name)
            return secret_data.get("master_key", "")

        # Fallback to environment variable
        return os.getenv("ADMIN_MASTER_KEY", "dev_master_key_change_in_production")


# Global instance for singleton pattern
_secrets_manager: Optional[SecretsManager] = None


def get_secrets_manager(region_name: str = "us-east-1") -> SecretsManager:
    """Get the global SecretsManager instance.

    Args:
        region_name: AWS region for Secrets Manager

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
    "AWS_ACCESS_KEY_ID": ["test"],
    "AWS_SECRET_ACCESS_KEY": ["test"],
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
        error_msg += "\n  1. AWS Secrets Manager (set USE_AWS_SECRETS=true)"
        error_msg += "\n  2. Secure environment variables"
        error_msg += "\n  3. For development, set REGENGINE_ENV=development"

        logger.error("production_secrets_validation_failed", errors=errors, environment=env)
        raise RuntimeError(error_msg)

    logger.info("production_secrets_validated", environment=env, checks_passed=len(INSECURE_DEFAULTS))


def require_aws_secrets_in_production() -> None:
    """Ensure AWS Secrets Manager is enabled in production mode.

    Raises:
        RuntimeError: If running in production without AWS Secrets Manager
    """
    env = os.getenv("REGENGINE_ENV", "development")

    if env.lower() != "production":
        return

    if not USE_AWS_SECRETS:
        error_msg = (
            "Production mode requires AWS Secrets Manager integration.\n"
            "Set USE_AWS_SECRETS=true and configure AWS credentials.\n"
            "For development, set REGENGINE_ENV=development"
        )
        logger.error("aws_secrets_required_in_production", environment=env)
        raise RuntimeError(error_msg)
